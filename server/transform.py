import json
import libcst as cst
from parser_libcst import LangGraphAnalyzer, ToolCallVisitor

def transform_to_react_flow(analyzer, tool_visitor):
    nodes = []
    edges = []
    warnings = []
    
    # 0. Add virtual START node (always present as it's the entry control)
    nodes.append({
        "id": "__start__",
        "type": "startNode",
        "position": {"x": -100, "y": 100},
        "data": {
            "label": "START",
            "isEditable": False,
            "deletable": False
        }
    })

    # 1. Process Agent Nodes
    y_offset = 100
    node_to_function = analyzer.nodes
    agent_functions = set(node_to_function.values())
    
    for node_id, func_name in node_to_function.items():
        is_tool = node_id and ("tool" in node_id.lower()) or (func_name and "tool" in func_name.lower())
        node_type = "toolNode" if is_tool else "agentNode"
        # Resolve builder key for the main node
        main_builder_var = analyzer.target_builder_key[1] if analyzer.target_builder_key else None
        main_scope = (analyzer.target_scope, main_builder_var)
        node_meta = analyzer.node_function_metadata.get((main_scope, node_id))
        
        if node_meta:
            line_info = (node_meta["start_line"], node_meta["end_line"])
            input_keys = list(set(node_meta["input_keys"]))
            output_keys = list(set(node_meta["update_keys"]))
        else:
            line_info = analyzer.function_lines.get(func_name) if func_name else None
            input_keys = list(set(analyzer.function_input_keys.get(func_name, []))) if func_name else []
            output_keys = list(set(analyzer.function_update_keys.get(func_name, []))) if func_name else []
        
        is_subgraph = False
        subgraph_data = None
        
        if node_id in analyzer.subgraph_nodes:
            builder_var = analyzer.subgraph_nodes[node_id]
            scope_key = (analyzer.target_scope, builder_var)
            if scope_key in analyzer.scope_nodes:
                is_subgraph = True
                sub_nodes = analyzer.scope_nodes[scope_key]
                sub_edges = analyzer.scope_edges.get(scope_key, [])
                sub_cond_edges = analyzer.scope_conditional_edges.get(scope_key, [])
                sub_entry = analyzer.scope_entry_points.get(scope_key)
                
                sub_react_nodes = []
                sub_react_edges = []
                sub_y = 100
                
                # START node
                sub_react_nodes.append({
                    "id": "__start__",
                    "type": "startNode",
                    "position": {"x": -100, "y": 100},
                    "data": {"label": "START"}
                })
                
                for sub_id, sub_func in sub_nodes.items():
                    is_sub_tool = sub_id and ("tool" in sub_id.lower()) or (sub_func and "tool" in sub_func.lower())
                    sub_scope = (analyzer.target_scope, builder_var)
                    sub_meta = analyzer.node_function_metadata.get((sub_scope, sub_id))
                    
                    if sub_meta:
                        sub_line_info = (sub_meta["start_line"], sub_meta["end_line"])
                        sub_input_keys = list(set(sub_meta["input_keys"]))
                        sub_output_keys = list(set(sub_meta["update_keys"]))
                    else:
                        sub_line_info = analyzer.function_lines.get(sub_func) if sub_func else None
                        sub_input_keys = list(set(analyzer.function_input_keys.get(sub_func, []))) if sub_func else []
                        sub_output_keys = list(set(analyzer.function_update_keys.get(sub_func, []))) if sub_func else []
                    
                    sub_react_nodes.append({
                        "id": sub_id,
                        "type": "toolNode" if is_sub_tool else "agentNode",
                        "position": {"x": 150, "y": sub_y},
                        "data": {
                            "label": sub_id,
                            "functionName": sub_func,
                            "lines": sub_line_info,
                            "inputs": sub_input_keys,
                            "outputs": sub_output_keys,
                            "isEditable": True,
                            "deletable": True
                        }
                    })
                    sub_y += 150
                    
                if sub_entry:
                    sub_react_edges.append({
                        "id": f"e-__start__-{sub_entry}",
                        "source": "__start__",
                        "target": sub_entry,
                        "animated": True,
                        "style": {"stroke": "#4caf50", "strokeWidth": 3}
                    })
                    
                sub_node_ids = {n["id"] for n in sub_react_nodes}
                for sub_src, sub_dst in sub_edges:
                    target_id = sub_dst
                    if sub_dst == "__end__":
                        end_node_id = "__end__"
                        if not any(n["id"] == end_node_id for n in sub_react_nodes):
                            sub_react_nodes.append({
                                "id": end_node_id,
                                "type": "startNode",
                                "position": {"x": 400, "y": sub_y},
                                "data": {"label": "END"}
                            })
                            sub_node_ids.add(end_node_id)
                        target_id = "__end__"
                    
                    sub_react_edges.append({
                        "id": f"e-{sub_src}-{target_id}",
                        "source": sub_src,
                        "target": target_id,
                        "animated": True
                    })
                    
                for sub_cond in sub_cond_edges:
                    sub_c_src = sub_cond["source"]
                    sub_c_mapping = sub_cond["mapping"]
                    for label, target in sub_c_mapping.items():
                        target_id = target
                        if target == "__end__":
                            end_node_id = "__end__"
                            if not any(n["id"] == end_node_id for n in sub_react_nodes):
                                sub_react_nodes.append({
                                    "id": end_node_id,
                                    "type": "startNode",
                                    "position": {"x": 400, "y": sub_y},
                                    "data": {"label": "END"}
                                })
                                sub_node_ids.add(end_node_id)
                            target_id = "__end__"
                        
                        sub_react_edges.append({
                            "id": f"e-{sub_c_src}-{target_id}-cond-{label}",
                            "source": sub_c_src,
                            "target": target_id,
                            "style": {"strokeDasharray": "5"},
                            "label": f"({label})",
                            "data": {"condition": label}
                        })
                
                sub_class_name = analyzer.builder_state_classes.get(scope_key, "AgentState")
                sub_schema_fields = analyzer.builder_state_schemas.get(scope_key, {})
                sub_state_keys = set(sub_schema_fields.keys())
                
                for sub_node in sub_react_nodes:
                    sub_nid = sub_node["id"]
                    if sub_nid in ["__start__", "__end__"]:
                        continue
                    
                    sub_outgoing = [e["target"] for e in sub_react_edges if e.get("source") == sub_nid]
                    sub_incoming = [e["source"] for e in sub_react_edges if e.get("target") == sub_nid]
                    sub_node["data"]["incoming"] = sub_incoming
                    sub_node["data"]["outgoing"] = sub_outgoing
                    
                    if not sub_outgoing:
                        warnings.append({
                            "type": "warning",
                            "message": f"Node '{sub_nid}' (inside subgraph '{node_id}') has no outgoing edges. It might be a dead end."
                        })
                    
                    sub_func = sub_node["data"].get("functionName")
                    sub_scope = (analyzer.target_scope, builder_var)
                    sub_meta = analyzer.node_function_metadata.get((sub_scope, sub_nid))
                    
                    if sub_meta:
                        sub_update_keys = list(set(sub_meta["update_keys"]))
                    elif sub_func and sub_func in analyzer.function_update_keys:
                        sub_update_keys = analyzer.function_update_keys[sub_func]
                    else:
                        sub_update_keys = []
                        
                    for uk in sub_update_keys:
                        if sub_state_keys and uk not in sub_state_keys:
                            warnings.append({
                                "type": "error",
                                "message": f"Node '{sub_nid}' (inside subgraph '{node_id}') returns key '{uk}', which is not defined in state schema '{sub_class_name}'."
                            })

                subgraph_data = {
                    "nodes": sub_react_nodes,
                    "edges": sub_react_edges,
                    "state_schema": {
                        "name": sub_class_name,
                        "fields": sub_schema_fields
                    }
                }
            
        nodes.append({
            "id": node_id,
            "type": node_type,
            "position": {"x": 150, "y": y_offset},
            "data": {
                "label": node_id,
                "functionName": func_name,
                "lines": line_info,
                "isEditable": True,
                "deletable": True,
                "inputs": input_keys,
                "outputs": output_keys,
                "isSubgraph": is_subgraph,
                "subgraph": subgraph_data
            }
        })
        y_offset += 150

    # 2. Add Entry Point Edge from START
    node_ids = {n["id"] for n in nodes}
    if analyzer.entry_point:
        if analyzer.entry_point in node_ids:
            edges.append({
                "id": f"e-__start__-{analyzer.entry_point}",
                "source": "__start__",
                "target": analyzer.entry_point,
                "animated": True,
                "style": {"stroke": "#4caf50", "strokeWidth": 3}
            })
        else:
            warnings.append({
                "type": "error",
                "message": f"Entry point references unknown node '{analyzer.entry_point}'."
            })
    else:
        warnings.append({
            "type": "error",
            "message": "START node does not have an entry point edge. Use builder.set_entry_point()."
        })

    # 3. Process Sub-Tool Nodes (Omitted to align with explicit LangGraph nodes)
    pass

    # 4. Process Standard Edges (including virtual END)
    for src, dst in analyzer.edges:
        # Check source and target validity
        if src not in node_ids:
            warnings.append({"type": "error", "message": f"Edge references unknown source node '{src}'."})
            continue

        target_id = dst
        if dst == "__end__":
             # Add END node only if an edge points to it
             end_node_id = "__end__"
             if not any(n["id"] == end_node_id for n in nodes):
                 nodes.append({
                     "id": end_node_id,
                     "type": "startNode",
                     "position": {"x": 400, "y": y_offset},
                     "data": {"label": "END", "isEditable": False, "deletable": True}
                 })
                 node_ids.add(end_node_id)
             target_id = "__end__"
        elif dst not in node_ids:
            warnings.append({"type": "error", "message": f"Edge from '{src}' references unknown target node '{dst}'."})
            continue
             
        edges.append({
            "id": f"e-{src}-{target_id}",
            "source": src,
            "target": target_id,
            "animated": True
        })

    # 5. Process Conditional Edges
    for cond in analyzer.conditional_edges:
        source = cond["source"]
        router_fn = cond["router"]
        mapping = cond["mapping"]
        
        if source not in node_ids:
            warnings.append({"type": "error", "message": f"Conditional edge references unknown source node '{source}'."})
            continue

        # Validation: check if router function returns values not in mapping
        if router_fn in analyzer.function_returns:
            returns = analyzer.function_returns[router_fn]
            for ret in returns:
                if ret not in mapping:
                    warnings.append({
                        "type": "warning",
                        "message": f"Router function '{router_fn}' returns '{ret}', but it is not mapped in builder.add_conditional_edges for node '{source}'."
                    })

        for label, target in mapping.items():
            target_id = target
            if target == "__end__":
                end_node_id = "__end__"
                if not any(n["id"] == end_node_id for n in nodes):
                    nodes.append({
                        "id": end_node_id,
                        "type": "startNode",
                        "position": {"x": 400, "y": y_offset},
                        "data": {"label": "END", "isEditable": False, "deletable": True}
                    })
                    node_ids.add(end_node_id)
                target_id = "__end__"
            elif target not in node_ids:
                warnings.append({"type": "error", "message": f"Conditional edge from '{source}' for key '{label}' references unknown node '{target}'."})
                continue
                
            edges.append({
                "id": f"e-{source}-{target_id}-cond-{label}",
                "source": source,
                "target": target_id,
                "style": {"strokeDasharray": "5"},
                "label": f"({label})",
                "data": {"condition": label}
            })

    # Node-level validations
    state_keys = set(analyzer.state_schema.keys())
    
    # Pre-calculate adjacency for cycle detection and edge listing
    # Safely handle node_ids
    adj = {nid: [] for nid in node_ids}
    for e in edges:
        # Extra safety check
        if e["source"] in adj and e["target"] in node_ids:
            adj[e["source"]].append(e["target"])

    def find_cycle(start_node):
        if start_node not in adj: return None
        # Simple DFS to find a cycle containing start_node
        stack = [(start_node, [start_node])]
        visited = set()
        while stack:
            (node, path) = stack.pop()
            if node in adj:
                for neighbor in adj[node]:
                    if neighbor == start_node:
                        return path + [start_node]
                    if neighbor not in visited:
                        visited.add(neighbor)
                        stack.append((neighbor, path + [neighbor]))
        return None

    for node in nodes:
        node_id = node["id"]
        if node_id in ["__start__", "__end__"]: continue
        if node["type"] == "subToolNode": continue
        
        # 1. Edge connectivity validation & metadata
        incoming = [e["source"] for e in edges if e.get("target") == node_id]
        outgoing = [e["target"] for e in edges if e.get("source") == node_id]
        cycle_path = find_cycle(node_id)
        
        node["data"]["incoming"] = incoming
        node["data"]["outgoing"] = outgoing
        node["data"]["cycle"] = " -> ".join(cycle_path) if cycle_path else None

        if not outgoing:
             warnings.append({
                "type": "warning",
                "message": f"Node '{node_id}' has no outgoing edges. It might be a dead end."
            })
        
        # 2. State schema validation
        func_name = node["data"].get("functionName")
        if func_name and func_name in analyzer.function_update_keys:
            update_keys = analyzer.function_update_keys[func_name]
            for uk in update_keys:
                if state_keys and uk not in state_keys:
                    warnings.append({
                        "type": "error",
                        "message": f"Node '{node_id}' returns key '{uk}', which is not defined in state schema '{analyzer.state_class_name or 'AgentState'}'."
                    })

    all_schemas = {}
    if analyzer.state_class_name:
        all_schemas[analyzer.state_class_name] = analyzer.state_schema
    for key, cls_name in analyzer.builder_state_classes.items():
        if cls_name in analyzer.class_schemas:
            all_schemas[cls_name] = analyzer.class_schemas[cls_name]

    state_schemas = [
        {"name": name, "fields": fields}
        for name, fields in all_schemas.items()
    ]

    return {
        "nodes": nodes, 
        "edges": edges, 
        "warnings": warnings,
        "state_schema": {
            "name": analyzer.state_class_name,
            "fields": analyzer.state_schema
        },
        "state_schemas": state_schemas
    }

if __name__ == "__main__":
    with open("agent.py", "r", encoding="utf8") as f:
        source = f.read()
    module = cst.parse_module(source)
    analyzer = LangGraphAnalyzer()
    module.visit(analyzer)
    tool_visitor = ToolCallVisitor()
    module.visit(tool_visitor)
    flow_data = transform_to_react_flow(analyzer, tool_visitor)
    print(json.dumps(flow_data, indent=2))
