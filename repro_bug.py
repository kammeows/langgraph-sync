import sys
sys.path.append('server')
import libcst as cst
from parser_libcst import LangGraphAnalyzer, ToolCallVisitor
from transform import transform_to_react_flow
import json

code = """
from langgraph.graph import StateGraph, END
class AgentState(dict): pass
builder = StateGraph(AgentState)
builder.add_node("node1", lambda x: x)
builder.add_node("node2", lambda x: x)
builder.add_edge("node1", "node2")
builder.set_entry_point("node1")
graph = builder.compile()
"""

# Test with target_var="graph"
analyzer = LangGraphAnalyzer(target_var="graph")
module = cst.parse_module(code)
wrapper = cst.metadata.MetadataWrapper(module)
wrapper.visit(analyzer)

tool_visitor = ToolCallVisitor()
module.visit(tool_visitor)

flow_data = transform_to_react_flow(analyzer, tool_visitor)
print("With target_var='graph':")
print("Nodes:", [n['id'] for n in flow_data['nodes']])
print("Edges:", len(flow_data['edges']))

# Test without target_var
analyzer2 = LangGraphAnalyzer()
wrapper2 = cst.metadata.MetadataWrapper(module)
wrapper2.visit(analyzer2)
flow_data2 = transform_to_react_flow(analyzer2, tool_visitor)
print("\nWithout target_var:")
print("Nodes:", [n['id'] for n in flow_data2['nodes']])
print("Edges:", len(flow_data2['edges']))
