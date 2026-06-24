import os
import json
import traceback
from typing import Optional, List, Dict, Any
from google import genai
from google.genai import types
from fastapi import HTTPException

# Load the prompt file
PROMPT_DIR = os.path.join(os.path.dirname(__file__), "prompts")
SYSTEM_INSTRUCTION_PATH = os.path.join(PROMPT_DIR, "system_instruction.md")

def load_system_instruction() -> str:
    try:
        with open(SYSTEM_INSTRUCTION_PATH, "r", encoding="utf8") as f:
            return f.read()
    except Exception as e:
        print("Error loading system instructions prompt file:", e)
        # Fallback prompt in case reading from file fails
        return (
            "You are an AI Copilot for a LangGraph visual editor. "
            "You translate user requests into sequences of graph mutations."
        )

async def run_copilot_chat(query: str, nodes_summary: List[Dict[str, Any]], edges_summary: List[Dict[str, Any]], history: Optional[List[Dict[str, str]]] = None) -> Any:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=400, detail="GEMINI_API_KEY environment variable is not set in backend.")
    
    history_str = ""
    if history:
        history_str = "Conversation history (context of previous user requests and your responses):\n"
        for msg in history:
            role = "User" if msg.get("sender") == "user" else "Copilot"
            content = msg.get("content", "")
            # Skip long code blocks or system errors in history to keep context clean
            if len(content) > 500:
                content = content[:500] + "..."
            history_str += f"{role}: {content}\n"
        history_str += "\n"

    prompt = f"""
Current graph context (nodes and edges):
Nodes: {json.dumps(nodes_summary)}
Edges: {json.dumps(edges_summary)}

{history_str}User Request: {query}
"""
    system_instruction = load_system_instruction()

    try:
        client = genai.Client(api_key=api_key)
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
