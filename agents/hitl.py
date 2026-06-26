from typing import TypedDict

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

# --------------------------------------------------------------------
# State
# --------------------------------------------------------------------

class MultiAgentState(TypedDict):
    question: str
    question_type: str
    answer: str
    feedback: str


# --------------------------------------------------------------------
# Human Feedback Node
# --------------------------------------------------------------------

def human_feedback_node(state: MultiAgentState):
    """
    This node is interrupted before execution.
    After resuming the graph, the feedback supplied by the user
    will be merged into the state.
    """
    return state


# --------------------------------------------------------------------
# Prompts
# --------------------------------------------------------------------

editor_prompt = """You're an editor and your goal is to provide the final answer to the customer, taking into account the feedback.
You don't add any information on your own. You use friendly and professional tone.
In the output please provide the final answer to the customer without additional comments.

Question from customer:
----
{question}
----

Draft answer:
----
{answer}
----

Feedback:
----
{feedback}
----
"""

question_category_prompt = """You are a senior specialist of analytical support.
Your task is to classify the incoming questions.

There are 3 possible question types:
- DATABASE
- LANGCHAIN
- GENERAL

Return only one word:
DATABASE
LANGCHAIN
GENERAL
"""

sql_expert_system_prompt = """
You are an expert SQL engineer.

Answer questions by using SQL whenever database information is needed.
Be precise and accurate.
"""

langchain_system_prompt = """
You are a senior LangChain and LangGraph expert.

Help users with:
- LangChain
- LangGraph
- Agents
- RAG
- Chains
- Memory
- Tools
- StateGraph

Provide clear technical explanations.
"""

general_system_prompt = """
You are a helpful AI assistant.

Answer the user's question professionally and clearly.
"""

# --------------------------------------------------------------------
# Database Expert
# --------------------------------------------------------------------

def execute_sql(query: str) -> str:
  """Returns the result of SQL query execution"""
  return "temporary data"

def sql_expert_node(state: MultiAgentState):
    model = ChatOpenAI(model="gpt-4o-mini")

    sql_agent = create_react_agent(
        model,
        [execute_sql],          # your SQL tool
        state_modifier=sql_expert_system_prompt
    )

    result = sql_agent.invoke(
        {
            "messages": [
                HumanMessage(content=state["question"])
            ]
        }
    )

    return {
        "answer": result["messages"][-1].content
    }


# --------------------------------------------------------------------
# LangChain Expert
# --------------------------------------------------------------------

def search_expert_node(state: MultiAgentState):
    model = ChatOpenAI(model="gpt-4o-mini")

    messages = [
        SystemMessage(content=langchain_system_prompt),
        HumanMessage(content=state["question"])
    ]

    response = model.invoke(messages)

    return {
        "answer": response.content
    }


# --------------------------------------------------------------------
# General Assistant
# --------------------------------------------------------------------

def general_assistant_node(state: MultiAgentState):
    model = ChatOpenAI(model="gpt-4o-mini")

    messages = [
        SystemMessage(content=general_system_prompt),
        HumanMessage(content=state["question"])
    ]

    response = model.invoke(messages)

    return {
        "answer": response.content
    }


# --------------------------------------------------------------------
# Router
# --------------------------------------------------------------------

def router_node(state: MultiAgentState):

    model = ChatOpenAI(model="gpt-4o-mini")

    messages = [
        SystemMessage(content=question_category_prompt),
        HumanMessage(content=state["question"])
    ]

    response = model.invoke(messages)

    return {
        "question_type": response.content.strip().upper()
    }


def route_question(state: MultiAgentState):
    return state["question_type"]


# --------------------------------------------------------------------
# Editor
# --------------------------------------------------------------------

def editor_node(state: MultiAgentState):

    model = ChatOpenAI(model="gpt-4o-mini")

    prompt = editor_prompt.format(
        question=state["question"],
        answer=state["answer"],
        feedback=state.get("feedback", "")
    )

    response = model.invoke(
        [
            SystemMessage(content=prompt)
        ]
    )

    return {
        "answer": response.content
    }


# --------------------------------------------------------------------
# Memory
# --------------------------------------------------------------------

memory = MemorySaver()

# --------------------------------------------------------------------
# Graph
# --------------------------------------------------------------------

builder = StateGraph(MultiAgentState)

builder.add_node("router", router_node)
builder.add_node("database_expert", sql_expert_node)
builder.add_node("langchain_expert", search_expert_node)
builder.add_node("general_assistant", general_assistant_node)
builder.add_node("human_validation", human_feedback_node)
builder.add_node("editor", editor_node)

builder.set_entry_point("router")

builder.add_conditional_edges(
    "router",
    route_question,
    {
    "LANGCHAIN": "langchain_expert",
    "GENERAL": "general_assistant",
    "DATABASE": "database_expert",
},
)

builder.add_edge("database_expert", "human_validation")
builder.add_edge("langchain_expert", "human_validation")
builder.add_edge("general_assistant", "human_validation")

builder.add_edge("human_validation", "editor")
builder.add_edge("editor", END)

graph = builder.compile(
    interrupt_before=["human_validation"]
)