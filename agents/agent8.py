from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage
from langgraph.graph import MessagesState
from langchain.agents.middleware import AgentMiddleware


class DummyMiddleware(AgentMiddleware):
    pass


# ---------------- State ----------------

class RailsAgentState(MessagesState):
    pass


# ---------------- Stub tools ----------------

@tool
def write_todos(text: str) -> str:
    """Stub."""
    pass

@tool
def ls(path: str = ".") -> str:
    """Stub."""
    pass

@tool
def read_file(path: str) -> str:
    """Stub."""
    pass

@tool
def write_file(path: str, content: str) -> str:
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
def fix_permissions() -> str:
    """Stub."""
    pass

@tool
def delegate_research(query: str) -> str:
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


default_tools = [
    write_todos,
    ls,
    read_file,
    write_file,
    edit_file,
    search_file,
    bash_command,
    fix_permissions,
    delegate_research,
    ls_agents,
    read_agent_file,
    write_agent_file,
    edit_agent_file,
    read_langgraph_json,
    edit_langgraph_json,
]


# ---------------- Stub model ----------------

class DummyModel:
    """Never actually invoked."""
    pass


# ---------------- Stub middleware ----------------

class SummarizationMiddleware:
    def __init__(self, *args, **kwargs):
        pass


class DynamicModelMiddleware:
    pass


def inject_view_context(*args, **kwargs):
    pass


def inject_testing_mode_context(*args, **kwargs):
    pass


def check_failure_limit(*args, **kwargs):
    pass


# ---------------- System prompt ----------------

def get_cached_system_prompt():
    return SystemMessage(content="Testing agent")


# ---------------- Graph ----------------

graph = create_agent(
    model=DummyModel(),
    tools=default_tools,
    system_prompt=get_cached_system_prompt(),
    state_schema=RailsAgentState,
    middleware = [
    DummyMiddleware()
]
)