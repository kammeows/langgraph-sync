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
        line_info = analyzer.function_lines.get(func_name) if func_name else None
        
        input_keys = list(set(analyzer.function_input_keys.get(func_name, []))) if func_name else []
        output_keys = list(set(analyzer.function_update_keys.get(func_name, []))) if func_name else []
            
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
                "outputs": output_keys
            }
        })
        y_offset += 150

    # 2. Add Entry Point Edge from START
    if analyzer.entry_point:
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
            "message": "START node does not have an entry point edge. Use builder.set_entry_point()."
        })

    # 3. Process Sub-Tool Nodes
    sub_tool_y = 100
    processed_subtools = set()

    for agent_func, called_funcs in tool_visitor.calls.items():
        if agent_func not in agent_functions: continue
        matches = [nid for nid, fname in node_to_function.items() if fname == agent_func]
        if not matches: continue
        agent_node_id = matches[0]
        
        for called in called_funcs:
            if called in analyzer.functions and called not in agent_functions:
                if called not in processed_subtools:
                    sub_line_info = analyzer.function_lines.get(called)
                    nodes.append({
                        "id": called,
                        "type": "subToolNode",
                        "position": {"x": 600, "y": sub_tool_y},
                        "data": {
                            "label": called,
                            "functionName": called,
                            "lines": sub_line_info,
                            "isEditable": False,
                            "deletable": True
                        }
                    })
                    processed_subtools.add(called)
                    sub_tool_y += 100
                
                edges.append({
                    "id": f"e-{agent_node_id}-{called}",
                    "source": agent_node_id,
                    "target": called,
                    "animated": True
                })

    # 4. Process Standard Edges (including virtual END)
    for src, dst in analyzer.edges:
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
             target_id = "__end__"
             
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
                target_id = "__end__"
                
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
    
    for node in nodes:
        node_id = node["id"]
        if node_id in ["__start__", "__end__"]: continue
        if node["type"] == "subToolNode": continue
        
        # 1. Edge connectivity validation
        has_outgoing = any(e["source"] == node_id for e in edges)
        if not has_outgoing:
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
                        "message": f"Node '{node_id}' returns key '{uk}', which is not defined in state schema '{analyzer.state_class_name}'."
                    })

    return {
        "nodes": nodes, 
        "edges": edges, 
        "warnings": warnings,
        "state_schema": {
            "name": analyzer.state_class_name,
            "fields": analyzer.state_schema
        }
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
