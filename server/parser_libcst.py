import libcst as cst
from libcst import matchers as m
import os
from typing import Optional, Set, Dict, Any, List, Tuple

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

def resolve_node_values(node: cst.CSTNode) -> List[str]:
    if isinstance(node, cst.SimpleString):
        return [node.evaluated_value]
    elif isinstance(node, cst.Name):
        if node.value == "START":
            return ["__start__"]
        elif node.value == "END":
            return ["__end__"]
        else:
            return [node.value]
    elif isinstance(node, (cst.List, cst.Tuple)):
        res = []
        for el in node.elements:
            res.extend(resolve_node_values(el.value))
        return res
    return []

def node_contains_value(node: cst.CSTNode, target_val: str) -> bool:
    if isinstance(node, cst.SimpleString):
        return node.evaluated_value == target_val
    if isinstance(node, cst.Name):
        if target_val == "__start__" and node.value == "START":
            return True
        if target_val == "__end__" and node.value == "END":
            return True
        return node.value == target_val
    if isinstance(node, (cst.List, cst.Tuple)):
        return any(node_contains_value(el.value, target_val) for el in node.elements)
    return False

def remove_value_from_node(node: cst.CSTNode, target_val: str) -> Optional[cst.CSTNode]:
    if isinstance(node, cst.SimpleString) and node.evaluated_value == target_val:
        return None
    if isinstance(node, cst.Name):
        if target_val == "__start__" and node.value == "START":
            return None
        if target_val == "__end__" and node.value == "END":
            return None
        if node.value == target_val:
            return None
    if isinstance(node, (cst.List, cst.Tuple)):
        new_elements = []
        for el in node.elements:
            new_val = remove_value_from_node(el.value, target_val)
            if new_val is not None:
                if new_val is el.value:
                    new_elements.append(el)
                else:
                    new_elements.append(el.with_changes(value=new_val))
        if not new_elements:
            return None
        return node.with_changes(elements=new_elements)
    return node

def rename_value_in_node(node: cst.CSTNode, old_val: str, new_val: str) -> Tuple[cst.CSTNode, bool]:
    if isinstance(node, cst.SimpleString) and node.evaluated_value == old_val:
        return cst.SimpleString(f'"{new_val}"'), True
    if isinstance(node, cst.Name):
        if old_val == "__start__" and node.value == "START":
            if new_val == "__start__":
                return node, False
            return cst.SimpleString(f'"{new_val}"'), True
        if old_val == "__end__" and node.value == "END":
            if new_val == "__end__":
                return node, False
            return cst.SimpleString(f'"{new_val}"'), True
        if node.value == old_val:
            return cst.SimpleString(f'"{new_val}"'), True
    if isinstance(node, (cst.List, cst.Tuple)):
        new_elements = []
        changed = False
        for el in node.elements:
            renamed_val, val_changed = rename_value_in_node(el.value, old_val, new_val)
            if val_changed:
                new_elements.append(el.with_changes(value=renamed_val))
                changed = True
            else:
                new_elements.append(el)
        if changed:
            return node.with_changes(elements=new_elements), True
    return node, False

def extract_send_target(expr: cst.CSTNode) -> Optional[str]:
    if isinstance(expr, cst.Call):
        if isinstance(expr.func, cst.Name) and expr.func.value == "Send":
            if expr.args and isinstance(expr.args[0].value, cst.SimpleString):
                return expr.args[0].value.evaluated_value
    return None

