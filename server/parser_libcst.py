import libcst as cst
from libcst import matchers as m
import os
from typing import Optional, Set, Dict, Any, List

def resolve_module_to_file(module_name: str, current_file_path: str, workspace_root: str) -> Optional[str]:
    # Support relative imports
    sub_path = module_name.lstrip(".").replace(".", os.sep)
    if module_name.startswith("."):
        dots_count = len(module_name) - len(module_name.lstrip("."))
        dir_path = os.path.dirname(current_file_path)
        for _ in range(dots_count - 1):
            dir_path = os.path.dirname(dir_path)
        file_path = os.path.join(dir_path, sub_path + ".py")
        if os.path.exists(file_path):
            return file_path
    else:
        # Check relative to current file's folder first
        dir_path = os.path.dirname(current_file_path)
        file_path = os.path.join(dir_path, sub_path + ".py")
        if os.path.exists(file_path):
            return file_path
        # Then check relative to workspace root
        file_path = os.path.join(workspace_root, sub_path + ".py")
        if os.path.exists(file_path):
            return file_path
            
    return None

def extract_callable_name(node: cst.CSTNode) -> Optional[str]:
    if isinstance(node, cst.Name):
        return node.value
    elif isinstance(node, cst.Attribute):
        val_str = extract_callable_name(node.value)
        if val_str:
            return f"{val_str}.{node.attr.value}"
    elif isinstance(node, cst.Call):
        return extract_callable_name(node.func)
    elif isinstance(node, cst.Lambda):
        return "lambda"
    return None

