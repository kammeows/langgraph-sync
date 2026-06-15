import json
import libcst as cst
from parser_libcst import LangGraphAnalyzer, ToolCallVisitor

def transform_to_react_flow(analyzer, tool_visitor):
    nodes = []
    edges = []
    
    # 0. Add virtual START node
    nodes.append({
        "id": "__start__",
        "type": "startNode", # New custom type
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
    
    # Track which functions are actually nodes
    agent_functions = set(node_to_function.values())
    
    for node_id, func_name in node_to_function.items():
        # Determine type
        node_type = "agentNode"
        if node_id and ("tool" in node_id.lower()):
            node_type = "toolNode"
        elif func_name and ("tool" in func_name.lower()):
            node_type = "toolNode"
            
        # Get line numbers if available
        line_info = analyzer.function_lines.get(func_name) if func_name else None
            
        nodes.append({
            "id": node_id,
            "type": node_type,
            "position": {"x": 150, "y": y_offset},
            "data": {
                "label": node_id,
                "functionName": func_name,
                "lines": line_info,
                "isEditable": True
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

    # 3. Process Sub-Tool Nodes
    # (Existing subtool logic, but fixed to be outside the agent loop)
    sub_tool_y = 100
    processed_subtools = set()

    for agent_func, called_funcs in tool_visitor.calls.items():
        if agent_func not in agent_functions: continue
        agent_node_id = next(nid for nid, fname in node_to_function.items() if fname == agent_func)
        
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
                            "isEditable": False
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

    # 4. Process Standard Edges
    for src, dst in analyzer.edges:
        # Handle END node visually
        if dst == "__end__":
             # Check if END node exists, if not add it once
             end_node_id = "__end__"
             if not any(n["id"] == end_node_id for n in nodes):
                 nodes.append({
                     "id": end_node_id,
                     "type": "startNode", # Use same non-editable type
                     "position": {"x": 400, "y": y_offset},
                     "data": {"label": "END", "isEditable": False, "deletable": False}
                 })
             edges.append({
                 "id": f"e-{src}-__end__",
                 "source": src,
                 "target": "__end__",
                 "animated": True
             })
        else:
             edges.append({
                 "id": f"e-{src}-{dst}",
                 "source": src,
                 "target": dst,
                 "animated": True
             })

    # 5. Process Conditional Edges
    for cond in analyzer.conditional_edges:
        source = cond["source"]
        mapping = cond["mapping"]
        
        for label, target in mapping.items():
            if target == "__end__":
                end_node_id = "__end__"
                if not any(n["id"] == end_node_id for n in nodes):
                    nodes.append({
                        "id": end_node_id,
                        "type": "startNode",
                        "position": {"x": 400, "y": y_offset},
                        "data": {"label": "END", "isEditable": False, "deletable": False}
                    })
                target = "__end__"
                
            edges.append({
                "id": f"e-{source}-{target}-cond-{label}",
                "source": source,
                "target": target,
                "style": {"strokeDasharray": "5"},
                "label": f"({label})"
            })

    return {"nodes": nodes, "edges": edges}

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
