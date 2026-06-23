import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import json
from fastapi.testclient import TestClient

# Add workspace root and server directory to path
workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(workspace_root)
sys.path.append(os.path.join(workspace_root, "server"))

try:
    from server import app
except ImportError:
    from server.server import app

# Determine the target module object dynamically to avoid hardcoded mock string issues
import server
if hasattr(server, "server"):
    target_module = server.server
else:
    target_module = server

class TestAPIEndpoints(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        
        # Test code block representing a minimal valid graph
        self.test_code = """from langgraph.graph import StateGraph, END
from typing import TypedDict

class AgentState(TypedDict):
    query: str

def agent(state: AgentState):
    return {"query": "test"}

builder = StateGraph(AgentState)
builder.add_node("agent", agent)
builder.set_entry_point("agent")
builder.add_edge("agent", END)
graph = builder.compile()
"""

    def test_list_graphs(self):
        response = self.client.get("/api/graphs")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(isinstance(data, list))
        self.assertTrue(len(data) > 0)
        self.assertIn("file", data[0])
        self.assertIn("var", data[0])

    def test_sync_graph_endpoint(self):
        payload = {
            "code": self.test_code,
            "graph_id": "default"
        }
        response = self.client.post("/api/graph/sync", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("nodes", data)
        self.assertIn("edges", data)
        self.assertIn("code", data)
        
        # Verify node structure parsed from CST
        nodes = data["nodes"]
        node_ids = [n["id"] for n in nodes]
        self.assertIn("agent", node_ids)
        self.assertIn("__start__", node_ids)
        self.assertIn("__end__", node_ids)

    def test_get_graph_endpoint(self):
        # Create a temporary file containing the graph code
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8") as temp:
            temp.write(self.test_code)
            temp_path = temp.name

        try:
            with patch.object(target_module, "get_graph_file_path", return_value=temp_path):
                response = self.client.get("/api/graph?graph_id=default")
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertIn("nodes", data)
                self.assertEqual(data["code"], self.test_code)
        finally:
            os.remove(temp_path)

    def test_mutate_graph_endpoint_add_node(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8") as temp:
            temp.write(self.test_code)
            temp_path = temp.name

        try:
            with patch.object(target_module, "get_graph_file_path", return_value=temp_path):
                # Add a node "new_node" via mutation API
                payload = {
                    "action": "add_node",
                    "graph_id": "default",
                    "new_id": "new_node"
                }
                response = self.client.post("/api/graph/mutate", json=payload)
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertIn("nodes", data)
                
                # Verify the updated graph contains "new_node"
                node_ids = [n["id"] for n in data["nodes"]]
                self.assertIn("new_node", node_ids)
                
                # Check mutated code has been written back to the file
                with open(temp_path, "r", encoding="utf-8") as f:
                    saved_code = f.read()
                self.assertIn("new_node", saved_code)
                self.assertIn("def new_node(state: AgentState):", saved_code)
        finally:
            os.remove(temp_path)

    def test_git_status_endpoint(self):
        mock_status = {
            "initialized": True,
            "active_branch": "main",
            "is_clean": True,
            "modified_files": [],
            "repo_owner": "owner",
            "repo_name": "repo",
            "has_remote": True
        }
        with patch.object(target_module, "get_git_status", return_value=mock_status):
            response = self.client.get("/api/git/status")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["active_branch"], "main")
            self.assertTrue(data["is_clean"])

    def test_git_diff_endpoint(self):
        with patch.object(target_module, "get_git_diff", return_value="diff_mock_contents"):
            response = self.client.get("/api/git/diff")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["diff"], "diff_mock_contents")

    def test_git_create_pr_endpoint(self):
        mock_res = {
            "success": True,
            "pr_url": "https://github.com/owner/repo/pull/1",
            "pr_number": 1
        }
        with patch.object(target_module, "create_pull_request", return_value=mock_res):
            payload = {
                "title": "feat: add lookup node",
                "body": "description"
            }
            response = self.client.post("/api/git/create-pr", json=payload)
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data["success"])
            self.assertEqual(data["pr_url"], "https://github.com/owner/repo/pull/1")

if __name__ == "__main__":
    unittest.main()
