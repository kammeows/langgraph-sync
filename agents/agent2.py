from langgraph.graph import StateGraph, END, START
from agents.extra_module import (
    AgentState,
    router_agent,
    research_agent,
    tool_agent,
    analyst_agent,
    report_agent,
    route_after_router,
)

builder = StateGraph(AgentState)

builder.add_node("router_v2", router_agent)
builder.add_node("research", research_agent)
builder.add_node("tool", tool_agent)
builder.add_node("analysis", analyst_agent)
builder.add_node("report", report_agent)
builder.add_edge(START, "router_v2")

builder.add_conditional_edges(
    "router_v2",
    route_after_router,
    {
        "research": "research",
        "tool": "tool",
    },
)

builder.add_edge("research", "tool")
builder.add_edge("tool", "analysis")
builder.add_edge("analysis", "report")
builder.add_edge("report", END)

graph = builder.compile()