class LangGraphAnalyzer(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)

    def __init__(self, target_var: str = None, current_file_path: Optional[str] = None, visited_files: Optional[Set[str]] = None, workspace_root: Optional[str] = None):
        super().__init__()
        self.functions = []
        self.function_lines = {}
        self.function_returns = {}
        self.function_update_keys = {} 
        self.function_input_keys = {} 
        self.nodes = {}
        self.edges = []
        self.conditional_edges = []
        self.entry_point = None
        self.state_class_name = None
        self.state_schema = {} 
        self.class_schemas = {}
        
        self.target_var = target_var
        self.graph_var_names = set()
        self._potential_builders = set()
        
        self.current_file_path = current_file_path
        self.visited_files = visited_files if visited_files is not None else set()
        self.workspace_root = workspace_root
        self.imports_map = {}
        self.variable_types = {}
        
        self._current_function = None
        self._state_param_name = None
        self._class_stack = []
        self._function_stack = []
        self._local_assignments = {}
        
        if current_file_path:
            self.visited_files.add(os.path.abspath(current_file_path))

    def resolve_callable_name(self, name_str: str) -> str:
        if not name_str:
            return name_str
        
        # 1. Resolve local/nested function names
        if self._function_stack and not name_str.startswith(self._function_stack[-1]):
            nested_candidate = f"{self._function_stack[-1]}.{name_str}"
            if nested_candidate in self.functions:
                return nested_candidate

        # 2. Handle class instances: agent.call_agent -> MyClass.call_agent
        if "." in name_str:
            parts = name_str.split(".")
            prefix = ".".join(parts[:-1])
            method = parts[-1]
            if prefix in self.variable_types:
                resolved_class = self.variable_types[prefix]
                return f"{resolved_class}.{method}"
                
        # 3. Handle __call__ if it's a class reference
        if name_str in self.class_schemas:
            call_method = f"{name_str}.__call__"
            if call_method in self.functions:
                return call_method

        return name_str

    def visit_Assign(self, node: cst.Assign):
        # Detect StateGraph(AgentState)
        if isinstance(node.value, cst.Call) and isinstance(node.value.func, cst.Name) and node.value.func.value == "StateGraph":
            for target in node.targets:
                if isinstance(target.target, cst.Name):
                    var_name = target.target.value
                    self._potential_builders.add(var_name)
                    self.graph_var_names.add(var_name)
                        
        # Detect compile() call
        elif self.target_var and isinstance(node.value, cst.Call) and isinstance(node.value.func, cst.Attribute):
            if node.value.func.attr.value == "compile":
                if isinstance(node.value.func.value, cst.Name):
                    builder_name = node.value.func.value.value
                    for target in node.targets:
                        if isinstance(target.target, cst.Name) and target.target.value == self.target_var:
                            pass

        # Detect assignments for variable types mapping
        if isinstance(node.value, cst.Call):
            class_name = None
            if isinstance(node.value.func, cst.Name):
                class_name = node.value.func.value
            elif isinstance(node.value.func, cst.Attribute) and isinstance(node.value.func.attr, cst.Name):
                class_name = node.value.func.attr.value
            
            if class_name and class_name[0].isupper():
                for target in node.targets:
                    if isinstance(target.target, cst.Name):
                        var_name = target.target.value
                        self.variable_types[var_name] = class_name

        # Detect local assignments inside functions
        if self._current_function:
            for target in node.targets:
                if isinstance(target.target, cst.Name):
                    var_name = target.target.value
                    val = None
                    if isinstance(node.value, cst.SimpleString):
                        val = node.value.evaluated_value
                    elif isinstance(node.value, cst.Name) and node.value.value == "END":
                        val = "__end__"
                    
                    if val is not None:
                        if var_name not in self._local_assignments:
                            self._local_assignments[var_name] = []
                        self._local_assignments[var_name].append(val)

    def visit_Import(self, node: cst.Import):
        for name in node.names:
            alias = name.asname.name.value if name.asname else name.name.value
            self.imports_map[alias] = {
                "module": name.name.value,
                "name": None
            }

    def visit_ImportFrom(self, node: cst.ImportFrom):
        level = len(node.relative)
        if not node.module:
            module_name = "." * level
        else:
            module_name = "." * level + cst.parse_module("").code_for_node(node.module).strip()

        if isinstance(node.names, cst.ImportStar):
            self.imports_map["*"] = {
                "module": module_name,
                "name": "*"
            }
        else:
            for name in node.names:
                alias = name.asname.name.value if name.asname else name.name.value
                self.imports_map[alias] = {
                    "module": module_name,
                    "name": name.name.value
                }

    def visit_ClassDef(self, node: cst.ClassDef):
        class_name = node.name.value
        self._class_stack.append(class_name)
        
        schema = {}
        for item in node.body.body:
            if isinstance(item, cst.SimpleStatementLine):
                for part in item.body:
                    if isinstance(part, cst.AnnAssign) and isinstance(part.target, cst.Name):
                        key = part.target.value
                        anno = "any"
                        if isinstance(part.annotation.annotation, cst.Name):
                            anno = part.annotation.annotation.value
                        elif isinstance(part.annotation.annotation, cst.Subscript):
                            try:
                                anno = cst.parse_module("").code_for_node(part.annotation.annotation)
                            except Exception:
                                anno = "complex_type"
                        schema[key] = anno
        
        is_messages_state = False
        for base in node.bases:
            if isinstance(base.value, cst.Name) and base.value.value == "MessagesState":
                is_messages_state = True
            elif isinstance(base.value, cst.Attribute) and isinstance(base.value.attr, cst.Name) and base.value.attr.value == "MessagesState":
                is_messages_state = True

        if is_messages_state and "messages" not in schema:
            schema["messages"] = "list"

        full_class_name = ".".join(self._class_stack)
        self.class_schemas[full_class_name] = schema

    def leave_ClassDef(self, node: cst.ClassDef):
        self._class_stack.pop()

    def visit_FunctionDef(self, node: cst.FunctionDef):
        func_name = node.name.value
        if self._class_stack:
            func_name = f"{'.'.join(self._class_stack)}.{func_name}"
        if self._function_stack:
            func_name = f"{self._function_stack[-1]}.{node.name.value}"
            
        self._function_stack.append(func_name)
        self.functions.append(func_name)
        
        self.function_returns[func_name] = []
        self.function_update_keys[func_name] = []
        self.function_input_keys[func_name] = []
        self._current_function = func_name
        self._state_param_name = None
        self._local_assignments = {}
        
        if node.params.params:
            first_param = node.params.params[0].name.value
            if first_param in ("self", "cls") and len(node.params.params) > 1:
                self._state_param_name = node.params.params[1].name.value
            else:
                self._state_param_name = first_param

        try:
            pos = self.get_metadata(cst.metadata.PositionProvider, node)
            start_line = pos.start.line
            end_line = pos.end.line
            self.function_lines[func_name] = (start_line, end_line)
        except Exception:
            self.function_lines[func_name] = (1, 1)

        # Parse decorators for graph registration
        for dec in node.decorators:
            dec_expr = dec.decorator
            dec_name = extract_callable_name(dec_expr)
            if dec_name:
                is_register = False
                node_name = func_name
                
                if "add_node" in dec_name or "register_node" in dec_name or dec_name.endswith(".node"):
                    is_register = True
                    
                if is_register:
                    if isinstance(dec_expr, cst.Call) and dec_expr.args:
                        if isinstance(dec_expr.args[0].value, cst.SimpleString):
                            node_name = dec_expr.args[0].value.evaluated_value
                    self.nodes[node_name] = func_name

    def leave_FunctionDef(self, node: cst.FunctionDef):
        self._function_stack.pop()
        self._current_function = self._function_stack[-1] if self._function_stack else None
        self._state_param_name = None
        self._local_assignments = {}

    def visit_Subscript(self, node: cst.Subscript):
        if self._current_function and self._state_param_name:
            if isinstance(node.value, cst.Name) and node.value.value == self._state_param_name:
                if len(node.slice) == 1:
                    slc = node.slice[0].slice
                    if isinstance(slc, cst.Index) and isinstance(slc.value, cst.SimpleString):
                         self.function_input_keys[self._current_function].append(slc.value.evaluated_value)
                    elif isinstance(slc, cst.SimpleString): 
                         self.function_input_keys[self._current_function].append(slc.evaluated_value)

    def visit_Return(self, node: cst.Return):
        if self._current_function and node.value:
            # 1. Simple String/END return
            if isinstance(node.value, cst.SimpleString):
                self.function_returns[self._current_function].append(node.value.evaluated_value)
            elif isinstance(node.value, cst.Name):
                var_name = node.value.value
                if var_name == "END":
                    self.function_returns[self._current_function].append("__end__")
                elif var_name in self._local_assignments:
                    for val in self._local_assignments[var_name]:
                        self.function_returns[self._current_function].append(val)

            # 2. Ternary operator (IfExp)
            elif isinstance(node.value, cst.IfExp):
                for expr in (node.value.body, node.value.orelse):
                    if isinstance(expr, cst.SimpleString):
                        self.function_returns[self._current_function].append(expr.evaluated_value)
                    elif isinstance(expr, cst.Name) and expr.value == "END":
                        self.function_returns[self._current_function].append("__end__")

            # 3. List/Tuple return (for parallel conditional routing)
            elif isinstance(node.value, (cst.List, cst.Tuple)):
                for el in node.value.elements:
                    if isinstance(el.element, cst.SimpleString):
                        self.function_returns[self._current_function].append(el.element.evaluated_value)
                    elif isinstance(el.element, cst.Name) and el.element.value == "END":
                        self.function_returns[self._current_function].append("__end__")

            # 4. Dict return (state updates)
            elif isinstance(node.value, cst.Dict):
                for el in node.value.elements:
                    if isinstance(el, cst.DictElement) and isinstance(el.key, cst.SimpleString):
                        self.function_update_keys[self._current_function].append(el.key.evaluated_value)

    def visit_Call(self, node: cst.Call):
        # Detect state.get("key")
        if self._current_function and self._state_param_name and m.matches(node.func, m.Attribute(value=m.Name(self._state_param_name), attr=m.Name("get"))):
            if node.args and isinstance(node.args[0].value, cst.SimpleString):
                self.function_input_keys[self._current_function].append(node.args[0].value.evaluated_value)

        # Detect StateGraph(AgentState)
        if m.matches(node.func, m.Name("StateGraph")):
            if node.args:
                arg0 = node.args[0].value
                if isinstance(arg0, cst.Name):
                    self.state_class_name = arg0.value

        # Extract workflow method calls
        if isinstance(node.func, cst.Attribute) and isinstance(node.func.value, cst.Name):
            obj_name = node.func.value.value
            method_name = node.func.attr.value

            if obj_name in self.graph_var_names:
                # add_node
                if method_name == "add_node" and len(node.args) >= 2:
                    node_name = None
                    if isinstance(node.args[0].value, cst.SimpleString):
                        node_name = node.args[0].value.evaluated_value

                    raw_fn = extract_callable_name(node.args[1].value)
                    function_name = self.resolve_callable_name(raw_fn) if raw_fn else None

                    if node_name and function_name:
                        self.nodes[node_name] = function_name

                # add_edge
                elif method_name == "add_edge" and len(node.args) >= 2:
                    src = node.args[0].value
                    dst = node.args[1].value
                    src_val = src.evaluated_value if isinstance(src, cst.SimpleString) else ("__start__" if isinstance(src, cst.Name) and src.value == "START" else None)
                    dst_val = dst.evaluated_value if isinstance(dst, cst.SimpleString) else ("__end__" if isinstance(dst, cst.Name) and dst.value == "END" else None)

                    if src_val and dst_val:
                        if src_val == "__start__":
                            self.entry_point = dst_val
                        else:
                            self.edges.append((src_val, dst_val))

                # set_entry_point
                elif method_name == "set_entry_point" and len(node.args) >= 1:
                    arg0 = node.args[0].value
                    if isinstance(arg0, cst.SimpleString):
                        self.entry_point = arg0.evaluated_value

                # add_conditional_edges
                elif method_name == "add_conditional_edges" and len(node.args) >= 2:
                    source = None
                    if isinstance(node.args[0].value, cst.SimpleString):
                        source = node.args[0].value.evaluated_value
                    elif isinstance(node.args[0].value, cst.Name) and node.args[0].value.value == "START":
                        source = "__start__"

                    raw_router = extract_callable_name(node.args[1].value)
                    router_fn = self.resolve_callable_name(raw_router) if raw_router else None

                    mapping = {}
                    if len(node.args) >= 3 and isinstance(node.args[2].value, cst.Dict):
                        for elt in node.args[2].value.elements:
                            if isinstance(elt, cst.DictElement):
                                key = elt.key.evaluated_value if isinstance(elt.key, cst.SimpleString) else ("__end__" if isinstance(elt.key, cst.Name) and elt.key.value == "END" else (elt.key.value if isinstance(elt.key, cst.Name) else None))
                                val = elt.value.evaluated_value if isinstance(elt.value, cst.SimpleString) else ("__end__" if isinstance(elt.value, cst.Name) and elt.value.value == "END" else (elt.value.value if isinstance(elt.value, cst.Name) else None))
                                if key and val:
                                    mapping[key] = val

                    self.conditional_edges.append({
                        "source": source,
                        "router": router_fn,
                        "mapping": mapping
                    })

    def leave_Module(self, original_node: cst.Module):
        # Fallback for builders
        if self.target_var and not self.graph_var_names and self._potential_builders:
            self.graph_var_names.update(self._potential_builders)

        # Store the original class name set by StateGraph instantiation
        original_state_class_name = self.state_class_name

        # Finalize state schema (first pass)
        if self.state_class_name and self.state_class_name in self.class_schemas:
            self.state_schema = self.class_schemas[self.state_class_name]
        else:
            state_classes = [name for name in self.class_schemas.keys() if "State" in name]
            if state_classes:
                self.state_class_name = "AgentState" if "AgentState" in state_classes else state_classes[0]
                self.state_schema = self.class_schemas[self.state_class_name]
            elif self.class_schemas:
                self.state_class_name = list(self.class_schemas.keys())[0]
                self.state_schema = self.class_schemas[self.state_class_name]

        # Resolve recursive imports
        if self.current_file_path:
            workspace_root = self.workspace_root or os.path.dirname(self.current_file_path)
            modules_to_parse = {}
            for alias, imp_info in self.imports_map.items():
                module_name = imp_info["module"]
                if module_name not in modules_to_parse:
                    resolved_file = resolve_module_to_file(module_name, self.current_file_path, workspace_root)
                    if resolved_file and os.path.abspath(resolved_file) not in self.visited_files:
                        modules_to_parse[module_name] = resolved_file

            for module_name, resolved_file in modules_to_parse.items():
                try:
                    with open(resolved_file, "r", encoding="utf8") as f:
                        imported_code = f.read()
                    
                    imported_module = cst.parse_module(imported_code)
                    imported_wrapper = cst.metadata.MetadataWrapper(imported_module)
                    imported_analyzer = LangGraphAnalyzer(
                        current_file_path=resolved_file, 
                        visited_files=self.visited_files,
                        workspace_root=workspace_root
                    )
                    imported_wrapper.visit(imported_analyzer)
                    
                    # Merge imported analyzer results based on import type
                    for alias, imp_info in self.imports_map.items():
                        if imp_info["module"] == module_name:
                            target_name = imp_info["name"]
                            
                            if target_name == "*":
                                for func in imported_analyzer.functions:
                                    self._merge_function_meta(func, func, imported_analyzer)
                                for cls_name, schema in imported_analyzer.class_schemas.items():
                                    self.class_schemas[cls_name] = schema
                                for var_name, type_name in imported_analyzer.variable_types.items():
                                    self.variable_types[var_name] = type_name
                                    
                            elif target_name is None:
                                for func in imported_analyzer.functions:
                                    self._merge_function_meta(func, f"{alias}.{func}", imported_analyzer)
                                for cls_name, schema in imported_analyzer.class_schemas.items():
                                    self.class_schemas[f"{alias}.{cls_name}"] = schema
                                for var_name, type_name in imported_analyzer.variable_types.items():
                                    self.variable_types[f"{alias}.{var_name}"] = type_name
                                    
                            else:
                                for func in imported_analyzer.functions:
                                    if func == target_name:
                                        self._merge_function_meta(func, alias, imported_analyzer)
                                    elif func.startswith(f"{target_name}."):
                                        sub_method = func[len(target_name)+1:]
                                        self._merge_function_meta(func, f"{alias}.{sub_method}", imported_analyzer)
                                
                                if target_name in imported_analyzer.class_schemas:
                                    self.class_schemas[alias] = imported_analyzer.class_schemas[target_name]
                                
                                for var_name, type_name in imported_analyzer.variable_types.items():
                                    if var_name == target_name:
                                        self.variable_types[alias] = type_name
                                
                except Exception as e:
                    print(f"Error recursively parsing {resolved_file}: {e}")

        # Finalize state schema again (second pass, after recursive imports are merged)
        if original_state_class_name:
            self.state_class_name = original_state_class_name
            
        if self.state_class_name and self.state_class_name in self.class_schemas:
            self.state_schema = self.class_schemas[self.state_class_name]
        else:
            state_classes = [name for name in self.class_schemas.keys() if "State" in name]
            if state_classes:
                self.state_class_name = "AgentState" if "AgentState" in state_classes else state_classes[0]
                self.state_schema = self.class_schemas[self.state_class_name]
            elif self.class_schemas:
                self.state_class_name = list(self.class_schemas.keys())[0]
                self.state_schema = self.class_schemas[self.state_class_name]

        # Resolve empty mappings for conditional edges
        for cond in self.conditional_edges:
            if not cond["mapping"] and cond["router"]:
                router = cond["router"]
                if router in self.function_returns:
                    for ret in self.function_returns[router]:
                        if ret:
                            cond["mapping"][ret] = ret

    def _merge_function_meta(self, orig_name: str, alias_name: str, other_analyzer):
        if alias_name not in self.functions:
            self.functions.append(alias_name)
        if orig_name in other_analyzer.function_lines:
            self.function_lines[alias_name] = other_analyzer.function_lines[orig_name]
        if orig_name in other_analyzer.function_returns:
            self.function_returns[alias_name] = other_analyzer.function_returns[orig_name]
        if orig_name in other_analyzer.function_update_keys:
            self.function_update_keys[alias_name] = other_analyzer.function_update_keys[orig_name]
        if orig_name in other_analyzer.function_input_keys:
            self.function_input_keys[alias_name] = other_analyzer.function_input_keys[orig_name]

