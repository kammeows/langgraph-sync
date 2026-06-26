from typing import TypedDict, List
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver


class AgentState(TypedDict):
    urls: List[str]
    schema_fields: List[str]
    schema_validated: bool
    requires_approval: bool


class ScrapeCraftAgent:
    def __init__(self):
        self.memory = MemorySaver()
        self.graph = self._build_graph()

    # ---------------- Nodes ----------------

    def analyze_request(self, state):
        return {}

    def collect_urls(self, state):
        return {}

    def validate_urls(self, state):
        return {}

    def define_schema(self, state):
        return {}

    def validate_schema(self, state):
        return {}

    def generate_code(self, state):
        return {}

    def await_approval(self, state):
        return {}

    def execute_pipeline(self, state):
        return {}

    def handle_error(self, state):
        return {}

    # ---------------- Routers ----------------

    def route_after_analysis(self, state):
        return "collect_urls"

    def route_after_approval(self, state):
        return "continue"

    def route_code_approval(self, state):
        return "execute"

    # ---------------- Graph ----------------

    def _build_graph(self):
        workflow = StateGraph(AgentState)

        workflow.add_node("analyze_request", self.analyze_request)
        workflow.add_node("collect_urls", self.collect_urls)
        workflow.add_node("validate_urls", self.validate_urls)
        workflow.add_node("define_schema", self.define_schema)
        workflow.add_node("validate_schema", self.validate_schema)
        workflow.add_node("generate_code", self.generate_code)
        workflow.add_node("await_approval", self.await_approval)
        workflow.add_node("execute_pipeline", self.execute_pipeline)
        workflow.add_node("handle_error", self.handle_error)

        workflow.set_entry_point("analyze_request")

        workflow.add_conditional_edges(
            "analyze_request",
            self.route_after_analysis,
            {
                "collect_urls": "collect_urls",
                "validate_urls": "validate_urls",
                "define_schema": "define_schema",
                "generate_code": "generate_code",
                "error": "handle_error",
            },
        )

        workflow.add_conditional_edges(
            "collect_urls",
            lambda state: "validate_urls" if state["urls"] else "handle_error",
        )

        workflow.add_conditional_edges(
            "validate_urls",
            lambda state: "await_approval"
            if state["requires_approval"]
            else "define_schema",
        )

        workflow.add_conditional_edges(
            "await_approval",
            self.route_after_approval,
            {
                "continue": "define_schema",
                "reject": "collect_urls",
                "timeout": "handle_error",
            },
        )

        workflow.add_conditional_edges(
            "define_schema",
            lambda state: "validate_schema"
            if state["schema_fields"]
            else "handle_error",
        )

        workflow.add_conditional_edges(
            "validate_schema",
            lambda state: "generate_code"
            if state["schema_validated"]
            else "define_schema",
        )

        workflow.add_edge("generate_code", "await_approval")

        workflow.add_conditional_edges(
            "await_approval",
            self.route_code_approval,
            {
                "execute": "execute_pipeline",
                "regenerate": "generate_code",
                "end": END,
            },
        )

        workflow.add_edge("execute_pipeline", END)
        workflow.add_edge("handle_error", END)

        return workflow.compile()


graph = ScrapeCraftAgent().graph