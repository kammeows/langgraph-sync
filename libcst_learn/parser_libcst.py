import libcst as cst
from libcst import matchers as m


class LangGraphAnalyzer(cst.CSTVisitor):

    def __init__(self):
        self.functions = []
        self.nodes = {}
        self.edges = []
        self.conditional_edges = []

    # ----------------------------------
    # Collect all function defs
    # ----------------------------------

    def visit_FunctionDef(self, node: cst.FunctionDef):
        self.functions.append(node.name.value)

    # ----------------------------------
    # Collect builder.add_node(...)
    # ----------------------------------

    def visit_Call(self, node: cst.Call):

        if m.matches(
            node.func,
            m.Attribute(
                value=m.Name("builder"),
                attr=m.Name("add_node")
            )
        ):

            if len(node.args) >= 2:

                node_name = None
                function_name = None

                if isinstance(node.args[0].value, cst.SimpleString):
                    node_name = node.args[0].value.evaluated_value

                if isinstance(node.args[1].value, cst.Name):
                    function_name = node.args[1].value.value

                self.nodes[node_name] = function_name

        # ----------------------------------
        # builder.add_edge(...)
        # ----------------------------------

        if m.matches(
            node.func,
            m.Attribute(
                value=m.Name("builder"),
                attr=m.Name("add_edge")
            )
        ):

            if len(node.args) >= 2:

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

        # ----------------------------------
        # builder.add_conditional_edges(...)
        # ----------------------------------

        if m.matches(
            node.func,
            m.Attribute(
                value=m.Name("builder"),
                attr=m.Name("add_conditional_edges")
            )
        ):

            if len(node.args) >= 3:

                source = None
                router_fn = None

                if isinstance(
                    node.args[0].value,
                    cst.SimpleString
                ):
                    source = node.args[0].value.evaluated_value

                if isinstance(
                    node.args[1].value,
                    cst.Name
                ):
                    router_fn = node.args[1].value.value

                # Extract mapping
                mapping = {}
                if len(node.args) >= 3 and isinstance(node.args[2].value, cst.Dict):
                    for elt in node.args[2].value.elements:
                        if isinstance(elt, cst.DictElement):
                            key = None
                            val = None
                            if isinstance(elt.key, cst.SimpleString):
                                key = elt.key.evaluated_value
                            if isinstance(elt.value, cst.SimpleString):
                                val = elt.value.evaluated_value
                            if key and val:
                                mapping[key] = val

                self.conditional_edges.append(
                    {
                        "source": source,
                        "router": router_fn,
                        "mapping": mapping
                    }
                )

class ToolCallVisitor(cst.CSTVisitor):

    def __init__(self):

        self.current_function = None

        self.calls = {}

    def visit_FunctionDef(self, node):

        self.current_function = node.name.value

        self.calls[self.current_function] = []

    def leave_FunctionDef(self, node):

        self.current_function = None

    def visit_Call(self, node):

        if self.current_function is None:
            return

        if isinstance(node.func, cst.Name):

            self.calls[self.current_function].append(
                node.func.value
            )

with open("agent.py", "r", encoding="utf8") as f:
    source = f.read()

module = cst.parse_module(source)

analyzer = LangGraphAnalyzer()
module.visit(analyzer)

tool_visitor = ToolCallVisitor()
module.visit(tool_visitor)

print("\nFUNCTIONS")
print(analyzer.functions)

print("\nGRAPH NODES")
print(analyzer.nodes)

print("\nEDGES")
print(analyzer.edges)

print("\nCONDITIONAL")
print(analyzer.conditional_edges)

print("\nCALLS")
for fn, calls in tool_visitor.calls.items():
    print(fn, "->", calls)