class SetEntryPointTransformer(cst.CSTTransformer):
    def __init__(self, target_id: str, graph_var: str):
        self.target_id = target_id
        self.graph_var = graph_var
        self.found = False

    def leave_SimpleStatementLine(self, original_node: cst.SimpleStatementLine, updated_node: cst.SimpleStatementLine):
        # Handle set_entry_point
        if m.matches(updated_node, m.SimpleStatementLine(body=[m.Expr(value=m.Call(func=m.Attribute(attr=m.Name("set_entry_point"))))])):
            call = updated_node.body[0].value
            if isinstance(call.func.value, cst.Name) and call.func.value.value == self.graph_var:
                self.found = True
                new_args = [cst.Arg(value=cst.SimpleString(f'"{self.target_id}"'))]
                return updated_node.with_changes(
                    body=[cst.Expr(value=call.with_changes(args=new_args))]
                )
        
        # Handle add_edge(START, ...)
        if m.matches(updated_node, m.SimpleStatementLine(body=[m.Expr(value=m.Call(func=m.Attribute(attr=m.Name("add_edge"))))])):
            call = updated_node.body[0].value
            if isinstance(call.func.value, cst.Name) and call.func.value.value == self.graph_var:
                if len(call.args) >= 2:
                    arg0 = call.args[0].value
                    if (isinstance(arg0, cst.Name) and arg0.value == "START") or (isinstance(arg0, cst.SimpleString) and arg0.evaluated_value == "__start__"):
                        self.found = True
                        new_args = list(call.args)
                        new_args[1] = cst.Arg(value=cst.SimpleString(f'"{self.target_id}"'))
                        return updated_node.with_changes(
                            body=[cst.Expr(value=call.with_changes(args=new_args))]
                        )
        return updated_node

