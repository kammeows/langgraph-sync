import subprocess
import os
import re
import uuid
import time
from typing import Optional, Dict, Any, List
import requests

def get_workspace_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def run_git_cmd(args: List[str], cwd: str) -> str:
    try:
        res = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except subprocess.CalledProcessError as e:
        # Securely mask tokens in command arguments to prevent secret leakage
        safe_cmd = []
        for arg in e.cmd:
            if "@github.com" in arg or "github_pat_" in arg or "ghp_" in arg:
                masked = re.sub(r"https://[^@]+@", "https://***@", arg)
                safe_cmd.append(masked)
            else:
                safe_cmd.append(arg)
        
        err_msg = f"Git command failed: {' '.join(safe_cmd)}"
        if e.stderr:
            # Securely mask tokens in stderr text
            safe_stderr = re.sub(r"github_pat_[a-zA-Z0-9_]+|ghp_[a-zA-Z0-9_]+", "***", e.stderr)
            err_msg += f"\nDetails: {safe_stderr.strip()}"
        raise RuntimeError(err_msg) from e

def get_github_repo_info(cwd: str) -> tuple[str, str]:
    try:
        url = run_git_cmd(["remote", "get-url", "origin"], cwd)
        # Regex to match owner and repo from HTTPS or SSH formats
        match = re.search(r"github\.com[/:]([^/]+)/([^/]+?)(?:\.git)?$", url)
        if match:
            return match.group(1), match.group(2)
    except Exception as e:
        print("Error getting remote repo info:", e)
    
    # Fallback to env
    repo_env = os.getenv("GITHUB_REPOSITORY", "")
    if "/" in repo_env:
        parts = repo_env.split("/")
        return parts[0], parts[1]
    return "", ""

def get_git_status() -> Dict[str, Any]:
    cwd = get_workspace_root()
    try:
        # Check if git is initialized
        if not os.path.exists(os.path.join(cwd, ".git")):
            return {"initialized": False, "msg": "Not a git repository."}
            
        branch = run_git_cmd(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
        status_out = run_git_cmd(["status", "--porcelain"], cwd)
        
        modified_files = []
        if status_out:
            for line in status_out.splitlines():
                parts = line.strip().split(maxsplit=1)
                if len(parts) == 2:
                    modified_files.append(parts[1])
                    
        owner, repo = get_github_repo_info(cwd)
        
        return {
            "initialized": True,
            "active_branch": branch,
            "is_clean": len(modified_files) == 0,
            "modified_files": modified_files,
            "repo_owner": owner,
            "repo_name": repo,
            "has_remote": bool(owner and repo)
        }
    except Exception as e:
        return {"initialized": False, "msg": str(e)}

def get_git_diff() -> str:
    cwd = get_workspace_root()
    try:
        # Diff unstaged and staged changes
        diff_unstaged = run_git_cmd(["diff"], cwd)
        diff_staged = run_git_cmd(["diff", "--cached"], cwd)
        
        diffs = []
        if diff_unstaged:
            diffs.append(diff_unstaged)
        if diff_staged:
            diffs.append(diff_staged)
            
        return "\n\n".join(diffs) if diffs else "No local changes detected."
    except Exception as e:
        return f"Error generating diff: {str(e)}"

def create_pull_request(title: str, body: str) -> Dict[str, Any]:
    cwd = get_workspace_root()
    token = os.getenv("GITHUB_PAT") or os.getenv("GITHUB_TOKEN")
    
    if not token:
        return {
            "success": False,
            "error": "GITHUB_PAT or GITHUB_TOKEN environment variable is not configured in .env file."
        }
        
    status = get_git_status()
    if not status.get("initialized"):
        return {"success": False, "error": "Not a git repository."}
        
    if status.get("is_clean"):
        return {"success": False, "error": "No local changes detected. Make some structural mutations first!"}
        
    owner = status.get("repo_owner")
    repo = status.get("repo_name")
    if not owner or not repo:
        return {"success": False, "error": "Could not determine GitHub repository owner or name from remote origin."}

    original_branch = status["active_branch"]
    temp_branch = f"autopilot/change-{uuid.uuid4().hex[:8]}-{int(time.time())}"
    
    try:
        # 1. Create and switch to temp branch
        run_git_cmd(["checkout", "-b", temp_branch], cwd)
        
        # 2. Stage and commit all changes
        run_git_cmd(["add", "."], cwd)
        run_git_cmd(["commit", "-m", title], cwd)
        
        # 3. Push branch to remote origin using token in URL for authentication
        push_url = f"https://{token}@github.com/{owner}/{repo}.git"
        run_git_cmd(["push", push_url, f"{temp_branch}:{temp_branch}"], cwd)
        
        # 4. Create Pull Request via GitHub REST API
        pr_api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        payload = {
            "title": title,
            "body": body,
            "head": temp_branch,
            "base": original_branch
        }
        
        response = requests.post(pr_api_url, json=payload, headers=headers)
        
        # 5. Switch back to original branch
        run_git_cmd(["checkout", original_branch], cwd)
        
        # 6. Delete local temp branch to keep it clean
        run_git_cmd(["branch", "-D", temp_branch], cwd)
        
        if response.status_code == 201:
            data = response.json()
            return {
                "success": True,
                "pr_url": data.get("html_url"),
                "pr_number": data.get("number"),
                "branch_name": temp_branch
            }
        else:
            err_msg = response.json().get("message", "Unknown error from GitHub API")
            return {
                "success": False,
                "error": f"Failed to create PR (status {response.status_code}): {err_msg}"
            }
            
    except Exception as e:
        # Fallback: make sure we checkout back to original branch
        try:
            run_git_cmd(["checkout", original_branch], cwd)
        except Exception:
            pass
        return {"success": False, "error": str(e)}
