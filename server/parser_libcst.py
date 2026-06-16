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
        self.entry_point = None

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

                src_val = None
                dst_val = None

                if isinstance(src, cst.SimpleString):
                    src_val = src.evaluated_value

                if isinstance(dst, cst.SimpleString):
                    dst_val = dst.evaluated_value
                elif isinstance(dst, cst.Name) and dst.value == "END":
                    dst_val = "__end__"

                if src_val and dst_val:
                    self.edges.append((src_val, dst_val))

        # ----------------------------------
        # builder.set_entry_point(...)
        # ----------------------------------

        if m.matches(
            node.func,
            m.Attribute(
                value=m.Name("builder"),
                attr=m.Name("set_entry_point")
            )
        ):
            if len(node.args) >= 1:
                arg0 = node.args[0].value
                if isinstance(arg0, cst.SimpleString):
                    self.entry_point = arg0.evaluated_value
    
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

class SetEntryPointTransformer(cst.CSTTransformer):
    def __init__(self, target_id: str):
        self.target_id = target_id
        self.found = False

    def leave_SimpleStatementLine(self, original_node: cst.SimpleStatementLine, updated_node: cst.SimpleStatementLine):
        if m.matches(updated_node, m.SimpleStatementLine(body=[m.Expr(value=m.Call(func=m.Attribute(value=m.Name("builder"), attr=m.Name("set_entry_point"))))])):
            self.found = True
            call = updated_node.body[0].value
            new_args = [cst.Arg(value=cst.SimpleString(f'"{self.target_id}"'))]
            return updated_node.with_changes(
                body=[cst.Expr(value=call.with_changes(args=new_args))]
            )
        return updated_node

def update_entry_point_in_code(source_code: str, target_id: str) -> str:
    module = cst.parse_module(source_code)
    transformer = SetEntryPointTransformer(target_id)
    new_module = module.visit(transformer)
    
    if transformer.found:
        return new_module.code
    
    # If not found, add it
    new_body = list(new_module.body)
    entry_stmt = cst.SimpleStatementLine(
        body=[
            cst.Expr(
                value=cst.Call(
                    func=cst.Attribute(value=cst.Name("builder"), attr=cst.Name("set_entry_point")),
                    args=[cst.Arg(value=cst.SimpleString(f'"{target_id}"'))]
                )
            )
        ]
    )
    
    # Place it after builder initialization or after last add_node
    insert_idx = -1
    for i, stmt in enumerate(new_body):
        if m.matches(stmt, m.SimpleStatementLine(body=[m.Expr(value=m.Call(func=m.Attribute(value=m.Name("builder"), attr=m.Name("add_node"))))])):
            insert_idx = i
        elif insert_idx == -1 and m.matches(stmt, m.SimpleStatementLine(body=[m.Assign(targets=[m.AssignTarget(target=m.Name("builder"))])])):
             insert_idx = i
             
    if insert_idx != -1:
        new_body.insert(insert_idx + 1, entry_stmt)
    else:
        new_body.append(entry_stmt)
        
    return new_module.with_changes(body=new_body).code

