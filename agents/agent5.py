from typing import List, TypedDict, Annotated
from langchain_core.messages import AIMessage
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.message import add_messages
from pydantic import BaseModel
import uuid
from dotenv import load_dotenv
import os

load_dotenv()

# Configure LLM
llm = ChatGroq(
    temperature=0.1,
    model_name="mixtral-8x7b-32768",
    groq_api_key=os.getenv("GROQ_API_KEY")
)
# Define State and Graph
class CodeState(TypedDict):
    messages: Annotated[list, add_messages]
    code: str
    error: str
    iterations: int
    thread_id: str
    checkpoint_namespace: str
    state_checkpoint_id: str
    previous_response: str  # tracking for previous response


def generate(state: CodeState):
    current_message = state["messages"][-1].content if state["messages"] else ""
    
    # Skip if we get same response as previous
    if current_message == state.get("previous_response", ""):
        return {**state, "error": ""}
    
    response = llm.invoke(current_message)
    
    return {
        **state,
        "code": response.content,
        "previous_response": current_message,
        "error": "",
        "iterations": state.get("iterations", 0)
    }

def validate(state: CodeState):
    # default value for iterations if not present
    iterations = state.get("iterations", 0)
    try:
# Only try to execute if it looks like Python code
        if state["code"].strip() and not state["code"].startswith(('Hello', 'Hi')):
            exec(state["code"])
            return {**state, "error": "", "iterations": iterations}
        return {**state, "error": "", "iterations": iterations}
    except Exception as e:
        return {**state, "error": str(e), "iterations": iterations + 1}

def route(state: CodeState):
    # Only retry if there's an error and haven't exceeded max attempts
    if state["error"] and state["iterations"] < 3:
        return "generate"
    return "end"

   # if not state["error"] or state["iterations"] >= 3:
    #     return ""d"
    # return "generate"

workflow = StateGraph(CodeState)
workflow.add_node("generate", generate)
workflow.add_node("validate", validate)
workflow.add_edge(START, "generate")
workflow.add_edge("generate", "validate")
workflow.add_conditional_edges(
    "validate",
    route,
    {"end": END, "generate": "generate"}
)

graph = workflow.compile(checkpointer=MemorySaver())