class EnsureStartImportTransformer(cst.CSTTransformer):
    def __init__(self):
        self.found = False
        self.import_inserted = False

    def leave_ImportFrom(self, original_node: cst.ImportFrom, updated_node: cst.ImportFrom):
        # Check if importing from langgraph.graph
        is_langgraph_graph = False
        if isinstance(updated_node.module, cst.Name) and updated_node.module.value == "graph":
            is_langgraph_graph = True
        elif isinstance(updated_node.module, cst.Attribute) and isinstance(updated_node.module.value, cst.Name) and updated_node.module.value.value == "langgraph" and updated_node.module.attr.value == "graph":
            is_langgraph_graph = True

        if is_langgraph_graph and not isinstance(updated_node.names, cst.ImportStar):
            for name in updated_node.names:
                if name.name.value == "START":
                    self.found = True
            
            if not self.found and not self.import_inserted:
                # Add START to the existing import
                new_names = list(updated_node.names)
                
                # We add an ImportAlias for START
                new_alias = cst.ImportAlias(name=cst.Name("START"))
                
                # Check if we need to add a comma to the previous last element
                if new_names:
                    last_name = new_names[-1]
                    new_names[-1] = last_name.with_changes(comma=cst.Comma(whitespace_after=cst.SimpleWhitespace(" ")))
                
                new_names.append(new_alias)
                self.import_inserted = True
                self.found = True # Mark as found since we just inserted it
                return updated_node.with_changes(names=new_names)

        return updated_node

    def leave_Module(self, original_node: cst.Module, updated_node: cst.Module):
        if not self.found and not self.import_inserted:
            # We need to add `from langgraph.graph import START` entirely
            new_import = cst.parse_statement("from langgraph.graph import START\n")
            new_body = list(updated_node.body)
            
            # Find the last import to put it after
            last_import_idx = -1
            for i, stmt in enumerate(new_body):
                if isinstance(stmt, cst.SimpleStatementLine) and any(isinstance(body, (cst.Import, cst.ImportFrom)) for body in stmt.body):
                    last_import_idx = i
            
            if last_import_idx != -1:
                new_body.insert(last_import_idx + 1, new_import)
            else:
                new_body.insert(0, new_import)
                
            self.import_inserted = True
            return updated_node.with_changes(body=new_body)
        return updated_node

