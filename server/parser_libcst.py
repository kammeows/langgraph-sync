import libcst as cst
from libcst import matchers as m


class LangGraphAnalyzer(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)

    def __init__(self):
        super().__init__()
        self.functions = []
        self.function_lines = {} # New: store {func_name: (start_line, end_line)}
        self.nodes = {}
        self.edges = []
        self.conditional_edges = []

    # ----------------------------------
    # Collect all function defs
    # ----------------------------------

    def visit_FunctionDef(self, node: cst.FunctionDef):
        func_name = node.name.value
        self.functions.append(func_name)
        
        # Capture line numbers using metadata
        pos = self.get_metadata(cst.metadata.PositionProvider, node)
        start_line = pos.start.line
        end_line = pos.end.line
        self.function_lines[func_name] = (start_line, end_line)

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

class RenameNodeTransformer(cst.CSTTransformer):
    def __init__(self, old_id: str, new_id: str):
        self.old_id = old_id
        self.new_id = new_id

    def leave_Call(self, original_node: cst.Call, updated_node: cst.Call):
        # Handle builder.add_node("old_id", ...)
        if m.matches(original_node.func, m.Attribute(value=m.Name("builder"), attr=m.Name("add_node"))):
            if len(updated_node.args) >= 1:
                arg0 = updated_node.args[0].value
                if isinstance(arg0, cst.SimpleString) and arg0.evaluated_value == self.old_id:
                    new_arg = updated_node.args[0].with_changes(
                        value=cst.SimpleString(f'"{self.new_id}"')
                    )
                    new_args = list(updated_node.args)
                    new_args[0] = new_arg
                    return updated_node.with_changes(args=new_args)

        # Handle builder.add_edge("old_id", ...) or builder.add_edge(..., "old_id")
        if m.matches(original_node.func, m.Attribute(value=m.Name("builder"), attr=m.Name("add_edge"))):
            new_args = list(updated_node.args)
            changed = False
            for i in range(min(2, len(new_args))):
                arg = new_args[i].value
                if isinstance(arg, cst.SimpleString) and arg.evaluated_value == self.old_id:
                    new_args[i] = new_args[i].with_changes(value=cst.SimpleString(f'"{self.new_id}"'))
                    changed = True
            if changed:
                return updated_node.with_changes(args=new_args)

        # Handle builder.add_conditional_edges("old_id", ...)
        if m.matches(original_node.func, m.Attribute(value=m.Name("builder"), attr=m.Name("add_conditional_edges"))):
            new_args = list(updated_node.args)
            changed = False
            if len(new_args) >= 1:
                arg = new_args[0].value
                if isinstance(arg, cst.SimpleString) and arg.evaluated_value == self.old_id:
                    new_args[0] = new_args[0].with_changes(value=cst.SimpleString(f'"{self.new_id}"'))
                    changed = True
            if changed:
                return updated_node.with_changes(args=new_args)

        # Handle builder.set_entry_point("old_id")
        if m.matches(original_node.func, m.Attribute(value=m.Name("builder"), attr=m.Name("set_entry_point"))):
            if len(updated_node.args) >= 1:
                arg = updated_node.args[0].value
                if isinstance(arg, cst.SimpleString) and arg.evaluated_value == self.old_id:
                    new_arg = updated_node.args[0].with_changes(
                        value=cst.SimpleString(f'"{self.new_id}"')
                    )
                    new_args = list(updated_node.args)
                    new_args[0] = new_arg
                    return updated_node.with_changes(args=new_args)

        return updated_node

    def leave_DictElement(self, original_node: cst.DictElement, updated_node: cst.DictElement):
        # Handle target node in mapping dict: {"condition": "old_id"}
        if isinstance(updated_node.value, cst.SimpleString) and updated_node.value.evaluated_value == self.old_id:
            return updated_node.with_changes(value=cst.SimpleString(f'"{self.new_id}"'))
        return updated_node

def add_node_to_code(source_code: str, node_name: str) -> str:
    module = cst.parse_module(source_code)
    
    # 1. Create the function definition
    # def node_name(state: AgentState):
    #     return {}
    func_def = cst.FunctionDef(
        name=cst.Name(node_name),
        params=cst.Parameters(
            params=[
                cst.Param(
                    name=cst.Name("state"),
                    annotation=cst.Annotation(annotation=cst.Name("AgentState"))
                )
            ]
        ),
        body=cst.IndentedBlock(
            body=[
                cst.SimpleStatementLine(
                    body=[
                        cst.Return(
                            value=cst.Dict(elements=[])
                        )
                    ]
                )
            ]
        ),
        leading_lines=[cst.EmptyLine(indent=False), cst.EmptyLine(indent=False)]
    )
    
    # 2. Create the builder.add_node call
    # builder.add_node("node_name", node_name)
    call_stmt = cst.SimpleStatementLine(
        body=[
            cst.Expr(
                value=cst.Call(
                    func=cst.Attribute(
                        value=cst.Name("builder"),
                        attr=cst.Name("add_node")
                    ),
                    args=[
                        cst.Arg(cst.SimpleString(f'"{node_name}"')),
                        cst.Arg(cst.Name(node_name))
                    ]
                )
            )
        ]
    )

    new_body = list(module.body)
    
    # Find insertion points
    builder_assign_idx = -1
    last_add_node_idx = -1
    
    for i, stmt in enumerate(new_body):
        # Match builder = StateGraph(...)
        if m.matches(stmt, m.SimpleStatementLine(body=[m.Assign(targets=[m.AssignTarget(target=m.Name("builder"))])])):
            builder_assign_idx = i
        
        # Match builder.add_node(...)
        if m.matches(stmt, m.SimpleStatementLine(body=[m.Call(func=m.Attribute(value=m.Name("builder"), attr=m.Name("add_node")))])):
            last_add_node_idx = i

    if builder_assign_idx != -1:
        # Insert function before builder assignment
        new_body.insert(builder_assign_idx, func_def)
        
        # Adjust indices as body changed
        if last_add_node_idx != -1:
            shifted_last_idx = last_add_node_idx + 1
            new_body.insert(shifted_last_idx + 1, call_stmt)
        else:
            new_body.insert(builder_assign_idx + 2, call_stmt)
    else:
        new_body.append(func_def)
        new_body.append(call_stmt)
        
    return module.with_changes(body=new_body).code

if __name__ == "__main__":
    import os
    
    # Try to find agent.py in parent or current dir for testing
    agent_path = "agent.py"
    if not os.path.exists(agent_path):
        agent_path = os.path.join("..", "agent.py")
        
    if os.path.exists(agent_path):
        with open(agent_path, "r", encoding="utf8") as f:
            source = f.read()

        module = cst.parse_module(source)
        wrapper = cst.metadata.MetadataWrapper(module)

        analyzer = LangGraphAnalyzer()
        wrapper.visit(analyzer)

        tool_visitor = ToolCallVisitor()
        module.visit(tool_visitor)

        print("\nFUNCTIONS (with lines)")
        for func in analyzer.functions:
            print(f"{func}: {analyzer.function_lines.get(func)}")

        print("\nGRAPH NODES")
        print(analyzer.nodes)

        print("\nEDGES")
        print(analyzer.edges)

        print("\nCONDITIONAL")
        print(analyzer.conditional_edges)

        print("\nCALLS")
        for fn, calls in tool_visitor.calls.items():
            print(fn, "->", calls)
    else:
        print("agent.py not found for standalone test.")