class RemoveEdgeTransformer(cst.CSTTransformer):
    def __init__(self, src: str, dst: str, condition: str = None):
        self.src = src
        self.dst = dst
        self.condition = condition

    def leave_SimpleStatementLine(self, original_node: cst.SimpleStatementLine, updated_node: cst.SimpleStatementLine):
        # 1. Handle builder.add_edge(...)
        if m.matches(updated_node, m.SimpleStatementLine(body=[m.Expr(value=m.Call(func=m.Attribute(value=m.Name("builder"), attr=m.Name("add_edge"))))])):
            expr = updated_node.body[0]
            call = expr.value
            if len(call.args) >= 2:
                arg0 = call.args[0].value
                arg1 = call.args[1].value
                
                match_src = isinstance(arg0, cst.SimpleString) and arg0.evaluated_value == self.src
                
                match_dst = False
                if isinstance(arg1, cst.SimpleString) and arg1.evaluated_value == self.dst:
                    match_dst = True
                elif isinstance(arg1, cst.Name) and arg1.value == "END" and self.dst == "__end__":
                    match_dst = True
                
                if match_src and match_dst:
                    return cst.RemoveFromParent()

        # 2. Handle builder.add_conditional_edges(...)
        if m.matches(updated_node, m.SimpleStatementLine(body=[m.Expr(value=m.Call(func=m.Attribute(value=m.Name("builder"), attr=m.Name("add_conditional_edges"))))])):
            expr = updated_node.body[0]
            call = expr.value
            if len(call.args) >= 3:
                # Arg 0: Source node ID
                arg0 = call.args[0].value
                if not (isinstance(arg0, cst.SimpleString) and arg0.evaluated_value == self.src):
                    return updated_node
                
                # Arg 2: Mapping dictionary {"label": "target"}
                arg2 = call.args[2].value
                if isinstance(arg2, cst.Dict):
                    new_elements = []
                    for el in arg2.elements:
                        if isinstance(el, cst.DictElement):
                            # Usually keys are condition strings, values are target node strings
                            # We want to remove the entry where key == condition OR value == dst
                            # (If condition is provided, use that for precision)
                            key_match = False
                            if self.condition and isinstance(el.key, cst.SimpleString) and el.key.evaluated_value == self.condition:
                                key_match = True
                            
                            val_match = False
                            if isinstance(el.value, cst.SimpleString) and el.value.evaluated_value == self.dst:
                                val_match = True
                            elif isinstance(el.value, cst.Name) and el.value.value == "END" and self.dst == "__end__":
                                val_match = True
                                
                            if key_match or (not self.condition and val_match):
                                # Skip this element (delete it)
                                continue
                        new_elements.append(el)
                    
                    if not new_elements:
                        # Dictionary is now empty, remove the whole add_conditional_edges call
                        return cst.RemoveFromParent()
                    
                    # Update the call with the new dictionary
                    new_dict = arg2.with_changes(elements=new_elements)
                    new_args = list(call.args)
                    new_args[2] = call.args[2].with_changes(value=new_dict)
                    return updated_node.with_changes(
                        body=[cst.Expr(value=call.with_changes(args=new_args))]
                    )

        return updated_node

class RemoveNodeTransformer(cst.CSTTransformer):
    def __init__(self, node_id: str):
        self.node_id = node_id

    def leave_SimpleStatementLine(self, original_node: cst.SimpleStatementLine, updated_node: cst.SimpleStatementLine):
        # 1. builder.add_node("node_id", ...)
        if m.matches(updated_node, m.SimpleStatementLine(body=[m.Expr(value=m.Call(func=m.Attribute(value=m.Name("builder"), attr=m.Name("add_node"))))])):
            call = updated_node.body[0].value
            if len(call.args) >= 1 and isinstance(call.args[0].value, cst.SimpleString):
                if call.args[0].value.evaluated_value == self.node_id:
                    return cst.RemoveFromParent()

        # 2. builder.add_edge("node_id", ...) or builder.add_edge(..., "node_id")
        if m.matches(updated_node, m.SimpleStatementLine(body=[m.Expr(value=m.Call(func=m.Attribute(value=m.Name("builder"), attr=m.Name("add_edge"))))])):
            call = updated_node.body[0].value
            if len(call.args) >= 2:
                arg0 = call.args[0].value
                arg1 = call.args[1].value
                match_src = isinstance(arg0, cst.SimpleString) and arg0.evaluated_value == self.node_id
                match_dst = (isinstance(arg1, cst.SimpleString) and arg1.evaluated_value == self.node_id) or \
                            (isinstance(arg1, cst.Name) and arg1.value == "END" and self.node_id == "__end__")
                if match_src or match_dst:
                    return cst.RemoveFromParent()

        # 3. builder.add_conditional_edges("node_id", ...)
        if m.matches(updated_node, m.SimpleStatementLine(body=[m.Expr(value=m.Call(func=m.Attribute(value=m.Name("builder"), attr=m.Name("add_conditional_edges"))))])):
            call = updated_node.body[0].value
            if len(call.args) >= 1 and isinstance(call.args[0].value, cst.SimpleString):
                if call.args[0].value.evaluated_value == self.node_id:
                    return cst.RemoveFromParent()

        # 4. builder.set_entry_point("node_id")
        if m.matches(updated_node, m.SimpleStatementLine(body=[m.Expr(value=m.Call(func=m.Attribute(value=m.Name("builder"), attr=m.Name("set_entry_point"))))])):
            call = updated_node.body[0].value
            if len(call.args) >= 1 and isinstance(call.args[0].value, cst.SimpleString):
                if call.args[0].value.evaluated_value == self.node_id:
                    return cst.RemoveFromParent()

        return updated_node

    def leave_DictElement(self, original_node: cst.DictElement, updated_node: cst.DictElement):
        # Remove entry from mapping if it's a target
        if isinstance(updated_node.value, cst.SimpleString) and updated_node.value.evaluated_value == self.node_id:
            return cst.RemoveFromParent()
        return updated_node

