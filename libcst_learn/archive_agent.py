from typing import TypedDict
import os
import requests

from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI

# ------------------------------------
# Gemini
# ------------------------------------

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=os.getenv("GEMINI_API_KEY"),
)

# ------------------------------------
# Shared State
# ------------------------------------

class AgentState(TypedDict):
    query: str
    research_notes: str
    news: str
    analysis: str
    critique: str
    final_report: str


# ------------------------------------
# Agent 1
# Research Agent
# ------------------------------------

def research_agent(state: AgentState):

    prompt = f"""
    Research this topic deeply:

    {state['query']}

    Produce:
    - key concepts
    - important facts
    - background context
    """

    result = llm.invoke(prompt)

    return {
        "research_notes": result.content
    }


# ------------------------------------
# Agent 2
# News Agent
# ------------------------------------

def news_agent(state: AgentState):

    api_key = os.getenv("NEWS_API_KEY")

    try:
        response = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": state["query"],
                "pageSize": 5,
                "sortBy": "publishedAt",
                "apiKey": api_key
            }
        )

        data = response.json()

        articles = []

        for article in data.get("articles", [])[:5]:

            articles.append(
                f"""
Title: {article['title']}
Source: {article['source']['name']}
Description: {article.get('description')}
URL: {article.get('url')}
"""
            )

        news_text = "\n\n".join(articles)

    except Exception as e:
        news_text = f"News fetch failed: {str(e)}"

    return {
        "news": news_text
    }


# ------------------------------------
# Agent 3
# Analyst Agent
# ------------------------------------

def analyst_agent(state: AgentState):

    prompt = f"""
You are a senior analyst.

Research:

{state['research_notes']}

Latest News:

{state['news']}

Provide:

1. Key findings
2. Trends
3. Opportunities
4. Risks
"""

    result = llm.invoke(prompt)

    return {
        "analysis": result.content
    }


# ------------------------------------
# Agent 4
# Critic Agent
# ------------------------------------

def critic_agent(state: AgentState):

    prompt = f"""
Critique this analysis.

Analysis:

{state['analysis']}

Find:

- weak assumptions
- missing information
- possible biases
- alternative interpretations
"""

    result = llm.invoke(prompt)

    return {
        "critique": result.content
    }


# ------------------------------------
# Agent 5
# Report Agent
# ------------------------------------

def report_agent(state: AgentState):

    prompt = f"""
Create a final executive report.

User Topic:
{state['query']}

Research:
{state['research_notes']}

News:
{state['news']}

Analysis:
{state['analysis']}

Critique:
{state['critique']}

Generate:

# Executive Summary
# Current Situation
# Opportunities
# Risks
# Final Conclusion
"""

    result = llm.invoke(prompt)

    return {
        "final_report": result.content
    }


# ------------------------------------
# Graph
# ------------------------------------

builder = StateGraph(AgentState)

builder.add_node("research", research_agent)
builder.add_node("news", news_agent)
builder.add_node("analysis", analyst_agent)
builder.add_node("critic", critic_agent)
builder.add_node("report", report_agent)

builder.set_entry_point("research")

builder.add_edge("research", "news")
builder.add_edge("news", "analysis")
builder.add_edge("analysis", "critic")
builder.add_edge("critic", "report")
builder.add_edge("report", END)

graph = builder.compile()