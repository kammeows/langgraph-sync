import os
import operator
from typing import Annotated
from typing_extensions import TypedDict

from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

# -------------------------------------------------------
# Environment
# -------------------------------------------------------

# os.environ["OPENAI_API_KEY"] = "your-api-key"

# -------------------------------------------------------
# Prompts
# -------------------------------------------------------

subjects_prompt = """
Generate a list of exactly 3 sub-topics related to this topic:

{topic}
"""

joke_prompt = """
Generate one funny joke about:

{subject}
"""

best_joke_prompt = """
Below are several jokes about {topic}.

Return ONLY the ID of the funniest joke.
The first joke has ID 0.

Jokes:

{jokes}
"""

# -------------------------------------------------------
# LLM
# -------------------------------------------------------

model = ChatOpenAI(
    model="gpt-4o",
    temperature=0,
)

# -------------------------------------------------------
# Structured Outputs
# -------------------------------------------------------

class Subjects(BaseModel):
    subjects: list[str]


class Joke(BaseModel):
    joke: str


class BestJoke(BaseModel):
    id: int


# -------------------------------------------------------
# Graph State
# -------------------------------------------------------

class OverallState(TypedDict):
    topic: str
    subjects: list[str]

    # reducer merges outputs from parallel nodes
    jokes: Annotated[list[str], operator.add]

    best_selected_joke: str


class JokeState(TypedDict):
    subject: str


# -------------------------------------------------------
# Nodes
# -------------------------------------------------------

def generate_topics(state: OverallState):
    prompt = subjects_prompt.format(topic=state["topic"])

    response = (
        model
        .with_structured_output(Subjects)
        .invoke(prompt)
    )

    return {
        "subjects": response.subjects
    }


def continue_to_jokes(state: OverallState):
    """
    Fan-out using Send.
    Creates one parallel execution for each subject.
    """
    return [
        Send(
            "generate_joke",
            {"subject": subject},
        )
        for subject in state["subjects"]
    ]


def generate_joke(state: JokeState):
    prompt = joke_prompt.format(
        subject=state["subject"]
    )

    response = (
        model
        .with_structured_output(Joke)
        .invoke(prompt)
    )

    return {
        "jokes": [response.joke]
    }


def best_joke(state: OverallState):
    jokes = "\n\n".join(
        f"{i}. {j}"
        for i, j in enumerate(state["jokes"])
    )

    prompt = best_joke_prompt.format(
        topic=state["topic"],
        jokes=jokes,
    )

    response = (
        model
        .with_structured_output(BestJoke)
        .invoke(prompt)
    )

    return {
        "best_selected_joke": state["jokes"][response.id]
    }


# -------------------------------------------------------
# Build Graph
# -------------------------------------------------------

builder = StateGraph(OverallState)

builder.add_node("generate_topics", generate_topics)
builder.add_node("generate_joke", generate_joke)
builder.add_node("best_joke", best_joke)

builder.add_edge(START, "generate_topics")

builder.add_conditional_edges(
    "generate_topics",
    continue_to_jokes,
    ["generate_joke"],
)

builder.add_edge(
    "generate_joke",
    "best_joke",
)

builder.add_edge(
    "best_joke",
    END,
)

app = builder.compile()

# -------------------------------------------------------
# Run
# -------------------------------------------------------

result = app.invoke(
    {
        "topic": "Animals"
    }
)

print("\nGenerated Subjects:\n")
print(result["subjects"])

print("\nGenerated Jokes:\n")
for i, joke in enumerate(result["jokes"]):
    print(f"{i}. {joke}")

print("\nBest Joke:\n")
print(result["best_selected_joke"])