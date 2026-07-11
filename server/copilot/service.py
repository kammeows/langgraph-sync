import os
import json
import traceback
from typing import Optional, List, Dict, Any
from google import genai
from google.genai import types
from fastapi import HTTPException

PROMPT_DIR = os.path.join(os.path.dirname(__file__), "prompts")
SYSTEM_INSTRUCTION_PATH = os.path.join(PROMPT_DIR, "system_instruction.md")
BUSINESS_INSTRUCTION_PATH = os.path.join(PROMPT_DIR, "business_instruction.md")

def load_instruction(mode: str) -> str:
    path = BUSINESS_INSTRUCTION_PATH if mode == "business" else SYSTEM_INSTRUCTION_PATH
    try:
        with open(path, "r", encoding="utf8") as f:
            return f.read()
    except Exception as e:
        print(f"Error loading instructions file {path}:", e)
        if mode == "business":
            return (
                "You are an AI Business Coder for a LangGraph visual editor. "
                "Modify the target node's Python function code and return the edit mutation."
            )
        return (
            "You are an AI Copilot for a LangGraph visual editor. "
            "You translate user requests into sequences of graph mutations."
        )

async def run_copilot_chat(
    query: str, 
    nodes_summary: List[Dict[str, Any]], 
    edges_summary: List[Dict[str, Any]], 
    history: Optional[List[Dict[str, str]]] = None,
    mode: str = "structural",
    model: str = "google/gemini-2.5-flash",
    source_code: Optional[str] = None
) -> Any:
    gemini_key = os.getenv("GEMINI_API_KEY")
    comet_key = os.getenv("COMETAPI_KEY")
    
    use_comet = bool(comet_key and (model != "google/gemini-2.5-flash" or "/" in model))
    
    if not gemini_key and not use_comet:
        raise HTTPException(status_code=400, detail="Neither GEMINI_API_KEY nor COMETAPI_KEY is configured in backend.")
        
    from git_service import get_git_status
    status = get_git_status()
    active_branch = status.get("active_branch", "main")
    
    history_str = ""
    if history:
        history_str = "Conversation history (context of previous user requests and your responses):\n"
        for msg in history:
            role = "User" if msg.get("sender") == "user" else "Copilot"
            content = msg.get("content", "")
            if len(content) > 500:
                content = content[:500] + "..."
            history_str += f"{role}: {content}\n"
        history_str += "\n"

    prompt = f"""
Current graph context (nodes and edges):
Nodes: {json.dumps(nodes_summary)}
Edges: {json.dumps(edges_summary)}

Current Git Branch: {active_branch}
"""

    if mode == "business" and source_code:
        prompt += f"\nActive Python Source Code:\n```python\n{source_code}\n```\n"

    prompt += f"\n{history_str}User Request: {query}\n"
    system_instruction = load_instruction(mode)

    try:
        if use_comet:
            import httpx
            headers = {
                "Authorization": f"Bearer {comet_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt}
                ],
                "response_format": {"type": "json_object"}
            }
            async with httpx.AsyncClient(timeout=60.0) as httpx_client:
                res = await httpx_client.post(
                    "https://api.cometapi.com/v1/chat/completions",
                    json=payload,
                    headers=headers
                )
                if res.status_code == 200:
                    data = res.json()
                    content = data["choices"][0]["message"]["content"]
                    return json.loads(content)
                else:
                    raise HTTPException(
                        status_code=res.status_code,
                        detail=f"CometAPI returned error: {res.text}"
                    )
        else:
            client = genai.Client(api_key=gemini_key)
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                ),
            )
            return json.loads(response.text)
            
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"LLM processing failed: {str(e)}")
