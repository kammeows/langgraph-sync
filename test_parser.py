import sys
sys.path.append('server')
import libcst as cst
from parser_libcst import LangGraphAnalyzer, ToolCallVisitor
from transform import transform_to_react_flow
import json

with open('test_agent1.py', 'r', encoding='utf-8') as f:
    source_code = f.read()

module = cst.parse_module(source_code)
wrapper = cst.metadata.MetadataWrapper(module)

analyzer = LangGraphAnalyzer()
wrapper.visit(analyzer)

tool_visitor = ToolCallVisitor()
module.visit(tool_visitor)

flow_data = transform_to_react_flow(analyzer, tool_visitor)
print(json.dumps(flow_data['state_schema'], indent=2))
print("NODES:", flow_data['nodes'])
