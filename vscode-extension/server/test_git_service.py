import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Add server directory to path if not already there
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from git_service import get_git_status, get_git_diff, create_pull_request, get_github_repo_info, run_git_cmd

class TestGitService(unittest.TestCase):

    @patch("git_service.subprocess.run")
    def test_run_git_cmd_mask_error(self, mock_sub_run):
        import subprocess
        # Mock subprocess.run raising CalledProcessError containing token
        mock_sub_run.side_effect = subprocess.CalledProcessError(
            returncode=128,
            cmd=["git", "push", "https://github_pat_SECRET123@github.com/owner/repo.git"],
            stderr="error: failed to push some refs to 'https://github_pat_SECRET123@github.com/owner/repo.git'"
        )

        with self.assertRaises(RuntimeError) as context:
            run_git_cmd(["push", "https://github_pat_SECRET123@github.com/owner/repo.git"], "/dummy")

        err_msg = str(context.exception)
        # Verify the secret token is masked in the error message
        self.assertNotIn("SECRET123", err_msg)
        self.assertIn("https://***@github.com/owner/repo.git", err_msg)
        self.assertIn("Details:", err_msg)

    @patch("git_service.run_git_cmd")
    def test_get_github_repo_info_https(self, mock_run):
        # Test HTTPS remote URL format
        mock_run.return_value = "https://github.com/owner/my-repo-name.git"
        owner, repo = get_github_repo_info("/dummy/path")
        self.assertEqual(owner, "owner")
        self.assertEqual(repo, "my-repo-name")

    @patch("git_service.run_git_cmd")
    def test_get_github_repo_info_ssh(self, mock_run):
        # Test SSH remote URL format
        mock_run.return_value = "git@github.com:owner/my-repo-name.git"
        owner, repo = get_github_repo_info("/dummy/path")
        self.assertEqual(owner, "owner")
        self.assertEqual(repo, "my-repo-name")

    @patch("git_service.run_git_cmd")
    def test_get_git_status_dirty(self, mock_run):
        # Setup git commands stdout mock
        def side_effect(args, cwd):
            if "rev-parse" in args:
                return "main"
            elif "status" in args:
                return " M agents/agent.py\n?? server/new_file.py"
            elif "remote" in args:
                return "https://github.com/owner/my-repo.git"
            return ""
        
        mock_run.side_effect = side_effect
        
        # Mock folder check
        with patch("os.path.exists", return_value=True):
            status = get_git_status()
            self.assertTrue(status["initialized"])
            self.assertEqual(status["active_branch"], "main")
            self.assertFalse(status["is_clean"])
            self.assertEqual(status["modified_files"], ["agents/agent.py", "server/new_file.py"])
            self.assertEqual(status["repo_owner"], "owner")
            self.assertEqual(status["repo_name"], "my-repo")

    @patch("git_service.run_git_cmd")
    def test_get_git_diff(self, mock_run):
        def side_effect(args, cwd):
            if "--cached" in args:
                return "staged change diff content"
            return "unstaged change diff content"
        
        mock_run.side_effect = side_effect
        diff = get_git_diff()
        self.assertIn("unstaged change diff content", diff)
        self.assertIn("staged change diff content", diff)

    @patch("git_service.requests.post")
    @patch("git_service.get_git_status")
    @patch("git_service.run_git_cmd")
    @patch("os.getenv")
    def test_create_pull_request_success(self, mock_getenv, mock_run_git, mock_get_status, mock_post):
        # Setup environment variables, status, and API responses
        mock_getenv.return_value = "mock_github_token"
        
        mock_get_status.return_value = {
            "initialized": True,
            "active_branch": "main",
            "is_clean": False,
            "modified_files": ["agents/agent.py"],
            "repo_owner": "owner",
            "repo_name": "repo",
            "has_remote": True
        }
        
        # Mock requests.post response
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "html_url": "https://github.com/owner/repo/pull/1",
            "number": 1
        }
        mock_post.return_value = mock_response

        # Execute
        res = create_pull_request("feat: my change", "some description")
        
        # Verify
        self.assertTrue(res["success"])
        self.assertEqual(res["pr_url"], "https://github.com/owner/repo/pull/1")
        self.assertEqual(res["pr_number"], 1)
        
        # Verify git checkout back, and checkout-b, add, commit, push runs
        checkout_main_called = any(
            args[0] == ["checkout", "main"] for args, _ in mock_run_git.call_args_list
        )
        self.assertTrue(checkout_main_called)

    @patch("git_service.requests.post")
    @patch("git_service.get_git_status")
    @patch("git_service.run_git_cmd")
    @patch("os.getenv")
    def test_create_pull_request_failure(self, mock_getenv, mock_run_git, mock_get_status, mock_post):
        mock_getenv.return_value = "mock_github_token"
        mock_get_status.return_value = {
            "initialized": True,
            "active_branch": "main",
            "is_clean": False,
            "modified_files": ["agents/agent.py"],
            "repo_owner": "owner",
            "repo_name": "repo",
            "has_remote": True
        }
        
        # Mock failed API response
        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.json.return_value = {
            "message": "Validation Failed"
        }
        mock_post.return_value = mock_response

        # Execute
        res = create_pull_request("feat: my change", "some description")
        
        # Verify
        self.assertFalse(res["success"])
        self.assertIn("Failed to create PR", res["error"])

if __name__ == "__main__":
    unittest.main()