def find_builder_var_from_compile_call(node_val: cst.CSTNode) -> Optional[str]:
    curr = node_val
    while isinstance(curr, cst.Call):
        if isinstance(curr.func, cst.Attribute):
            if curr.func.attr.value == "compile":
                if isinstance(curr.func.value, cst.Name):
                    return curr.func.value.value
            curr = curr.func.value
        else:
            break
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
        self.function_llm_calls = {}
        self.llm_variables = {}
        self.comet_clients = set()
        self.nodes = {}
        self.edges = []
        self.conditional_edges = []
        self.entry_point = None
        self.state_class_name = None
        self.state_schema = {} 
        self.class_schemas = {}
        self.builder_state_classes = {}
        self.builder_state_schemas = {}
        
        self.target_var = target_var
        self.graph_var_names = set()
        self._potential_builders = set()
        
        self.scope_nodes = {}
        self.scope_edges = {}
        self.scope_conditional_edges = {}
        self.scope_entry_points = {}
        self.target_scope = None
        self.target_builder_key = None
        self.subgraph_nodes = {}
        self.function_defs = []
        self.node_function_metadata = {}
        self._all_graph_assignments = []
        self._target_var_found = False
        
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

    def _process_prebuilt_agent(self, call_node: cst.Call, var_name: str):
        state_schema_val = None
        for arg in call_node.args:
            if arg.keyword and isinstance(arg.keyword, cst.Name) and arg.keyword.value == "state_schema":
                if isinstance(arg.value, cst.Name):
                    state_schema_val = arg.value.value
        
        if state_schema_val:
            self.state_class_name = state_schema_val
        
        self.entry_point = "agent"
        self.nodes["agent"] = "agent"
        self.nodes["tools"] = "ToolNode"
        self.edges.append(("tools", "agent"))
        cond_dict = {
            "source": "agent",
            "router": "tools_condition",
            "mapping": {"tools": "tools", "__end__": "__end__"}
        }
        self.conditional_edges.append(cond_dict)

        self.scope_entry_points[self._current_function] = "agent"
        scope_key = (self._current_function, var_name)
        self.scope_entry_points[scope_key] = "agent"
        self.scope_nodes.setdefault(scope_key, {})["agent"] = "agent"
        self.scope_nodes.setdefault(scope_key, {})["tools"] = "ToolNode"
        self.scope_edges.setdefault(scope_key, []).append(("tools", "agent"))
        self.scope_conditional_edges.setdefault(scope_key, []).append(cond_dict)

    def visit_Assign(self, node: cst.Assign):
        # Extract target variable name
        target_name = None
        for target in node.targets:
            if isinstance(target.target, cst.Name):
                target_name = target.target.value
                break

        # Check compile() call (handles chained calls like .compile().with_config())
        builder_name = None
        if isinstance(node.value, cst.Call):
            builder_name = find_builder_var_from_compile_call(node.value)

        is_compile = builder_name is not None
        if builder_name:
            self._all_graph_assignments.append({
                "type": "compile",
                "var_name": target_name,
                "scope": self._current_function,
                "builder_var": builder_name,
                "node": node
            })
            if self.target_var and target_name == self.target_var:
                self._target_var_found = True
                self.target_scope = self._current_function
                self.target_builder_key = (self._current_function, builder_name)

        # Detect create_agent or create_react_agent
        is_prebuilt_agent = False
        func_name = None
        if isinstance(node.value, cst.Call):
            if isinstance(node.value.func, cst.Name):
                func_name = node.value.func.value
            elif isinstance(node.value.func, cst.Attribute) and isinstance(node.value.func.attr, cst.Name):
                func_name = node.value.func.attr.value
            
            if func_name in ("create_agent", "create_react_agent"):
                is_prebuilt_agent = True

        if is_prebuilt_agent:
            self._all_graph_assignments.append({
                "type": "prebuilt",
                "var_name": target_name,
                "scope": self._current_function,
                "node": node
            })
            
            is_target = False
            if not self.target_var or target_name == self.target_var:
                is_target = True
                
            if is_target:
                self._target_var_found = True
                self.target_scope = self._current_function
                self._process_prebuilt_agent(node.value, target_name)

        # Track LLM / Client variables
        if target_name and isinstance(node.value, cst.Call):
            cls_name = extract_callable_name(node.value)
            if cls_name:
                # 1. Check for OpenAI client instantiation
                if cls_name == "OpenAI" or cls_name.endswith(".OpenAI"):
                    is_comet = False
                    for arg in node.value.args:
                        if arg.keyword and isinstance(arg.keyword, cst.Name) and arg.keyword.value == "base_url":
                            if isinstance(arg.value, cst.SimpleString) and "cometapi" in arg.value.evaluated_value:
                                is_comet = True
                    if is_comet:
                        if not hasattr(self, "comet_clients"):
                            self.comet_clients = set()
                        self.comet_clients.add(target_name)
                
                # 2. Check for LangChain or direct LLM classes
                elif any(x in cls_name for x in ["ChatGoogleGenerativeAI", "ChatOpenAI", "ChatAnthropic", "ChatMistralAI", "ChatCohere", "ChatOllama"]):
                    model_val = None
                    for arg in node.value.args:
                        if arg.keyword and isinstance(arg.keyword, cst.Name) and arg.keyword.value == "model":
                            if isinstance(arg.value, cst.SimpleString):
                                model_val = arg.value.evaluated_value
                            elif isinstance(arg.value, cst.Name):
                                if hasattr(self, "_local_assignments") and arg.value.value in self._local_assignments:
                                    model_val = self._local_assignments[arg.value.value][0]
                        elif not arg.keyword and isinstance(arg.value, cst.SimpleString):
                            model_val = arg.value.evaluated_value
                    
                    if not model_val:
                        if "ChatOpenAI" in cls_name:
                            model_val = "gpt-4o"
                        elif "ChatGoogleGenerativeAI" in cls_name:
                            model_val = "gemini-1.5-pro"
                        elif "ChatAnthropic" in cls_name:
                            model_val = "claude-3-5-sonnet"
                        else:
                            model_val = "default"
                            
                    provider = "Unknown"
                    if "Google" in cls_name:
                        provider = "Google"
                    elif "OpenAI" in cls_name:
                        provider = "OpenAI"
                    elif "Anthropic" in cls_name:
                        provider = "Anthropic"
                    elif "Mistral" in cls_name:
                        provider = "Mistral"
                    elif "Cohere" in cls_name:
                        provider = "Cohere"
                    elif "Ollama" in cls_name:
                        provider = "Ollama"
                        
                    if not hasattr(self, "llm_variables"):
                        self.llm_variables = {}
                    self.llm_variables[(self._current_function, target_name)] = {
                        "model": model_val,
                        "provider": provider,
                        "class": cls_name
                    }
                
                # 3. Check for prebuilt agent creations (like create_react_agent)
                elif cls_name in ["create_react_agent", "create_agent"] or cls_name.endswith(".create_react_agent") or cls_name.endswith(".create_agent"):
                    llm_arg_val = None
                    if node.value.args:
                        for arg in node.value.args:
                            if arg.keyword and isinstance(arg.keyword, cst.Name) and arg.keyword.value in ["model", "llm"]:
                                llm_arg_val = arg.value
                                break
                        if not llm_arg_val and not node.value.args[0].keyword:
                            llm_arg_val = node.value.args[0].value
                    
                    if isinstance(llm_arg_val, cst.Name):
                        parent_var = llm_arg_val.value
                        scope_key = (self._current_function, parent_var)
                        global_key = (None, parent_var)
                        if not hasattr(self, "llm_variables"):
                            self.llm_variables = {}
                        if scope_key in self.llm_variables:
                            self.llm_variables[(self._current_function, target_name)] = self.llm_variables[scope_key]
                        elif global_key in self.llm_variables:
                            self.llm_variables[(self._current_function, target_name)] = self.llm_variables[global_key]

                # 4. Check for method chaining, e.g. structured_llm = llm.with_structured_output(...)
                elif isinstance(node.value.func, cst.Attribute) and isinstance(node.value.func.value, cst.Name):
                    parent_var = node.value.func.value.value
                    scope_key = (self._current_function, parent_var)
                    global_key = (None, parent_var)
                    if not hasattr(self, "llm_variables"):
                        self.llm_variables = {}
                    if scope_key in self.llm_variables:
                        self.llm_variables[(self._current_function, target_name)] = self.llm_variables[scope_key]
                    elif global_key in self.llm_variables:
                        self.llm_variables[(self._current_function, target_name)] = self.llm_variables[global_key]

        # Detect StateGraph(AgentState)
        if isinstance(node.value, cst.Call) and isinstance(node.value.func, cst.Name) and node.value.func.value == "StateGraph":
            for target in node.targets:
                if isinstance(target.target, cst.Name):
                    var_name = target.target.value
                    self._potential_builders.add(var_name)
                    self.graph_var_names.add(var_name)
                    
                    schema_name = None
                    if node.value.args:
                        # Check keyword first
                        for arg in node.value.args:
                            if arg.keyword and isinstance(arg.keyword, cst.Name) and arg.keyword.value == "state_schema":
                                if isinstance(arg.value, cst.Name):
                                    schema_name = arg.value.value
                        # Fallback to first positional argument
                        if not schema_name:
                            arg0 = node.value.args[0].value
                            if isinstance(arg0, cst.Name):
                                schema_name = arg0.value
                    if schema_name:
                        self.builder_state_classes[(self._current_function, var_name)] = schema_name

        # Track target scope for local function calls
        if isinstance(node.value, cst.Call) and not is_compile and not is_prebuilt_agent:
            raw_callable = extract_callable_name(node.value)
            if raw_callable and self.target_var and target_name == self.target_var:
                self.target_scope = raw_callable

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
        
        self._current_function = func_name
        self._state_param_name = None
        self._local_assignments = {}
        
        pos = (1, 1)
        try:
            p = self.get_metadata(cst.metadata.PositionProvider, node)
            pos = (p.start.line, p.end.line)
            self.function_lines[func_name] = pos
        except Exception:
            self.function_lines[func_name] = (1, 1)

        active_def = {
            "name": func_name,
            "start_line": pos[0],
            "end_line": pos[1],
            "update_keys": [],
            "input_keys": [],
            "returns": []
        }
        self.function_defs.append(active_def)

        self.function_returns[func_name] = active_def["returns"]
        self.function_update_keys[func_name] = active_def["update_keys"]
        self.function_input_keys[func_name] = active_def["input_keys"]
        
        if node.params.params:
            first_param = node.params.params[0].name.value
            if first_param in ("self", "cls") and len(node.params.params) > 1:
                self._state_param_name = node.params.params[1].name.value
            else:
                self._state_param_name = first_param

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
                    if isinstance(el.value, cst.SimpleString):
                        self.function_returns[self._current_function].append(el.value.evaluated_value)
                    elif isinstance(el.value, cst.Name) and el.value.value == "END":
                        self.function_returns[self._current_function].append("__end__")
                    else:
                        target = extract_send_target(el.value)
                        if target:
                            self.function_returns[self._current_function].append(target)

            # 4. Dict return (state updates)
            elif isinstance(node.value, cst.Dict):
                for el in node.value.elements:
                    if isinstance(el, cst.DictElement) and isinstance(el.key, cst.SimpleString):
                        self.function_update_keys[self._current_function].append(el.key.evaluated_value)

            # 5. ListComp / GeneratorExp return (common for Send)
            elif isinstance(node.value, (cst.ListComp, cst.GeneratorExp)):
                target = extract_send_target(node.value.elt)
                if target:
                    self.function_returns[self._current_function].append(target)

            # 6. Direct Send call
            else:
                target = extract_send_target(node.value)
                if target:
                    self.function_returns[self._current_function].append(target)

    def visit_Call(self, node: cst.Call):
        # LLM detection for Comet API and other models
        if self._current_function:
            call_expr_str = extract_callable_name(node.func)
            model_val = None
            for arg in node.args:
                if arg.keyword and isinstance(arg.keyword, cst.Name) and arg.keyword.value == "model":
                    if isinstance(arg.value, cst.SimpleString):
                        model_val = arg.value.evaluated_value
                    elif isinstance(arg.value, cst.Name):
                        if hasattr(self, "_local_assignments") and arg.value.value in self._local_assignments:
                            vals = self._local_assignments[arg.value.value]
                            if vals:
                                model_val = vals[0]
                        else:
                            model_val = arg.value.value
            
            is_llm_call = False
            provider = "Unknown"
            is_comet = False
            
            if call_expr_str:
                if any(x in call_expr_str for x in ["chat.completions.create", "completions.create"]):
                    is_llm_call = True
                    client_name = call_expr_str.split(".")[0]
                    scope_client_key = (self._current_function, client_name)
                    global_client_key = (None, client_name)
                    comet_clients_set = getattr(self, "comet_clients", set())
                    if scope_client_key in comet_clients_set or global_client_key in comet_clients_set:
                        is_comet = True
                    else:
                        if "comet" in client_name.lower():
                            is_comet = True
                elif "generate_content" in call_expr_str or "generate_text" in call_expr_str:
                    is_llm_call = True
                    provider = "Google"
                elif "invoke" in call_expr_str:
                    var_name = call_expr_str.split(".")[0]
                    scope_llm_key = (self._current_function, var_name)
                    global_llm_key = (None, var_name)
                    llm_vars = getattr(self, "llm_variables", {})
                    if scope_llm_key in llm_vars:
                        is_llm_call = True
                        var_info = llm_vars[scope_llm_key]
                        model_val = var_info["model"]
                        provider = var_info["provider"]
                    elif global_llm_key in llm_vars:
                        is_llm_call = True
                        var_info = llm_vars[global_llm_key]
                        model_val = var_info["model"]
                        provider = var_info["provider"]
                    else:
                        parts = call_expr_str.split('.')
                        if parts and any(x in parts[0].lower() for x in ["llm", "model", "gpt", "claude", "client", "chat"]):
                            is_llm_call = True
            
            if not is_llm_call and model_val and call_expr_str and any(x in call_expr_str.lower() for x in ["create", "generate", "complete", "invoke", "call", "run"]):
                is_llm_call = True

            if is_llm_call:
                model_str = model_val or "unknown-model"
                if provider == "Unknown":
                    if "/" in model_str:
                        parts = model_str.split("/", 1)
                        prov_key = parts[0].lower()
                        if prov_key == "deepseek":
                            provider = "DeepSeek"
                        elif prov_key == "openai":
                            provider = "OpenAI"
                        elif prov_key == "anthropic":
                            provider = "Anthropic"
                        elif prov_key == "google":
                            provider = "Google"
                        else:
                            provider = parts[0].capitalize()
                        model_str = parts[1]
                    else:
                        model_lower = model_str.lower()
                        if "gpt" in model_lower or "o1" in model_lower or "dall-e" in model_lower:
                            provider = "OpenAI"
                        elif "claude" in model_lower:
                            provider = "Anthropic"
                        elif "gemini" in model_lower:
                            provider = "Google"
                        elif "deepseek" in model_lower:
                            provider = "DeepSeek"
                        elif "llama" in model_lower:
                            provider = "Meta"
                        elif "qwen" in model_lower:
                            provider = "Alibaba"
                        elif "mistral" in model_lower or "mixtral" in model_lower:
                            provider = "Mistral"
                        elif "flux" in model_lower:
                            provider = "Black Forest Labs"
                        elif "cohere" in model_lower or "command-r" in model_lower:
                            provider = "Cohere"
                
                if not hasattr(self, "function_llm_calls"):
                    self.function_llm_calls = {}
                if self._current_function not in self.function_llm_calls:
                    self.function_llm_calls[self._current_function] = []
                
                exists = any(item["model"] == model_str and item["provider"] == provider for item in self.function_llm_calls[self._current_function])
                if not exists:
                    self.function_llm_calls[self._current_function].append({
                        "model": model_str,
                        "provider": provider,
                        "raw_model": model_val,
                        "is_comet": is_comet
                    })

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
                scope_key = (self._current_function, obj_name)
                # add_node
                if method_name == "add_node" and len(node.args) >= 2:
                    node_name = None
                    if isinstance(node.args[0].value, cst.SimpleString):
                        node_name = node.args[0].value.evaluated_value

                    raw_fn = extract_callable_name(node.args[1].value)
                    function_name = self.resolve_callable_name(raw_fn) if raw_fn else None

                    if node_name and function_name:
                        self.nodes[node_name] = function_name
                        self.scope_nodes.setdefault(scope_key, {})[node_name] = function_name
                        
                        # Bind lexical function definition using call line number
                        call_line = 1
                        try:
                            p = self.get_metadata(cst.metadata.PositionProvider, node)
                            call_line = p.start.line
                        except Exception:
                            pass

                        f_def = None
                        base_name = function_name.split(".")[-1] if function_name else ""
                        for d in reversed(self.function_defs):
                            d_base_name = d["name"].split(".")[-1]
                            if d_base_name == base_name and d["start_line"] <= call_line:
                                f_def = d
                                break
                        if not f_def:
                            for d in reversed(self.function_defs):
                                d_base_name = d["name"].split(".")[-1]
                                if d_base_name == base_name:
                                    f_def = d
                                    break
                        if f_def:
                            self.node_function_metadata[(scope_key, node_name)] = f_def

                        # Detect if node is a compiled subgraph
                        subgraph_builder = None
                        if isinstance(node.args[1].value, cst.Call):
                            subgraph_builder = find_builder_var_from_compile_call(node.args[1].value)
                        elif isinstance(node.args[1].value, cst.Name):
                            ref_var = node.args[1].value.value
                            for assign in self._all_graph_assignments:
                                if assign["type"] == "compile" and assign["var_name"] == ref_var:
                                    subgraph_builder = assign["builder_var"]
                                    break
                        if subgraph_builder:
                            self.subgraph_nodes[node_name] = subgraph_builder

                # add_edge
                elif method_name == "add_edge" and len(node.args) >= 2:
                    src_vals = resolve_node_values(node.args[0].value)
                    dst_vals = resolve_node_values(node.args[1].value)

                    for src_val in src_vals:
                        for dst_val in dst_vals:
                            if src_val == "__start__":
                                self.entry_point = dst_val
                                self.scope_entry_points[scope_key] = dst_val
                            else:
                                self.edges.append((src_val, dst_val))
                                self.scope_edges.setdefault(scope_key, []).append((src_val, dst_val))

                # set_entry_point
                elif method_name == "set_entry_point" and len(node.args) >= 1:
                    arg0 = node.args[0].value
                    if isinstance(arg0, cst.SimpleString):
                        self.entry_point = arg0.evaluated_value
                        self.scope_entry_points[scope_key] = arg0.evaluated_value

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
                    if len(node.args) >= 3:
                        arg2_val = node.args[2].value
                        if isinstance(arg2_val, cst.Dict):
                            for elt in arg2_val.elements:
                                if isinstance(elt, cst.DictElement):
                                    key = elt.key.evaluated_value if isinstance(elt.key, cst.SimpleString) else ("__end__" if isinstance(elt.key, cst.Name) and elt.key.value == "END" else (elt.key.value if isinstance(elt.key, cst.Name) else None))
                                    val = elt.value.evaluated_value if isinstance(elt.value, cst.SimpleString) else ("__end__" if isinstance(elt.value, cst.Name) and elt.value.value == "END" else (elt.value.value if isinstance(elt.value, cst.Name) else None))
                                    if key and val:
                                        mapping[key] = val
                        elif isinstance(arg2_val, (cst.List, cst.Tuple)):
                            for elt in arg2_val.elements:
                                if isinstance(elt.value, cst.SimpleString):
                                    val = elt.value.evaluated_value
                                    mapping[val] = val
                                elif isinstance(elt.value, cst.Name):
                                    val = elt.value.value
                                    if val == "END":
                                        mapping["__end__"] = "__end__"
                                    else:
                                        mapping[val] = val

                    if not mapping and router_fn == "tools_condition":
                        mapping = {"tools": "tools", "__end__": "__end__"}

                    cond_dict = {
                        "source": source,
                        "router": router_fn,
                        "mapping": mapping
                    }
                    self.conditional_edges.append(cond_dict)
                    self.scope_conditional_edges.setdefault(scope_key, []).append(cond_dict)

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
                                for k, v in imported_analyzer.llm_variables.items():
                                    self.llm_variables[k] = v
                                for k in imported_analyzer.comet_clients:
                                    self.comet_clients.add(k)
                                    
                            elif target_name is None:
                                for func in imported_analyzer.functions:
                                    self._merge_function_meta(func, f"{alias}.{func}", imported_analyzer)
                                for cls_name, schema in imported_analyzer.class_schemas.items():
                                    self.class_schemas[f"{alias}.{cls_name}"] = schema
                                for var_name, type_name in imported_analyzer.variable_types.items():
                                    self.variable_types[f"{alias}.{var_name}"] = type_name
                                for k, v in imported_analyzer.llm_variables.items():
                                    self.llm_variables[f"{alias}.{k}"] = v
                                for k in imported_analyzer.comet_clients:
                                    self.comet_clients.add(f"{alias}.{k}")
                                    
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
                                        
                                if target_name in imported_analyzer.llm_variables:
                                    self.llm_variables[alias] = imported_analyzer.llm_variables[target_name]
                                if target_name in imported_analyzer.comet_clients:
                                    self.comet_clients.add(alias)
                                
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

        # Resolve builder schemas for all builders
        for key, cls_name in list(self.builder_state_classes.items()):
            if cls_name in self.class_schemas:
                self.builder_state_schemas[key] = self.class_schemas[cls_name]
            else:
                self.builder_state_schemas[key] = {}

        # Override main state class and schema for the target builder key
        if self.target_builder_key and self.target_builder_key in self.builder_state_classes:
            self.state_class_name = self.builder_state_classes[self.target_builder_key]
            self.state_schema = self.builder_state_schemas.get(self.target_builder_key, {})

        # Resolve empty mappings for conditional edges
        for cond in self.conditional_edges:
            if not cond["mapping"] and cond["router"]:
                router = cond["router"]
                if router in self.function_returns:
                    for ret in self.function_returns[router]:
                        if ret:
                            cond["mapping"][ret] = ret

        # Fallback if target_var was not found in graph assignments
        if self.target_var and not self._target_var_found and self._all_graph_assignments:
            # Let's search backward for self.target_var
            target_assign = None
            for assign in reversed(self._all_graph_assignments):
                if assign["var_name"] == self.target_var:
                    target_assign = assign
                    break
            if not target_assign:
                target_assign = self._all_graph_assignments[-1]
                
            if target_assign["type"] == "prebuilt":
                self.target_builder_key = (target_assign["scope"], target_assign["var_name"])
                self.target_scope = target_assign["scope"]
            elif target_assign["type"] == "compile":
                self.target_builder_key = (target_assign["scope"], target_assign.get("builder_var"))
                self.target_scope = target_assign["scope"]

        # Resolve target builder key if it's not explicitly set
        if not self.target_builder_key:
            if self._all_graph_assignments:
                for assign in reversed(self._all_graph_assignments):
                    if assign["type"] == "prebuilt":
                        self.target_builder_key = (assign["scope"], assign["var_name"])
                        break
                    elif assign["type"] == "compile" and assign.get("builder_var"):
                        self.target_builder_key = (assign["scope"], assign["builder_var"])
                        break

        if not self.target_builder_key:
            active_keys = [k for k, nds in self.scope_nodes.items() if nds]
            if len(active_keys) == 1:
                self.target_builder_key = active_keys[0]
            elif active_keys:
                global_keys = [k for k in active_keys if k[0] is None]
                if global_keys:
                    self.target_builder_key = global_keys[-1]
                else:
                    self.target_builder_key = active_keys[-1]

        # Apply target builder key filtering
        if self.target_builder_key is not None:
            self.nodes = self.scope_nodes.get(self.target_builder_key, {})
            self.edges = self.scope_edges.get(self.target_builder_key, [])
            self.conditional_edges = self.scope_conditional_edges.get(self.target_builder_key, [])
            self.entry_point = self.scope_entry_points.get(self.target_builder_key, None)
            self.target_scope = self.target_builder_key[0]

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
        if orig_name in other_analyzer.function_llm_calls:
            self.function_llm_calls[alias_name] = other_analyzer.function_llm_calls[orig_name]

