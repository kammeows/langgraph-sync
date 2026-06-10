import libcst as cst
from libcst import matchers as m


class AgentGraphAnalyzer(cst.CSTVisitor):

    def __init__(self):

        self.functions = set()

        self.nodes = {}
        self.edges = []

        self.routing_functions = set()

        self.conditional_edges = []

        self.current_function = None

        self.function_calls = {}

    # ---------------------------
    # functions
    # ---------------------------

    def visit_FunctionDef(self, node):

        fn = node.name.value

        self.functions.add(fn)

        self.current_function = fn

        self.function_calls.setdefault(fn, set())

    def leave_FunctionDef(self, node):

        self.current_function = None

    # ---------------------------
    # calls
    # ---------------------------

    def visit_Call(self, node):

        # collect function calls

        if (
            self.current_function
            and isinstance(node.func, cst.Name)
        ):
            self.function_calls[
                self.current_function
            ].add(node.func.value)

        # -------------------
        # add_node
        # -------------------

        if m.matches(
            node.func,
            m.Attribute(
                value=m.Name("builder"),
                attr=m.Name("add_node")
            )
        ):

            node_name = (
                node.args[0]
                .value
                .evaluated_value
            )

            fn_name = (
                node.args[1]
                .value
                .value
            )

            self.nodes[node_name] = fn_name

        # -------------------
        # add_edge
        # -------------------

        if m.matches(
            node.func,
            m.Attribute(
                value=m.Name("builder"),
                attr=m.Name("add_edge")
            )
        ):

            src = node.args[0].value
            dst = node.args[1].value

            if (
                isinstance(src, cst.SimpleString)
                and isinstance(dst, cst.SimpleString)
            ):

                self.edges.append(
                    (
                        src.evaluated_value,
                        dst.evaluated_value,
                    )
                )

        # -------------------
        # add_conditional_edges
        # -------------------

        if m.matches(
            node.func,
            m.Attribute(
                value=m.Name("builder"),
                attr=m.Name("add_conditional_edges")
            )
        ):

            source = (
                node.args[0]
                .value
                .evaluated_value
            )

            router_fn = (
                node.args[1]
                .value
                .value
            )

            self.routing_functions.add(
                router_fn
            )

            self.conditional_edges.append(
                {
                    "source": source,
                    "router": router_fn,
                }
            )

with open("agent.py", "r") as f:
    source = f.read()

module = cst.parse_module(source)

analyzer = AgentGraphAnalyzer()

module.visit(analyzer)

graph_agent_functions = set(
    analyzer.nodes.values()
)

tools = (
    analyzer.functions
    - graph_agent_functions
    - analyzer.routing_functions
)

agent_tool_usage = {}

for node_name, fn_name in analyzer.nodes.items():

    calls = analyzer.function_calls.get(
        fn_name,
        set()
    )

    used_tools = sorted(
        calls & tools
    )

    agent_tool_usage[node_name] = used_tools


domain_graph = {
    "agents": analyzer.nodes,
    "tools": sorted(tools),
    "edges": analyzer.edges,
    "conditional_edges": analyzer.conditional_edges,
    "agent_tool_usage": agent_tool_usage,
}

from pprint import pprint

pprint(domain_graph)