def update_entry_point_in_code(source_code: str, target_id: str) -> str:
    module = cst.parse_module(source_code)
    
    analyzer = LangGraphAnalyzer()
    cst.metadata.MetadataWrapper(module).visit(analyzer)
    graph_var = list(analyzer.graph_var_names)[0] if analyzer.graph_var_names else "builder"
    
    transformer = SetEntryPointTransformer(target_id, graph_var)
    new_module = module.visit(transformer)
    
    if not transformer.found:
        # If not found, add it as graph_var.add_edge(START, "target_id")
        entry_stmt = cst.SimpleStatementLine(
            body=[
                cst.Expr(
                    value=cst.Call(
                        func=cst.Attribute(value=cst.Name(graph_var), attr=cst.Name("add_edge")),
                        args=[cst.Arg(value=cst.Name("START")), cst.Arg(value=cst.SimpleString(f'"{target_id}"'))]
                    )
                )
            ]
        )
        
        inserter = GraphCallInserter(entry_stmt, graph_var, "add_node")
        new_module = new_module.visit(inserter)
        
        if not inserter.inserted:
            # Fallback
            final_body = list(new_module.body)
            final_body.append(entry_stmt)
            new_module = new_module.with_changes(body=final_body)

    # Ensure START is imported since we are using it
    import_transformer = EnsureStartImportTransformer()
    final_module = new_module.visit(import_transformer)

    return final_module.code

class RemoveEdgeTransformer(cst.CSTTransformer):
    def __init__(self, src: str, dst: str, condition: str = None):
        self.src = src
        self.dst = dst
        self.condition = condition

    def leave_SimpleStatementLine(self, original_node: cst.SimpleStatementLine, updated_node: cst.SimpleStatementLine):
        # 1. Handle any_graph.add_edge(...)
        if m.matches(updated_node, m.SimpleStatementLine(body=[m.Expr(value=m.Call(func=m.Attribute(attr=m.Name("add_edge"))))])):
            expr = updated_node.body[0]
            call = expr.value
            if len(call.args) >= 2:
                arg0 = call.args[0].value
                arg1 = call.args[1].value
                
                match_src = (isinstance(arg0, cst.SimpleString) and arg0.evaluated_value == self.src) or \
                            (isinstance(arg0, cst.Name) and arg0.value == "START" and self.src == "__start__")
                
                match_dst = False
                if isinstance(arg1, cst.SimpleString) and arg1.evaluated_value == self.dst:
                    match_dst = True
                elif isinstance(arg1, cst.Name) and arg1.value == "END" and self.dst == "__end__":
                    match_dst = True
                
                if match_src and match_dst:
                    return cst.RemoveFromParent()

        # 2. Handle any_graph.add_conditional_edges(...)
        if m.matches(updated_node, m.SimpleStatementLine(body=[m.Expr(value=m.Call(func=m.Attribute(attr=m.Name("add_conditional_edges"))))])):
            expr = updated_node.body[0]
            call = expr.value
            if len(call.args) >= 3:
                # Arg 0: Source node ID
                arg0 = call.args[0].value
                
                match_src = (isinstance(arg0, cst.SimpleString) and arg0.evaluated_value == self.src) or \
                            (isinstance(arg0, cst.Name) and arg0.value == "START" and self.src == "__start__")
                            
                if not match_src:
                    return updated_node
                
                # Arg 2: Mapping dictionary {"label": "target"}
                arg2 = call.args[2].value
                if isinstance(arg2, cst.Dict):
                    new_elements = []
                    for el in arg2.elements:
                        if isinstance(el, cst.DictElement):
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
        # 1. any_graph.add_node("node_id", ...)
        if m.matches(updated_node, m.SimpleStatementLine(body=[m.Expr(value=m.Call(func=m.Attribute(attr=m.Name("add_node"))))])):
            call = updated_node.body[0].value
            if len(call.args) >= 1 and isinstance(call.args[0].value, cst.SimpleString):
                if call.args[0].value.evaluated_value == self.node_id:
                    return cst.RemoveFromParent()

        # 2. any_graph.add_edge("node_id", ...) or any_graph.add_edge(..., "node_id")
        if m.matches(updated_node, m.SimpleStatementLine(body=[m.Expr(value=m.Call(func=m.Attribute(attr=m.Name("add_edge"))))])):
            call = updated_node.body[0].value
            if len(call.args) >= 2:
                arg0 = call.args[0].value
                arg1 = call.args[1].value
                match_src = isinstance(arg0, cst.SimpleString) and arg0.evaluated_value == self.node_id
                match_dst = (isinstance(arg1, cst.SimpleString) and arg1.evaluated_value == self.node_id) or \
                            (isinstance(arg1, cst.Name) and arg1.value == "END" and self.node_id == "__end__")
                if match_src or match_dst:
                    return cst.RemoveFromParent()

        # 3. any_graph.add_conditional_edges("node_id", ...)
        if m.matches(updated_node, m.SimpleStatementLine(body=[m.Expr(value=m.Call(func=m.Attribute(attr=m.Name("add_conditional_edges"))))])):
            call = updated_node.body[0].value
            # Check source node match
            if len(call.args) >= 1 and isinstance(call.args[0].value, cst.SimpleString):
                if call.args[0].value.evaluated_value == self.node_id:
                    return cst.RemoveFromParent()
            
            # Check if mapping dictionary became empty
            if len(call.args) >= 3 and isinstance(call.args[2].value, cst.Dict):
                mapping_dict = call.args[2].value
                if len(mapping_dict.elements) == 0:
                    return cst.RemoveFromParent()

        # 4. any_graph.set_entry_point("node_id")
        if m.matches(updated_node, m.SimpleStatementLine(body=[m.Expr(value=m.Call(func=m.Attribute(attr=m.Name("set_entry_point"))))])):
            call = updated_node.body[0].value
            if len(call.args) >= 1 and isinstance(call.args[0].value, cst.SimpleString):
                if call.args[0].value.evaluated_value == self.node_id:
                    return cst.RemoveFromParent()

        return updated_node

    def leave_DictElement(self, original_node: cst.DictElement, updated_node: cst.DictElement):
        # Remove entry from mapping if it's a target
        match_target = False
        if isinstance(updated_node.value, cst.SimpleString) and updated_node.value.evaluated_value == self.node_id:
            match_target = True
        elif isinstance(updated_node.value, cst.Name) and updated_node.value.value == "END" and self.node_id == "__end__":
            match_target = True
            
        if match_target:
            return cst.RemoveFromParent()
        return updated_node