class ChangeNodeModelTransformer(cst.CSTTransformer):
    def __init__(self, function_name: str, new_model: str):
        self.function_name = function_name
        self.new_model = new_model
        self.in_target_function = False

    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool:
        if node.name.value == self.function_name:
            self.in_target_function = True
        return True

    def leave_FunctionDef(self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef) -> cst.FunctionDef:
        if original_node.name.value == self.function_name:
            self.in_target_function = False
        return updated_node

    def leave_Call(self, original_node: cst.Call, updated_node: cst.Call) -> cst.Call:
        if self.in_target_function:
            model_arg_idx = -1
            for idx, arg in enumerate(updated_node.args):
                if arg.keyword and isinstance(arg.keyword, cst.Name) and arg.keyword.value == "model":
                    model_arg_idx = idx
                    break
            
            if model_arg_idx != -1:
                new_value = cst.SimpleString(f'"{self.new_model}"')
                new_args = list(updated_node.args)
                new_args[model_arg_idx] = updated_node.args[model_arg_idx].with_changes(value=new_value)
                return updated_node.with_changes(args=new_args)
        return updated_node

class ReplaceFunctionTransformer(cst.CSTTransformer):
    def __init__(self, function_name: str, new_function_code: str):
        self.function_name = function_name
        self.new_function_code = new_function_code

    def leave_FunctionDef(self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef) -> cst.FunctionDef:
        if original_node.name.value == self.function_name:
            try:
                new_node = cst.parse_statement(self.new_function_code.strip())
                if isinstance(new_node, cst.FunctionDef):
                    return new_node
            except Exception as e:
                print(f"Failed to parse new function code: {e}")
        return updated_node

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
                
                if node_contains_value(arg0, self.src) and node_contains_value(arg1, self.dst):
                    is_src_multiple = isinstance(arg0, (cst.List, cst.Tuple))
                    is_dst_multiple = isinstance(arg1, (cst.List, cst.Tuple))
                    
                    if not is_src_multiple and not is_dst_multiple:
                        return cst.RemoveFromParent()
                    
                    new_args = list(call.args)
                    if is_src_multiple and not is_dst_multiple:
                        new_src = remove_value_from_node(arg0, self.src)
                        if new_src is None:
                            return cst.RemoveFromParent()
                        new_args[0] = call.args[0].with_changes(value=new_src)
                    elif is_dst_multiple and not is_src_multiple:
                        new_dst = remove_value_from_node(arg1, self.dst)
                        if new_dst is None:
                            return cst.RemoveFromParent()
                        new_args[1] = call.args[1].with_changes(value=new_dst)
                    else:
                        new_src = remove_value_from_node(arg0, self.src)
                        if new_src is None:
                            return cst.RemoveFromParent()
                        new_args[0] = call.args[0].with_changes(value=new_src)
                    
                    return updated_node.with_changes(
                        body=[cst.Expr(value=call.with_changes(args=new_args))]
                    )

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
                elif isinstance(arg2, (cst.List, cst.Tuple)):
                    new_elements = []
                    for el in arg2.elements:
                        val_match = False
                        if isinstance(el.value, cst.SimpleString) and el.value.evaluated_value == self.dst:
                            val_match = True
                        elif isinstance(el.value, cst.Name) and el.value.value == "END" and self.dst == "__end__":
                            val_match = True
                        
                        if val_match:
                            continue
                        new_elements.append(el)
                    
                    if not new_elements:
                        return cst.RemoveFromParent()
                    
                    new_list = arg2.with_changes(elements=new_elements)
                    new_args = list(call.args)
                    new_args[2] = call.args[2].with_changes(value=new_list)
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
                
                contains_src = node_contains_value(arg0, self.node_id)
                contains_dst = node_contains_value(arg1, self.node_id)
                
                if contains_src or contains_dst:
                    new_src = remove_value_from_node(arg0, self.node_id)
                    new_dst = remove_value_from_node(arg1, self.node_id)
                    
                    if new_src is None or new_dst is None:
                        return cst.RemoveFromParent()
                        
                    new_args = list(call.args)
                    new_args[0] = call.args[0].with_changes(value=new_src)
                    new_args[1] = call.args[1].with_changes(value=new_dst)
                    return updated_node.with_changes(
                        body=[cst.Expr(value=call.with_changes(args=new_args))]
                    )

        # 3. any_graph.add_conditional_edges("node_id", ...)
        if m.matches(updated_node, m.SimpleStatementLine(body=[m.Expr(value=m.Call(func=m.Attribute(attr=m.Name("add_conditional_edges"))))])):
            call = updated_node.body[0].value
            # Check source node match
            if len(call.args) >= 1 and isinstance(call.args[0].value, cst.SimpleString):
                if call.args[0].value.evaluated_value == self.node_id:
                    return cst.RemoveFromParent()
            
            # Check if mapping dictionary became empty
            if len(call.args) >= 3:
                val = call.args[2].value
                if isinstance(val, cst.Dict):
                    if len(val.elements) == 0:
                        return cst.RemoveFromParent()
                elif isinstance(val, (cst.List, cst.Tuple)):
                    new_elements = []
                    for el in val.elements:
                        if isinstance(el.value, cst.SimpleString) and el.value.evaluated_value == self.node_id:
                            continue
                        elif isinstance(el.value, cst.Name) and el.value.value == self.node_id:
                            continue
                        else:
                            new_elements.append(el)
                    if len(new_elements) == 0:
                        return cst.RemoveFromParent()
                    
                    new_args = list(call.args)
                    new_args[2] = call.args[2].with_changes(value=val.with_changes(elements=new_elements))
                    return updated_node.with_changes(
                        body=[cst.Expr(value=call.with_changes(args=new_args))]
                    )

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

