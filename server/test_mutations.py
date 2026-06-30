import unittest
import os
import sys
import libcst as cst

# Add workspace root and server directory to system path
workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(workspace_root)
sys.path.append(os.path.join(workspace_root, "server"))

try:
    from server import apply_mutation_to_source
    from parser_libcst import LangGraphAnalyzer
except ImportError:
    from server.server import apply_mutation_to_source
    from server.parser_libcst import LangGraphAnalyzer

class TestASTMutations(unittest.TestCase):

    def setUp(self):
        # Base template code for state graph testing
        self.base_code = """from langgraph.graph import StateGraph, END
from typing import TypedDict

class AgentState(TypedDict):
    query: str

def my_agent(state: AgentState):
    return {"query": state["query"]}

builder = StateGraph(AgentState)
builder.add_node("agent", my_agent)
builder.set_entry_point("agent")
builder.add_edge("agent", END)
graph = builder.compile()
"""

    def _get_analyzer_for_code(self, code: str) -> LangGraphAnalyzer:
        module = cst.parse_module(code)
        wrapper = cst.metadata.MetadataWrapper(module)
        analyzer = LangGraphAnalyzer(target_var="graph")
        wrapper.visit(analyzer)
        return analyzer

    def test_add_node_mutation(self):
        # Run mutation
        mutated_code = apply_mutation_to_source(self.base_code, "add_node", new_id="database_lookup")
        
        # Parse mutated code and analyze
        analyzer = self._get_analyzer_for_code(mutated_code)
        
        # Verify the new node is registered and function is created
        self.assertIn("database_lookup", analyzer.nodes)
        self.assertIn("def database_lookup(state: AgentState):", mutated_code)
        self.assertIn('builder.add_node("database_lookup", database_lookup)', mutated_code)

    def test_add_node_mutation_existing_function(self):
        from fastapi import HTTPException
        # Base code with my_custom_agent function defined but not added to graph
        code_with_existing_fn = self.base_code + "\n\ndef my_custom_agent(state: AgentState):\n    return state\n"
        
        # 1. Calling add_node without use_existing should raise 409 HTTPException
        with self.assertRaises(HTTPException) as context:
            apply_mutation_to_source(code_with_existing_fn, "add_node", new_id="my_custom_agent")
        self.assertEqual(context.exception.status_code, 409)
        self.assertIn("already implemented in the code", context.exception.detail)

        # 2. Calling add_node with use_existing=True payload should succeed and NOT add duplicate function def
        mutated_code = apply_mutation_to_source(
            code_with_existing_fn, 
            "add_node", 
            new_id="my_custom_agent", 
            payload={"use_existing": True}
        )
        
        # Analyze
        analyzer = self._get_analyzer_for_code(mutated_code)
        
        # Verify the node is added to graph registry
        self.assertIn("my_custom_agent", analyzer.nodes)
        
        # Verify there is exactly one function definition of my_custom_agent (not duplicated)
        self.assertEqual(mutated_code.count("def my_custom_agent"), 1)
        self.assertIn('builder.add_node("my_custom_agent", my_custom_agent)', mutated_code)

    def test_rename_node_mutation(self):
        # Run mutation: rename "agent" -> "researcher"
        mutated_code = apply_mutation_to_source(self.base_code, "rename", node_id="agent", new_id="researcher")
        
        # Analyze
        analyzer = self._get_analyzer_for_code(mutated_code)
        
        # Verify renamed nodes and edges
        self.assertNotIn("agent", analyzer.nodes)
        self.assertIn("researcher", analyzer.nodes)
        self.assertEqual(analyzer.entry_point, "researcher")
        self.assertIn(("researcher", "__end__"), analyzer.edges)
        self.assertNotIn(("agent", "__end__"), analyzer.edges)

    def test_add_edge_mutation(self):
        # Setup: add another node first
        code_with_two_nodes = apply_mutation_to_source(self.base_code, "add_node", new_id="tool")
        
        # Run mutation: connect "agent" -> "tool"
        mutated_code = apply_mutation_to_source(code_with_two_nodes, "add_edge", source="agent", target="tool")
        
        # Analyze
        analyzer = self._get_analyzer_for_code(mutated_code)
        
        # Verify edge exists
        self.assertIn(("agent", "tool"), analyzer.edges)

    def test_delete_edge_mutation(self):
        # Run mutation: delete the static edge "agent" -> END (represented as "__end__" in analyzer)
        mutated_code = apply_mutation_to_source(self.base_code, "delete_edge", source="agent", target="__end__")
        
        # Analyze
        analyzer = self._get_analyzer_for_code(mutated_code)
        
        # Verify edge is gone
        self.assertNotIn(("agent", "__end__"), analyzer.edges)

    def test_delete_node_mutation(self):
        # Setup code with multiple nodes and edges
        code = self.base_code
        code = apply_mutation_to_source(code, "add_node", new_id="tool")
        code = apply_mutation_to_source(code, "add_edge", source="agent", target="tool")
        
        # Run mutation: delete the node "tool"
        mutated_code = apply_mutation_to_source(code, "delete_node", node_id="tool")
        
        # Analyze
        analyzer = self._get_analyzer_for_code(mutated_code)
        
        # Verify the node is deleted
        self.assertNotIn("tool", analyzer.nodes)
        # Verify the attached edge "agent" -> "tool" is also automatically deleted
        self.assertNotIn(("agent", "tool"), analyzer.edges)

    def test_add_conditional_edge_mutation(self):
        # Setup: add a second node "tool" first
        code = apply_mutation_to_source(self.base_code, "add_node", new_id="tool")
        
        # Payload for conditional edge
        payload = {
            "router_fn": "my_router",
            "mapping": {
                "go_to_tool": "tool",
                "go_to_end": "__end__"
            }
        }
        
        # Run mutation: add conditional edge from "agent"
        mutated_code = apply_mutation_to_source(
            code, 
            "add_conditional_edge", 
            source="agent", 
            payload=payload
        )
        
        # Analyze
        analyzer = self._get_analyzer_for_code(mutated_code)
        
        # Verify conditional edges exist in analyzer metadata
        self.assertEqual(len(analyzer.conditional_edges), 1)
        cond_edge = analyzer.conditional_edges[0]
        self.assertEqual(cond_edge["source"], "agent")
        self.assertEqual(cond_edge["router"], "my_router")
        self.assertEqual(cond_edge["mapping"]["go_to_tool"], "tool")
        self.assertEqual(cond_edge["mapping"]["go_to_end"], "__end__")

        # Verify the generated function code exists
        self.assertIn("def my_router(state: AgentState):", mutated_code)
        self.assertIn('builder.add_conditional_edges("agent", my_router,', mutated_code)

    def test_merge_conditional_edge_mutation(self):
        # 1. Setup code with an existing conditional edge
        code = self.base_code
        code = apply_mutation_to_source(code, "add_node", new_id="tool")
        code = apply_mutation_to_source(code, "add_node", new_id="database")
        
        payload1 = {
            "router_fn": "my_router",
            "mapping": {
                "go_to_tool": "tool"
            }
        }
        code = apply_mutation_to_source(code, "add_conditional_edge", source="agent", payload=payload1)
        
        # 2. Add second conditional edge routing to database using same source and router_fn
        payload2 = {
            "router_fn": "my_router",
            "mapping": {
                "go_to_db": "database"
            }
        }
        mutated_code = apply_mutation_to_source(code, "add_conditional_edge", source="agent", payload=payload2)
        
        # 3. Verify assertions
        analyzer = self._get_analyzer_for_code(mutated_code)
        
        # There should only be ONE conditional edge statement registered in metadata
        self.assertEqual(len(analyzer.conditional_edges), 1)
        cond_edge = analyzer.conditional_edges[0]
        
        # The mappings must be merged!
        self.assertEqual(cond_edge["mapping"]["go_to_tool"], "tool")
        self.assertEqual(cond_edge["mapping"]["go_to_db"], "database")
        
        # Check that add_conditional_edges appears exactly once in the code
        self.assertEqual(mutated_code.count("add_conditional_edges"), 1)

    def test_delete_node_part_of_conditional_edge(self):
        # 1. Setup code with conditional edge having multiple targets
        code = self.base_code
        code = apply_mutation_to_source(code, "add_node", new_id="tool")
        code = apply_mutation_to_source(code, "add_node", new_id="db")
        
        payload = {
            "router_fn": "my_router",
            "mapping": {
                "go_to_tool": "tool",
                "go_to_db": "db"
            }
        }
        code = apply_mutation_to_source(code, "add_conditional_edge", source="agent", payload=payload)
        
        # Verify both targets exist initially
        analyzer = self._get_analyzer_for_code(code)
        self.assertEqual(len(analyzer.conditional_edges), 1)
        self.assertEqual(analyzer.conditional_edges[0]["mapping"]["go_to_tool"], "tool")
        self.assertEqual(analyzer.conditional_edges[0]["mapping"]["go_to_db"], "db")

        # 2. Delete "tool" node
        mutated_code_1 = apply_mutation_to_source(code, "delete_node", node_id="tool")
        
        # Verify conditional edge still exists but "tool" mapping is gone, leaving only "db"
        analyzer_1 = self._get_analyzer_for_code(mutated_code_1)
        self.assertEqual(len(analyzer_1.conditional_edges), 1)
        self.assertNotIn("go_to_tool", analyzer_1.conditional_edges[0]["mapping"])
        self.assertEqual(analyzer_1.conditional_edges[0]["mapping"]["go_to_db"], "db")
        self.assertIn("add_conditional_edges", mutated_code_1)

        # 3. Delete "db" node from mutated_code_1 (which has only "db" mapping remaining)
        mutated_code_2 = apply_mutation_to_source(mutated_code_1, "delete_node", node_id="db")

        # Verify that since conditional edge now has no target nodes left, the entire conditional edge statement is deleted
        analyzer_2 = self._get_analyzer_for_code(mutated_code_2)
        self.assertEqual(len(analyzer_2.conditional_edges), 0)
        self.assertNotIn("add_conditional_edges", mutated_code_2)

    def test_update_target_in_conditional_edge_mutation(self):
        # 1. Setup code with conditional edge having target "tool"
        code = self.base_code
        code = apply_mutation_to_source(code, "add_node", new_id="tool")
        code = apply_mutation_to_source(code, "add_node", new_id="researching")
        
        payload1 = {
            "router_fn": "my_router",
            "mapping": {
                "research": "tool"
            }
        }
        code = apply_mutation_to_source(code, "add_conditional_edge", source="agent", payload=payload1)
        
        # Verify initial target
        analyzer = self._get_analyzer_for_code(code)
        self.assertEqual(len(analyzer.conditional_edges), 1)
        self.assertEqual(analyzer.conditional_edges[0]["mapping"]["research"], "tool")

        # 2. Update target of key "research" to "researching"
        payload2 = {
            "router_fn": "my_router",
            "mapping": {
                "research": "researching"
            }
        }
        mutated_code = apply_mutation_to_source(code, "add_conditional_edge", source="agent", payload=payload2)
        
        # Verify that the target is updated, it did not add duplicate keys/lines, and only 1 add_conditional_edges statement exists
        analyzer_mutated = self._get_analyzer_for_code(mutated_code)
        self.assertEqual(len(analyzer_mutated.conditional_edges), 1)
        self.assertEqual(analyzer_mutated.conditional_edges[0]["mapping"]["research"], "researching")
        self.assertEqual(mutated_code.count("add_conditional_edges"), 1)

    def test_rename_key_in_conditional_edge_mutation(self):
        # 1. Setup code with conditional edge having target "researcher"
        code = self.base_code
        code = apply_mutation_to_source(code, "add_node", new_id="researcher")
        
        payload1 = {
            "router_fn": "my_router",
            "mapping": {
                "research": "researcher"
            }
        }
        code = apply_mutation_to_source(code, "add_conditional_edge", source="agent", payload=payload1)
        
        # Verify initial mapping
        analyzer = self._get_analyzer_for_code(code)
        self.assertEqual(len(analyzer.conditional_edges), 1)
        self.assertEqual(analyzer.conditional_edges[0]["mapping"]["research"], "researcher")

        # 2. Update route of target "researcher" to "new_research" (renaming key "research" to "new_research")
        payload2 = {
            "router_fn": "my_router",
            "mapping": {
                "new_research": "researcher"
            }
        }
        mutated_code = apply_mutation_to_source(code, "add_conditional_edge", source="agent", payload=payload2)
        
        # Verify that the key is renamed to "new_research", it did not keep "research", and only 1 statement exists
        analyzer_mutated = self._get_analyzer_for_code(mutated_code)
        self.assertEqual(len(analyzer_mutated.conditional_edges), 1)
        self.assertNotIn("research", analyzer_mutated.conditional_edges[0]["mapping"])
        self.assertEqual(analyzer_mutated.conditional_edges[0]["mapping"]["new_research"], "researcher")
        self.assertEqual(mutated_code.count("add_conditional_edges"), 1)

    def test_list_edges_parsing_and_mutations(self):
        # 1. Base code containing list edge
        list_edge_code = """from langgraph.graph import StateGraph, END
from typing import TypedDict

class AgentState(TypedDict):
    query: str

def b2(state: AgentState): pass
def c(state: AgentState): pass
def d(state: AgentState): pass

builder = StateGraph(AgentState)
builder.add_node("b2", b2)
builder.add_node("c", c)
builder.add_node("d", d)
builder.add_edge(["b2", "c"], "d")
builder.add_edge("d", END)
graph = builder.compile()
"""
        # Parse and check edges
        analyzer = self._get_analyzer_for_code(list_edge_code)
        self.assertIn(("b2", "d"), analyzer.edges)
        self.assertIn(("c", "d"), analyzer.edges)

        # 2. Rename node b2 to new_b2
        renamed_code = apply_mutation_to_source(list_edge_code, "rename", node_id="b2", new_id="new_b2")
        self.assertIn('builder.add_edge(["new_b2", "c"], "d")', renamed_code)
        analyzer_renamed = self._get_analyzer_for_code(renamed_code)
        self.assertIn(("new_b2", "d"), analyzer_renamed.edges)
        self.assertIn(("c", "d"), analyzer_renamed.edges)

        # 3. Delete edge b2 -> d
        deleted_edge_code = apply_mutation_to_source(list_edge_code, "delete_edge", source="b2", target="d")
        self.assertIn('builder.add_edge(["c"], "d")', deleted_edge_code)
        analyzer_deleted_edge = self._get_analyzer_for_code(deleted_edge_code)
        self.assertNotIn(("b2", "d"), analyzer_deleted_edge.edges)
        self.assertIn(("c", "d"), analyzer_deleted_edge.edges)

        # 4. Delete node b2
        deleted_node_code = apply_mutation_to_source(list_edge_code, "delete_node", node_id="b2")
        self.assertIn('builder.add_edge(["c"], "d")', deleted_node_code)
        analyzer_deleted_node = self._get_analyzer_for_code(deleted_node_code)
        self.assertNotIn(("b2", "d"), analyzer_deleted_node.edges)
        self.assertIn(("c", "d"), analyzer_deleted_node.edges)

    def test_list_conditional_edge_mutations(self):
        cond_list_code = """
from langgraph.graph import StateGraph, START, END

def generate_topics(state): pass
def continue_to_jokes(state): pass
def generate_joke(state): pass
def other_node(state): pass

builder = StateGraph(dict)
builder.add_node("generate_topics", generate_topics)
builder.add_node("generate_joke", generate_joke)
builder.add_node("other_node", other_node)
builder.add_edge(START, "generate_topics")
builder.add_conditional_edges(
    "generate_topics",
    continue_to_jokes,
    ["generate_joke", "other_node"]
)
graph = builder.compile()
"""
        # Delete conditional edge to other_node
        mutated = apply_mutation_to_source(cond_list_code, "delete_edge", source="generate_topics", target="other_node")
        self.assertIn('["generate_joke", ]', mutated)
        self.assertNotIn('["generate_joke", "other_node"]', mutated)

        # Delete all conditional edges from generate_topics
        mutated_all = apply_mutation_to_source(mutated, "delete_edge", source="generate_topics", target="generate_joke")
        self.assertNotIn('add_conditional_edges', mutated_all)

if __name__ == "__main__":
    unittest.main()

