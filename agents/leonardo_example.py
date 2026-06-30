from typing import Literal

from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.tools import tool


# ---------------- State ----------------

class RailsAgentState(MessagesState):
    pass


# ---------------- Dummy tools ----------------

@tool
def write_todos(text: str) -> str:
    """Stub."""
    pass

@tool
def write_file(path: str, content: str) -> str:
    """Stub."""
    pass

@tool
def read_file(path: str) -> str:
    """Stub."""
    pass

@tool
def ls(path: str = ".") -> str:
    """Stub."""
    pass

@tool
def edit_file(path: str, old: str, new: str) -> str:
    """Stub."""
    pass

@tool
def search_file(query: str) -> str:
    """Stub."""
    pass

@tool
def bash_command(cmd: str) -> str:
    """Stub."""
    pass

@tool
def ls_agents() -> str:
    """Stub."""
    pass

@tool
def read_agent_file(path: str) -> str:
    """Stub."""
    pass

@tool
def write_agent_file(path: str, content: str) -> str:
    """Stub."""
    pass

@tool
def edit_agent_file(path: str, old: str, new: str) -> str:
    """Stub."""
    pass

@tool
def read_langgraph_json() -> str:
    """Stub."""
    pass

@tool
def edit_langgraph_json(content: str) -> str:
    """Stub."""
    pass

@tool
def delegate_research(query: str) -> str:
    """Stub."""
    pass


default_tools = [
    write_todos,
    ls,
    read_file,
    write_file,
    edit_file,
    search_file,
    bash_command,
    delegate_research,
    ls_agents,
    read_agent_file,
    write_agent_file,
    edit_agent_file,
    read_langgraph_json,
    edit_langgraph_json,
]


# ---------------- Agent node ----------------

def leonardo_ai_builder(
    state: RailsAgentState,
) -> dict:
    # Never actually runs; exists only so the graph compiles.
    return {}


# ---------------- Graph ----------------

def build_workflow(checkpointer=None):
    builder = StateGraph(RailsAgentState)

    builder.add_node("leonardo_ai_builder", leonardo_ai_builder)
    builder.add_node("tools", ToolNode(default_tools))

    builder.add_edge(START, "leonardo_ai_builder")

    builder.add_conditional_edges(
        "leonardo_ai_builder",
        tools_condition,
    )

    builder.add_edge("tools", "leonardo_ai_builder")

    return builder.compile(checkpointer=checkpointer)


graph = build_workflow()