class RemoveEntryPointTransformer(cst.CSTTransformer):
    def __init__(self):
        self.graph_var = None

    def visit_Assign(self, node: cst.Assign):
        if isinstance(node.value, cst.Call) and isinstance(node.value.func, cst.Name) and node.value.func.value == "StateGraph":
            for target in node.targets:
                if isinstance(target.target, cst.Name):
                    self.graph_var = target.target.value

    def leave_SimpleStatementLine(self, original_node: cst.SimpleStatementLine, updated_node: cst.SimpleStatementLine):
        # Handle set_entry_point
        if m.matches(updated_node, m.SimpleStatementLine(body=[m.Expr(value=m.Call(func=m.Attribute(attr=m.Name("set_entry_point"))))])):
            # Verify it's on the graph variable if we know it
            call = updated_node.body[0].value
            if self.graph_var and isinstance(call.func.value, cst.Name) and call.func.value.value != self.graph_var:
                return updated_node
            return cst.RemoveFromParent()
        
        # Handle add_edge(START, ...)
        if m.matches(updated_node, m.SimpleStatementLine(body=[m.Expr(value=m.Call(func=m.Attribute(attr=m.Name("add_edge"))))])):
            call = updated_node.body[0].value
            if self.graph_var and isinstance(call.func.value, cst.Name) and call.func.value.value != self.graph_var:
                return updated_node
                
            if len(call.args) >= 2:
                arg0 = call.args[0].value
                if isinstance(arg0, cst.Name) and arg0.value == "START":
                    return cst.RemoveFromParent()
                if isinstance(arg0, cst.SimpleString) and arg0.evaluated_value == "__start__":
                    return cst.RemoveFromParent()

        return updated_node