class RemoveEntryPointTransformer(cst.CSTTransformer):
    def leave_SimpleStatementLine(self, original_node: cst.SimpleStatementLine, updated_node: cst.SimpleStatementLine):
        if m.matches(updated_node, m.SimpleStatementLine(body=[m.Expr(value=m.Call(func=m.Attribute(value=m.Name("builder"), attr=m.Name("set_entry_point"))))])):
            return cst.RemoveFromParent()
        return updated_node

def add_edge_to_code(source_code: str, src: str, dst: str) -> str:
    module = cst.parse_module(source_code)
    
    # Create builder.add_edge("src", "dst" or END)
    dst_node = cst.Name("END") if dst == "__end__" else cst.SimpleString(f'"{dst}"')
    
    edge_stmt = cst.SimpleStatementLine(
        body=[
            cst.Expr(
                value=cst.Call(
                    func=cst.Attribute(
                        value=cst.Name("builder"),
                        attr=cst.Name("add_edge")
                    ),
                    args=[
                        cst.Arg(cst.SimpleString(f'"{src}"')),
                        cst.Arg(dst_node)
                    ]
                )
            )
        ]
    )

    new_body = list(module.body)
    last_edge_idx = -1
    builder_assign_idx = -1

    for i, stmt in enumerate(new_body):
        if m.matches(stmt, m.SimpleStatementLine(body=[m.Expr(value=m.Call(func=m.Attribute(value=m.Name("builder"), attr=m.Name("add_edge"))))])):
            last_edge_idx = i
        if m.matches(stmt, m.SimpleStatementLine(body=[m.Assign(targets=[m.AssignTarget(target=m.Name("builder"))])])):
            builder_assign_idx = i

    if last_edge_idx != -1:
        new_body.insert(last_edge_idx + 1, edge_stmt)
    elif builder_assign_idx != -1:
        # If no edges yet, put it after builder.add_node calls or just after builder init
        # Finding last add_node would be better
        last_node_idx = -1
        for i, stmt in enumerate(new_body):
             if m.matches(stmt, m.SimpleStatementLine(body=[m.Call(func=m.Attribute(value=m.Name("builder"), attr=m.Name("add_node")))])):
                 last_node_idx = i
        
        if last_node_idx != -1:
            new_body.insert(last_node_idx + 1, edge_stmt)
        else:
            new_body.insert(builder_assign_idx + 1, edge_stmt)
    else:
        new_body.append(edge_stmt)

    return module.with_changes(body=new_body).code

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
        if m.matches(stmt, m.SimpleStatementLine(body=[m.Expr(value=m.Call(func=m.Attribute(value=m.Name("builder"), attr=m.Name("add_node"))))])):
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