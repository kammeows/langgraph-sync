import json
import libcst as cst
from libcst_learn.parser_libcst import LangGraphAnalyzer, ToolCallVisitor

def transform_to_react_flow(analyzer, tool_visitor):
    nodes = []
    edges = []
    
    # 1. Process Agent Nodes
    y_offset = 100
    node_to_function = analyzer.nodes
    
    # Track which functions are actually nodes
    agent_functions = set(node_to_function.values())
    
    for node_id, func_name in node_to_function.items():
        # Determine type
        node_type = "agentNode"
        if "tool" in node_id.lower() or "tool" in func_name.lower():
            node_type = "toolNode"
            
        nodes.append({
            "id": node_id,
            "type": node_type,
            "position": {"x": 100 if node_type == "agentNode" else 300, "y": y_offset},
            "data": {"label": f"{node_id} ({func_name})"}
        })
        y_offset += 150

    # 2. Process Sub-Tool Nodes
    # Find functions called by agents that are not agents themselves
    sub_tool_y = 100
    processed_subtools = set()
    
    for agent_func, called_funcs in tool_visitor.calls.items():
        # Only look at agents that are actually nodes
        if agent_func not in agent_functions:
            continue
            
        # Get the node_id for this function
        agent_node_id = next(nid for nid, fname in node_to_function.items() if fname == agent_func)
        
        for called in called_funcs:
            # If it's a defined function but not an agent, it's a subtool
            if called in analyzer.functions and called not in agent_functions:
                if called not in processed_subtools:
                    nodes.append({
                        "id": called,
                        "type": "subToolNode",
                        "position": {"x": 500, "y": sub_tool_y},
                        "data": {"label": called}
                    })
                    processed_subtools.add(called)
                    sub_tool_y += 100
                
                # Add edge from agent to subtool
                edges.append({
                    "id": f"e-{agent_node_id}-{called}",
                    "source": agent_node_id,
                    "target": called,
                    "animated": True
                })

    # 3. Process Standard Edges
    for src, dst in analyzer.edges:
        # Handle END node if necessary
        if dst == "__end__":
             # React flow might need a special node for END or just skip
             continue
             
        edges.append({
            "id": f"e-{src}-{dst}",
            "source": src,
            "target": dst,
            "animated": True
        })

    # 4. Process Conditional Edges
    for cond in analyzer.conditional_edges:
        source = cond["source"]
        mapping = cond["mapping"]
        
        for label, target in mapping.items():
            if target == "__end__":
                continue
                
            edges.append({
                "id": f"e-{source}-{target}-cond",
                "source": source,
                "target": target,
                "style": {"strokeDasharray": "5"},
                "label": f"Conditional ({label})"
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