def add_edge_to_code(source_code: str, src: str, dst: str) -> str:
    module = cst.parse_module(source_code)
    
    analyzer = LangGraphAnalyzer()
    wrapper = cst.metadata.MetadataWrapper(module)
    wrapper.visit(analyzer)
    
    graph_var = list(analyzer.graph_var_names)[0] if analyzer.graph_var_names else "builder"
    
    # Create graph_var.add_edge("src", "dst" or END)
    dst_node = cst.Name("END") if dst == "__end__" else cst.SimpleString(f'"{dst}"')
    
    edge_stmt = cst.SimpleStatementLine(
        body=[
            cst.Expr(
                value=cst.Call(
                    func=cst.Attribute(
                        value=cst.Name(graph_var),
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

    inserter = GraphCallInserter(edge_stmt, graph_var, "add_edge")
    final_module = module.visit(inserter)
    
    if not inserter.inserted:
        final_body = list(final_module.body)
        final_body.append(edge_stmt)
        final_module = final_module.with_changes(body=final_body)

    return final_module.code

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
        # Handle any_graph.add_node("old_id", ...)
        if m.matches(original_node.func, m.Attribute(attr=m.Name("add_node"))):
            if len(updated_node.args) >= 1:
                arg0 = updated_node.args[0].value
                if isinstance(arg0, cst.SimpleString) and arg0.evaluated_value == self.old_id:
                    new_arg = updated_node.args[0].with_changes(
                        value=cst.SimpleString(f'"{self.new_id}"')
                    )
                    new_args = list(updated_node.args)
                    new_args[0] = new_arg
                    return updated_node.with_changes(args=new_args)

        # Handle any_graph.add_edge("old_id", ...) or any_graph.add_edge(..., "old_id")
        if m.matches(original_node.func, m.Attribute(attr=m.Name("add_edge"))):
            new_args = list(updated_node.args)
            changed = False
            for i in range(min(2, len(new_args))):
                arg = new_args[i].value
                if isinstance(arg, cst.SimpleString) and arg.evaluated_value == self.old_id:
                    new_args[i] = new_args[i].with_changes(value=cst.SimpleString(f'"{self.new_id}"'))
                    changed = True
            if changed:
                return updated_node.with_changes(args=new_args)

        # Handle any_graph.add_conditional_edges("old_id", ...)
        if m.matches(original_node.func, m.Attribute(attr=m.Name("add_conditional_edges"))):
            new_args = list(updated_node.args)
            changed = False
            if len(new_args) >= 1:
                arg = new_args[0].value
                if isinstance(arg, cst.SimpleString) and arg.evaluated_value == self.old_id:
                    new_args[0] = new_args[0].with_changes(value=cst.SimpleString(f'"{self.new_id}"'))
                    changed = True
            if changed:
                return updated_node.with_changes(args=new_args)

        # Handle any_graph.set_entry_point("old_id")
        if m.matches(original_node.func, m.Attribute(attr=m.Name("set_entry_point"))):
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

class GraphCallInserter(cst.CSTTransformer):
    def __init__(self, stmt_to_insert: cst.SimpleStatementLine, graph_var: str, method_to_follow: str):
        self.stmt_to_insert = stmt_to_insert
        self.graph_var = graph_var
        self.method_to_follow = method_to_follow
        self.inserted = False

    def leave_IndentedBlock(self, original_node: cst.IndentedBlock, updated_node: cst.IndentedBlock):
        if not self.inserted:
            return self._insert_in_body(updated_node)
        return updated_node

    def leave_Module(self, original_node: cst.Module, updated_node: cst.Module):
        if not self.inserted:
            return self._insert_in_body(updated_node)
        return updated_node

    def _insert_in_body(self, node):
        new_body = []
        last_idx = -1
        
        for i, stmt in enumerate(node.body):
            if m.matches(stmt, m.SimpleStatementLine(body=[m.Expr(value=m.Call(func=m.Attribute(value=m.Name(self.graph_var), attr=m.Name(self.method_to_follow))))])):
                last_idx = i
            elif last_idx == -1 and m.matches(stmt, m.SimpleStatementLine(body=[m.Assign(targets=[m.AssignTarget(target=m.Name(self.graph_var))])])):
                last_idx = i

        if last_idx != -1:
            new_body = list(node.body)
            new_body.insert(last_idx + 1, self.stmt_to_insert)
            self.inserted = True
            return node.with_changes(body=new_body)
        return node

def add_node_to_code(source_code: str, node_name: str, only_add_call: bool = False) -> str:
    module = cst.parse_module(source_code)
    
    analyzer = LangGraphAnalyzer()
    wrapper = cst.metadata.MetadataWrapper(module)
    wrapper.visit(analyzer)
    
    state_name = analyzer.state_class_name or "AgentState"
    graph_var = list(analyzer.graph_var_names)[0] if analyzer.graph_var_names else "builder"

    call_stmt = cst.SimpleStatementLine(
        body=[
            cst.Expr(
                value=cst.Call(
                    func=cst.Attribute(
                        value=cst.Name(graph_var),
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

    if not only_add_call:
        func_def = cst.FunctionDef(
            name=cst.Name(node_name),
            params=cst.Parameters(
                params=[
                    cst.Param(
                        name=cst.Name("state"),
                        annotation=cst.Annotation(annotation=cst.Name(state_name))
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
        
        new_body = list(module.body)
        
        # We will inject the function definition at the module level.
        # To find the best place, we can put it right before the function that defines the graph, 
        # or just before the graph assignment if global.
        insert_idx = -1
        for i, stmt in enumerate(new_body):
            # Look for the graph assignment globally
            if m.matches(stmt, m.SimpleStatementLine(body=[m.Assign(targets=[m.AssignTarget(target=m.Name(graph_var))])])):
                insert_idx = i
                break
            # Or look for a function that contains it
            if m.matches(stmt, m.FunctionDef()) and any("StateGraph" in cst.parse_module("").code_for_node(stmt) for _ in [1]):
                # Simple heuristic
                insert_idx = i
                break

        if insert_idx != -1:
            new_body.insert(insert_idx, func_def)
        else:
            new_body.append(func_def)

        new_module = module.with_changes(body=new_body)
    else:
        new_module = module

    # Now inject the add_node call inside the correct block
    inserter = GraphCallInserter(call_stmt, graph_var, "add_node")
    final_module = new_module.visit(inserter)
    
    if not inserter.inserted:
        final_body = list(final_module.body)
        final_body.append(call_stmt)
        final_module = final_module.with_changes(body=final_body)

    return final_module.code

class MergeConditionalEdgeTransformer(cst.CSTTransformer):
    def __init__(self, graph_var: str, source: str, router_fn: str, new_mapping: dict):
        self.graph_var = graph_var
        self.source = source
        self.router_fn = router_fn
        self.new_mapping = new_mapping
        self.merged = False

    def leave_SimpleStatementLine(self, original_node: cst.SimpleStatementLine, updated_node: cst.SimpleStatementLine):
        if m.matches(updated_node, m.SimpleStatementLine(body=[m.Expr(value=m.Call(func=m.Attribute(value=m.Name(self.graph_var), attr=m.Name("add_conditional_edges"))))])):
            expr = updated_node.body[0]
            call = expr.value
            if len(call.args) >= 3:
                arg0 = call.args[0].value
                arg1 = call.args[1].value
                arg2 = call.args[2].value
                
                match_src = False
                if isinstance(arg0, cst.SimpleString) and arg0.evaluated_value == self.source:
                    match_src = True
                elif isinstance(arg0, cst.Name) and arg0.value == "START" and self.source == "__start__":
                    match_src = True
                
                router_code = cst.parse_module("").code_for_node(arg1).strip()
                if match_src and router_code == self.router_fn:
                    if isinstance(arg2, cst.Dict):
                        existing_items = []
                        for el in arg2.elements:
                            if isinstance(el, cst.DictElement):
                                k_val = el.key.evaluated_value if isinstance(el.key, cst.SimpleString) else cst.parse_module("").code_for_node(el.key).strip()
                                
                                if isinstance(el.value, cst.SimpleString):
                                    v_val = el.value.evaluated_value
                                elif isinstance(el.value, cst.Name) and el.value.value == "END":
                                    v_val = "__end__"
                                else:
                                    v_val = cst.parse_module("").code_for_node(el.value).strip()
                                
                                existing_items.append({
                                    "key": k_val,
                                    "target": v_val
                                })
                        
                        updated_existing_indices = set()
                        new_entries_to_add = []
                        
                        for new_key, new_target in self.new_mapping.items():
                            matched = False
                            # 1. Match by key first
                            for idx, item in enumerate(existing_items):
                                if item["key"] == new_key:
                                    item["target"] = new_target
                                    updated_existing_indices.add(idx)
                                    matched = True
                                    break
                            
                            if matched:
                                continue
                                
                            # 2. Match by target to handle key renames/updates
                            for idx, item in enumerate(existing_items):
                                if idx not in updated_existing_indices and item["target"] == new_target:
                                    item["key"] = new_key
                                    updated_existing_indices.add(idx)
                                    matched = True
                                    break
                                    
                            if not matched:
                                new_entries_to_add.append((new_key, new_target))
                                
                        existing_mappings = []
                        for idx, item in enumerate(existing_items):
                            k = item["key"]
                            v = item["target"]
                            
                            k_code = k if (k.startswith('"') or k.startswith("'")) else f'"{k}"'
                            if v == "__end__" or v == "END":
                                v_code = "END"
                            elif v.startswith('"') or v.startswith("'"):
                                v_code = v
                            else:
                                v_code = f'"{v}"'
                            existing_mappings.append((k_code, v_code))
                            
                        for new_key, new_target in new_entries_to_add:
                            k_code = f'"{new_key}"'
                            v_code = "END" if new_target == "__end__" else f'"{new_target}"'
                            existing_mappings.append((k_code, v_code))
                        
                        self.merged = True
                        dict_str = "{\n"
                        for k, v in existing_mappings:
                            dict_str += f'    {k}: {v},\n'
                        dict_str += "}"
                        updated_dict = cst.parse_expression(dict_str)
                        
                        updated_args = list(call.args)
                        updated_args[2] = call.args[2].with_changes(value=updated_dict)
                        updated_call = call.with_changes(args=updated_args)
                        return updated_node.with_changes(body=[cst.Expr(value=updated_call)])
        return updated_node

def add_conditional_edge_to_code(source_code: str, source: str, router_fn: str, mapping: dict) -> str:
    module = cst.parse_module(source_code)
    
    analyzer = LangGraphAnalyzer()
    wrapper = cst.metadata.MetadataWrapper(module)
    wrapper.visit(analyzer)
    
    state_name = analyzer.state_class_name or "AgentState"
    graph_var = list(analyzer.graph_var_names)[0] if analyzer.graph_var_names else "builder"

    new_body = list(module.body)
    
    # 1. Check if router_fn exists, if not and it's a valid identifier, add a skeleton
    if router_fn.isidentifier() and router_fn not in analyzer.functions:
        first_key = list(mapping.keys())[0] if mapping else "next"
        router_def = cst.FunctionDef(
            name=cst.Name(router_fn),
            params=cst.Parameters(
                params=[
                    cst.Param(
                        name=cst.Name("state"),
                        annotation=cst.Annotation(annotation=cst.Name(state_name))
                    )
                ]
            ),
            body=cst.IndentedBlock(
                body=[
                    cst.SimpleStatementLine(
                        body=[
                            cst.Return(
                                value=cst.SimpleString(f'"{first_key}"')
                            )
                        ]
                    )
                ]
            ),
            leading_lines=[cst.EmptyLine(indent=False), cst.EmptyLine(indent=False)]
        )
        
        insert_idx = -1
        for i, stmt in enumerate(new_body):
            if m.matches(stmt, m.SimpleStatementLine(body=[m.Assign(targets=[m.AssignTarget(target=m.Name(graph_var))])])):
                insert_idx = i
                break
            if m.matches(stmt, m.FunctionDef()) and any("StateGraph" in cst.parse_module("").code_for_node(stmt) for _ in [1]):
                insert_idx = i
                break
        
        if insert_idx != -1:
            new_body.insert(insert_idx, router_def)
        else:
            new_body.append(router_def)

    new_module = module.with_changes(body=new_body)

    # 2. Try to merge into an existing add_conditional_edges call first
    merger = MergeConditionalEdgeTransformer(graph_var, source, router_fn, mapping)
    final_module = new_module.visit(merger)
    
    if merger.merged:
        return final_module.code

    # 3. Create mapping dictionary and new add_conditional_edges call
    dict_str = "{\n"
    for key, val in mapping.items():
        val_str = "END" if val == "__end__" else f'"{val}"'
        dict_str += f'    "{key}": {val_str},\n'
    dict_str += "}"
    mapping_dict = cst.parse_expression(dict_str)
    
    cond_stmt = cst.SimpleStatementLine(
        body=[
            cst.Expr(
                value=cst.Call(
                    func=cst.Attribute(
                        value=cst.Name(graph_var),
                        attr=cst.Name("add_conditional_edges")
                    ),
                    args=[
                        cst.Arg(cst.SimpleString(f'"{source}"')),
                        cst.Arg(cst.parse_expression(router_fn)),
                        cst.Arg(mapping_dict)
                    ]
                )
            )
        ]
    )

    # 4. Insert the new add_conditional_edges call
    inserter = GraphCallInserter(cond_stmt, graph_var, "add_conditional_edges")
    final_module = new_module.visit(inserter)
    
    if not inserter.inserted:
        # Fallback to appending
        final_body = list(final_module.body)
        final_body.append(cond_stmt)
        final_module = final_module.with_changes(body=final_body)

    return final_module.code

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