import os
from typing import TypedDict
from openai import OpenAI
from langgraph.graph import StateGraph, END

# Initialize the Comet API client (OpenAI-compatible)
comet_client = OpenAI(
    api_key=os.getenv("COMETAPI_KEY", "mock_key"),
    base_url="https://api.cometapi.com/v1"
)

class CometAgentState(TypedDict):
    query: str
    planner_output: str
    coder_output: str
    critic_output: str
    final_response: str
def planner_node(state: CometAgentState):
    """Planner node using DeepSeek V3 via Comet API."""
    response = comet_client.chat.completions.create(
        model="deepseek/deepseek-chat",
        messages=[
            {"role": "system", "content": "You are a meticulous and highly organized senior planner. Your task is to create a comprehensive, step-by-step plan to achieve the user's goal. Break down the task into clear phases, specify dependencies between phases, suggest any required tools or resources, and flag potential risks or edge cases. Your output should be structured, actionable, and easy for a coder to follow."},
            {"role": "user", "content": f"Plan this task: {state['query']}"}
        ]
    )
    return {"planner_output": response.choices[0].message.content}

def coder_node(state: CometAgentState):
    """Coder node using Claude 3.5 Sonnet via Comet API."""
    response = comet_client.chat.completions.create(
        model="anthropic/claude-3-5-sonnet",
        messages=[
            {"role": "system", "content": "You are an expert coder agent."},
            {"role": "user", "content": f"Write code based on this plan: {state['planner_output']}"}
        ]
    )
    return {"coder_output": response.choices[0].message.content}

def critic_node(state: CometAgentState):
    """Critic node using GPT-4o via Comet API."""
    response = comet_client.chat.completions.create(
        model="openai/gpt-4o",
        messages=[
            {"role": "system", "content": "You are a critical reviewer agent."},
            {"role": "user", "content": f"Review this code: {state['coder_output']}"}
        ]
    )
    return {"critic_output": response.choices[0].message.content}

def synthesizer_node(state: CometAgentState):
    """Synthesizer node using Gemini 2.5 Flash via Comet API."""
    response = comet_client.chat.completions.create(
        model="google/gemini-2.5-flash",
        messages=[
            {"role": "system", "content": "You are a synthesizer agent."},
            {"role": "user", "content": f"Synthesize a final response from the work."}
        ]
    )
    return {"final_response": response.choices[0].message.content}

# Construct the graph
builder = StateGraph(CometAgentState)
builder.add_node("planner", planner_node)
builder.add_node("coder", coder_node)
builder.add_node("critic", critic_node)
builder.add_node("synthesizer", synthesizer_node)

builder.set_entry_point("planner")
builder.add_edge("planner", "coder")
builder.add_edge("coder", "critic")
builder.add_edge("critic", "synthesizer")
builder.add_edge("synthesizer", END)

graph = builder.compile()