def add_edge_to_code(source_code: str, src: str, dst: str, target_var: Optional[str] = None) -> str:
    module = cst.parse_module(source_code)
    
    analyzer = LangGraphAnalyzer(target_var=target_var)
    wrapper = cst.metadata.MetadataWrapper(module)
    wrapper.visit(analyzer)
    
    graph_var = "builder"
    if analyzer.target_builder_key and analyzer.target_builder_key[1]:
        graph_var = analyzer.target_builder_key[1]
    elif analyzer.graph_var_names:
        graph_var = list(analyzer.graph_var_names)[0]
    
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
                renamed_arg, arg_changed = rename_value_in_node(arg, self.old_id, self.new_id)
                if arg_changed:
                    new_args[i] = new_args[i].with_changes(value=renamed_arg)
                    changed = True
            if changed:
                return updated_node.with_changes(args=new_args)

        # Handle any_graph.add_conditional_edges("old_id", ...)
        if m.matches(original_node.func, m.Attribute(attr=m.Name("add_conditional_edges"))):
            new_args = list(updated_node.args)
            changed = False
            if len(new_args) >= 1:
                arg = new_args[0].value
                renamed_arg, arg_changed = rename_value_in_node(arg, self.old_id, self.new_id)
                if arg_changed:
                    new_args[0] = new_args[0].with_changes(value=renamed_arg)
                    changed = True
            
            # Handle list/tuple target nodes renaming in the 3rd argument
            if len(new_args) >= 3:
                val = new_args[2].value
                if isinstance(val, (cst.List, cst.Tuple)):
                    new_elements = []
                    list_changed = False
                    for el in val.elements:
                        renamed_el, el_changed = rename_value_in_node(el.value, self.old_id, self.new_id)
                        if el_changed:
                            new_elements.append(el.with_changes(value=renamed_el))
                            list_changed = True
                        else:
                            new_elements.append(el)
                    if list_changed:
                        new_args[2] = new_args[2].with_changes(value=val.with_changes(elements=new_elements))
                        changed = True

            if changed:
                return updated_node.with_changes(args=new_args)

        # Handle any_graph.set_entry_point("old_id")
        if m.matches(original_node.func, m.Attribute(attr=m.Name("set_entry_point"))):
            if len(updated_node.args) >= 1:
                arg = updated_node.args[0].value
                renamed_arg, arg_changed = rename_value_in_node(arg, self.old_id, self.new_id)
                if arg_changed:
                    new_arg = updated_node.args[0].with_changes(value=renamed_arg)
                    new_args = list(updated_node.args)
                    new_args[0] = new_arg
                    return updated_node.with_changes(args=new_args)

        # Handle compile(interrupt_before=[...], interrupt_after=[...])
        if m.matches(original_node.func, m.Attribute(attr=m.Name("compile"))) or (isinstance(original_node.func, cst.Name) and original_node.func.value == "compile"):
            new_args = list(updated_node.args)
            changed = False
            for idx, arg in enumerate(new_args):
                if arg.keyword and isinstance(arg.keyword, cst.Name) and arg.keyword.value in ("interrupt_before", "interrupt_after"):
                    val = arg.value
                    if isinstance(val, (cst.List, cst.Tuple)):
                        new_elements = []
                        list_changed = False
                        for el in val.elements:
                            if isinstance(el.value, cst.SimpleString) and el.value.evaluated_value == self.old_id:
                                new_el = el.with_changes(value=cst.SimpleString(f'"{self.new_id}"'))
                                new_elements.append(new_el)
                                list_changed = True
                            else:
                                new_elements.append(el)
                        if list_changed:
                            new_val = val.with_changes(elements=new_elements)
                            new_args[idx] = arg.with_changes(value=new_val)
                            changed = True
                    elif isinstance(val, cst.SimpleString) and val.evaluated_value == self.old_id:
                        new_args[idx] = arg.with_changes(value=cst.SimpleString(f'"{self.new_id}"'))
                        changed = True
            if changed:
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

