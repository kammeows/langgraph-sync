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
