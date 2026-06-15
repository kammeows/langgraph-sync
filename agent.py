from typing import TypedDict, Literal
from dataclasses import dataclass
import os
import requests
import json

from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI


# ---------------------------------
# LLM
# ---------------------------------

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=os.getenv("GEMINI_API_KEY"),
)


# ---------------------------------
# State
# ---------------------------------

class AgentState(TypedDict):
    query: str
    intent: str
    research_notes: str
    tool_output: str
    analysis: str
    final_report: str


# ---------------------------------
# Tool Registry
# ---------------------------------

@dataclass
class ToolResult:
    success: bool
    data: str


def wikipedia_tool(query: str) -> ToolResult:
    try:
        response = requests.get(
            "https://en.wikipedia.org/api/rest_v1/page/summary/" + query
        )

        data = response.json()

        return ToolResult(
            success=True,
            data=data.get("extract", "")
        )

    except Exception as e:
        return ToolResult(
            success=False,
            data=str(e)
        )


def weather_tool(city: str) -> ToolResult:

    fake_weather = {
        "Delhi": "42C, Hot",
        "Mumbai": "31C, Humid",
        "London": "18C, Cloudy",
    }

    return ToolResult(
        success=True,
        data=fake_weather.get(city, "Unknown")
    )


def calculator_tool(expression: str) -> ToolResult:

    try:
        result = eval(expression)

        return ToolResult(
            success=True,
            data=str(result)
        )

    except Exception as e:
        return ToolResult(
            success=False,
            data=str(e)
        )


TOOLS = {
    "wiki": wikipedia_tool,
    "weather": weather_tool,
    "calculator": calculator_tool,
}


# ---------------------------------
# Agent 1
# Router
# ---------------------------------

def router_agent(state: AgentState):

    query = state["query"].lower()

    if "weather" in query:
        intent = "weather"

    elif any(
        keyword in query
        for keyword in ["calculate", "+", "-", "*", "/"]
    ):
        intent = "calculator"

    else:
        intent = "research"

    return {
        "intent": intent
    }


# ---------------------------------
# Agent 2
# Research Agent
# ---------------------------------

def research_agent(state: AgentState):

    prompt = (
    f"Research this topic:\n\n"
    f"{state['query']}\n\n"
    f"Provide key facts and context."
)

    result = llm.invoke(prompt)

    return {
        "research_notes": result.content
    }


# ---------------------------------
# Agent 3
# Tool Agent
# ---------------------------------

def tool_agent(state: AgentState):

    intent = state["intent"]

    if intent == "weather":

        result = weather_tool("Delhi")

    elif intent == "calculator":

        result = calculator_tool("12 * 8 + 5")

    else:

        result = wikipedia_tool(
            state["query"].replace(" ", "_")
        )

    return {
        "tool_output": result.data
    }


# ---------------------------------
# Agent 4
# Analyst
# ---------------------------------

def analyst_agent(state: AgentState):
    
    prompt = (
    f"User Query: {state['query']}\n\n"
    f"Research: {state.get('research_notes', '')}\n\n"
    f"Tool Output: {state['tool_output']}\n\n"
    f"Create an analysis."
)

    result = llm.invoke(prompt)

    return {
        "analysis": result.content
    }


# ---------------------------------
# Agent 5
# Report Agent
# ---------------------------------

def report_agent(state: AgentState):

    prompt = (
    f"Generate a final report.\n\n"
    f"Analysis:\n\n"
    f"{state['analysis']}"
)

    result = llm.invoke(prompt)

    return {
        "final_report": result.content
    }


# ---------------------------------
# Routing Logic
# ---------------------------------

def route_after_router(
    state: AgentState
) -> Literal["tool", "research"]:

    if state["intent"] == "research":
        return "research"

    return "tool"


# ---------------------------------
# Graph
# ---------------------------------

builder = StateGraph(AgentState)

builder.add_node("router", router_agent)
builder.add_node("research", research_agent)
builder.add_node("tool", tool_agent)
builder.add_node("analysis", analyst_agent)
builder.add_node("report", report_agent)

builder.set_entry_point("router")

builder.add_conditional_edges(
    "router",
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