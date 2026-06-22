from typing import TypedDict, Literal
from dataclasses import dataclass
import os
import requests

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
# Tools
# ---------------------------------

@dataclass
class ToolResult:
    success: bool
    data: str


def wikipedia_tool(query: str) -> ToolResult:
    try:
        response = requests.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{query}"
        )

        return ToolResult(
            success=True,
            data=response.json().get("extract", "")
        )

    except Exception as e:
        return ToolResult(False, str(e))


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
        return ToolResult(False, str(e))


TOOLS = {
    "wiki": wikipedia_tool,
    "weather": weather_tool,
    "calculator": calculator_tool,
}


# ---------------------------------
# Agents
# ---------------------------------

def router_agent(state: AgentState):
    query = state["query"].lower()

    if "weather" in query:
        intent = "weather"

    elif any(k in query for k in ["calculate", "+", "-", "*", "/"]):
        intent = "calculator"

    else:
        intent = "research"

    return {"intent": intent}


def research_agent(state: AgentState):
    prompt = f"""
    Research this topic:

    {state['query']}

    Provide key facts and context.
    """

    result = llm.invoke(prompt)

    return {"research_notes": result.content}


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

    return {"tool_output": result.data}


def analyst_agent(state: AgentState):
    prompt = f"""
    User Query: {state['query']}

    Research: {state.get('research_notes', '')}

    Tool Output: {state['tool_output']}

    Create an analysis.
    """

    result = llm.invoke(prompt)

    return {"analysis": result.content}


def report_agent(state: AgentState):
    prompt = f"""
    Generate a final report.

    Analysis:

    {state['analysis']}
    """

    result = llm.invoke(prompt)

    return {"final_report": result.content}


# ---------------------------------
# Routes
# ---------------------------------

def route_after_router(
    state: AgentState
) -> Literal["tool", "research"]:

    if state["intent"] == "research":
        return "research"

    return "tool"