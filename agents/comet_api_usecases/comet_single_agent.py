import os
from typing import TypedDict
from openai import OpenAI
from langgraph.graph import StateGraph, END

# Initialize the Comet API client (OpenAI-compatible)
comet_client = OpenAI(
    api_key=os.getenv("COMETAPI_KEY", "mock_key"),
    base_url="https://api.cometapi.com/v1"
)

class SingleAgentState(TypedDict):
    input: str
    reasoning: str
    output: str

def reasoning_node(state: SingleAgentState):
    """Reasoning node that invokes DeepSeek-R1 (deepseek-reasoner) via Comet API."""
    response = comet_client.chat.completions.create(
        model="deepseek/deepseek-reasoner",
        messages=[
            {"role": "system", "content": "You are a logical solver agent that reasons step-by-step."},
            {"role": "user", "content": state["input"]}
        ]
    )
    return {
        "reasoning": getattr(response.choices[0].message, "reasoning_content", "Reasoned locally."),
        "output": response.choices[0].message.content
    }

builder = StateGraph(SingleAgentState)
builder.add_node("reasoner", reasoning_node)
builder.set_entry_point("reasoner")
builder.add_edge("reasoner", END)

graph = builder.compile()