def add_node_to_code(source_code: str, node_name: str, only_add_call: bool = False, target_var: Optional[str] = None) -> str:
    module = cst.parse_module(source_code)
    
    analyzer = LangGraphAnalyzer(target_var=target_var)
    wrapper = cst.metadata.MetadataWrapper(module)
    wrapper.visit(analyzer)
    
    state_name = analyzer.state_class_name or "AgentState"
    graph_var = "builder"
    if analyzer.target_builder_key and analyzer.target_builder_key[1]:
        graph_var = analyzer.target_builder_key[1]
    elif analyzer.graph_var_names:
        graph_var = list(analyzer.graph_var_names)[0]

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
            if len(call.args) >= 2:
                arg0 = call.args[0].value
                arg1 = call.args[1].value
                
                match_src = False
                if isinstance(arg0, cst.SimpleString) and arg0.evaluated_value == self.source:
                    match_src = True
                elif isinstance(arg0, cst.Name) and arg0.value == "START" and self.source == "__start__":
                    match_src = True
                
                router_code = cst.parse_module("").code_for_node(arg1).strip()
                if match_src and router_code == self.router_fn:
                    existing_items = []
                    if len(call.args) >= 3:
                        arg2 = call.args[2].value
                        if isinstance(arg2, cst.Dict):
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
                    if len(call.args) >= 3:
                        updated_args[2] = call.args[2].with_changes(value=updated_dict)
                    else:
                        updated_args.append(cst.Arg(value=updated_dict))
                    updated_call = call.with_changes(args=updated_args)
                    return updated_node.with_changes(body=[cst.Expr(value=updated_call)])
        return updated_node

def add_conditional_edge_to_code(source_code: str, source: str, router_fn: str, mapping: dict, target_var: Optional[str] = None) -> str:
    module = cst.parse_module(source_code)
    
    analyzer = LangGraphAnalyzer(target_var=target_var)
    wrapper = cst.metadata.MetadataWrapper(module)
    wrapper.visit(analyzer)
    
    state_name = analyzer.state_class_name or "AgentState"
    graph_var = "builder"
    if analyzer.target_builder_key and analyzer.target_builder_key[1]:
        graph_var = analyzer.target_builder_key[1]
    elif analyzer.graph_var_names:
        graph_var = list(analyzer.graph_var_names)[0]

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