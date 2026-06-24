import unittest
import os
import sys
import tempfile
import libcst as cst

# Add server directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from parser_libcst import LangGraphAnalyzer

class TestParserAgentState(unittest.TestCase):

    def setUp(self):
        # Create a temporary directory to act as workspace root
        self.test_dir = tempfile.TemporaryDirectory()
        self.workspace_root = self.test_dir.name

    def tearDown(self):
        self.test_dir.cleanup()

    def test_imported_agent_state(self):
        # 1. Create the imported state file: state_module.py
        state_code = """
from typing import TypedDict, List

class AgentState(TypedDict):
    query: str
    messages: List[str]
    counter: int
"""
        state_file_path = os.path.join(self.workspace_root, "state_module.py")
        with open(state_file_path, "w", encoding="utf-8") as f:
            f.write(state_code)

        # 2. Create the main graph file importing AgentState: main_graph.py
        main_code = """
from langgraph.graph import StateGraph
from state_module import AgentState

def my_node(state: AgentState):
    return {"counter": state["counter"] + 1}

builder = StateGraph(AgentState)
builder.add_node("my_node", my_node)
graph = builder.compile()
"""
        main_file_path = os.path.join(self.workspace_root, "main_graph.py")
        with open(main_file_path, "w", encoding="utf-8") as f:
            f.write(main_code)

        # 3. Run the analyzer on main_graph.py
        module = cst.parse_module(main_code)
        wrapper = cst.metadata.MetadataWrapper(module)

        analyzer = LangGraphAnalyzer(
            target_var="graph",
            current_file_path=main_file_path,
            workspace_root=self.workspace_root
        )
        wrapper.visit(analyzer)

        # 4. Verify results
        # The analyzer should have successfully resolved and set the state_schema!
        self.assertEqual(analyzer.state_class_name, "AgentState")
        self.assertIn("query", analyzer.state_schema)
        self.assertIn("messages", analyzer.state_schema)
        self.assertIn("counter", analyzer.state_schema)
        self.assertEqual(analyzer.state_schema["query"], "str")
        self.assertEqual(analyzer.state_schema["counter"], "int")

if __name__ == "__main__":
    unittest.main()
