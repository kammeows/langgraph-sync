from typing import Optional
from datetime import datetime

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt.chat_agent_executor import AgentState


# ---------------- State ----------------

class LlamaPressState(AgentState):
    api_token: str
    agent_prompt: str
    page_id: str
    current_page_html: str
    selected_element: Optional[str]
    javascript_console_errors: Optional[str]
    created_at: Optional[datetime] = datetime.now()


# ---------------- Dummy child agents ----------------

def build_html_agent(checkpointer=None):
    builder = StateGraph(LlamaPressState)

    def html_node(state):
        return {}

    builder.add_node("html", html_node)
    builder.add_edge(START, "html")
    builder.add_edge("html", END)

    return builder.compile(checkpointer=checkpointer)


def build_clone_agent(checkpointer=None):
    builder = StateGraph(LlamaPressState)

    def clone_node(state):
        return {}

    builder.add_node("clone", clone_node)
    builder.add_edge(START, "clone")
    builder.add_edge("clone", END)

    return builder.compile(checkpointer=checkpointer)


# ---------------- Router ----------------

def route_to_agent(state: LlamaPressState):
    return {"next": "html_agent"}


# ---------------- Supervisor ----------------

def build_workflow(checkpointer=None):
    html_agent = build_html_agent(checkpointer)
    clone_agent = build_clone_agent(checkpointer)

    builder = StateGraph(LlamaPressState)

    builder.add_node("route_to_agent", route_to_agent)
    builder.add_node("html_agent", html_agent)
    builder.add_node("clone_agent", clone_agent)

    builder.add_edge(START, "route_to_agent")

    builder.add_conditional_edges(
        "route_to_agent",
        lambda x: x["next"],
        {
            "html_agent": "html_agent",
            "clone_agent": "clone_agent",
        },
    )

    builder.add_edge("html_agent", END)
    builder.add_edge("clone_agent", END)

    return builder.compile(checkpointer=checkpointer)


graph = build_workflow()