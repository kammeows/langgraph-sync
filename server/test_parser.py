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

    def test_subgraph_isolation(self):
        subgraph_code = """
from langgraph.graph import StateGraph, START, END

fa_builder = StateGraph(state_schema=dict)
fa_builder.add_node("get_failures", lambda x: x)
fa_builder.add_node("generate_summary", lambda x: x)
fa_builder.add_edge(START, "get_failures")
fa_builder.add_edge("get_failures", "generate_summary")
fa_builder.add_edge("generate_summary", END)

graph = fa_builder.compile()

qs_builder = StateGraph(dict)
qs_builder.add_node("generate_summary", lambda x: x)
qs_builder.add_node("send_to_slack", lambda x: x)
qs_builder.add_edge(START, "generate_summary")
qs_builder.add_edge("generate_summary", "send_to_slack")
qs_builder.add_edge("send_to_slack", END)

graph = qs_builder.compile()

entry_builder = StateGraph(dict)
entry_builder.add_node("clean_logs", lambda x: x)
entry_builder.add_node("question_summarization", qs_builder.compile())
entry_builder.add_node("failure_analysis", fa_builder.compile())

entry_builder.add_edge(START, "clean_logs")
entry_builder.add_edge("clean_logs", "failure_analysis")
entry_builder.add_edge("clean_logs", "question_summarization")
entry_builder.add_edge("failure_analysis", END)
entry_builder.add_edge("question_summarization", END)

graph = entry_builder.compile()
"""
        module = cst.parse_module(subgraph_code)
        wrapper = cst.metadata.MetadataWrapper(module)

        analyzer = LangGraphAnalyzer(
            target_var="graph",
            current_file_path=os.path.join(self.workspace_root, "main_graph.py"),
            workspace_root=self.workspace_root
        )
        wrapper.visit(analyzer)

        self.assertEqual(analyzer.entry_point, "clean_logs")
        self.assertEqual(set(analyzer.nodes.keys()), {"clean_logs", "question_summarization", "failure_analysis"})
        self.assertEqual(set(analyzer.edges), {
            ("clean_logs", "failure_analysis"),
            ("clean_logs", "question_summarization"),
            ("failure_analysis", "__end__"),
            ("question_summarization", "__end__")
        })

    def test_reduce_usecase_parsing(self):
        reduce_code = """
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

def generate_topics(state):
    return {"subjects": ["joke-about-cats"]}

def continue_to_jokes(state):
    return [Send("generate_joke", {"subject": s}) for s in state["subjects"]]

def generate_joke(state):
    return {"joke": "hahaha"}

builder = StateGraph(dict)
builder.add_node("generate_topics", generate_topics)
builder.add_node("generate_joke", generate_joke)
builder.add_edge(START, "generate_topics")
builder.add_conditional_edges(
    "generate_topics",
    continue_to_jokes,
    ["generate_joke"]
)
graph = builder.compile()
"""
        module = cst.parse_module(reduce_code)
        wrapper = cst.metadata.MetadataWrapper(module)

        analyzer = LangGraphAnalyzer(
            target_var="graph",
            current_file_path=os.path.join(self.workspace_root, "main_graph.py"),
            workspace_root=self.workspace_root
        )
        wrapper.visit(analyzer)

        self.assertEqual(analyzer.entry_point, "generate_topics")
        self.assertEqual(set(analyzer.nodes.keys()), {"generate_topics", "generate_joke"})
        self.assertEqual(len(analyzer.conditional_edges), 1)
        cond = analyzer.conditional_edges[0]
        self.assertEqual(cond["source"], "generate_topics")
        self.assertEqual(cond["router"], "continue_to_jokes")
        self.assertEqual(cond["mapping"], {"generate_joke": "generate_joke"})

    def test_chained_compile_parsing(self):
        chained_code = """
from langgraph.graph import StateGraph, START, END

builder = StateGraph(dict)
builder.add_node("node_a", lambda x: x)
builder.add_edge(START, "node_a")
builder.add_edge("node_a", END)

graph = builder.compile().with_config(run_name="MyChainedGraph")
"""
        module = cst.parse_module(chained_code)
        wrapper = cst.metadata.MetadataWrapper(module)

        analyzer = LangGraphAnalyzer(
            target_var="graph",
            current_file_path=os.path.join(self.workspace_root, "main_graph.py"),
            workspace_root=self.workspace_root
        )
        wrapper.visit(analyzer)

        self.assertEqual(analyzer.entry_point, "node_a")
        self.assertEqual(set(analyzer.nodes.keys()), {"node_a"})
        self.assertEqual(analyzer.target_builder_key, (None, "builder"))

    def test_subgraph_metadata_extraction(self):
        subgraph_code = """
from langgraph.graph import StateGraph, START, END

sub_builder = StateGraph(dict)
sub_builder.add_node("sub_a", lambda x: x)
sub_builder.add_edge(START, "sub_a")
sub_builder.add_edge("sub_a", END)

entry_builder = StateGraph(dict)
entry_builder.add_node("entry_a", lambda x: x)
entry_builder.add_node("my_sub", sub_builder.compile())
entry_builder.add_edge(START, "entry_a")
entry_builder.add_edge("entry_a", "my_sub")
entry_builder.add_edge("my_sub", END)

graph = entry_builder.compile()
"""
        module = cst.parse_module(subgraph_code)
        wrapper = cst.metadata.MetadataWrapper(module)

        analyzer = LangGraphAnalyzer(
            target_var="graph",
            current_file_path=os.path.join(self.workspace_root, "main_graph.py"),
            workspace_root=self.workspace_root
        )
        wrapper.visit(analyzer)

        from transform import transform_to_react_flow
        from parser_libcst import ToolCallVisitor
        tool_visitor = ToolCallVisitor()
        module.visit(tool_visitor)
        flow_data = transform_to_react_flow(analyzer, tool_visitor)

        # Verify entry level nodes
        nodes = flow_data["nodes"]
        my_sub_node = next((n for n in nodes if n["id"] == "my_sub"), None)
        self.assertIsNotNone(my_sub_node)
        self.assertTrue(my_sub_node["data"]["isSubgraph"])

        # Verify internal nodes of the subgraph metadata
        sub_flow = my_sub_node["data"]["subgraph"]
        self.assertIsNotNone(sub_flow)
        sub_nodes = {n["id"] for n in sub_flow["nodes"]}
        self.assertIn("sub_a", sub_nodes)

    def test_multiple_state_schemas_validation(self):
        multi_state_code = """
from typing import TypedDict
from langgraph.graph import StateGraph, START, END

class SubState(TypedDict):
    sub_key: str

class MainState(TypedDict):
    main_key: str

sub_builder = StateGraph(SubState)
def sub_fn(state: SubState):
    return {"sub_key": "ok"}
sub_builder.add_node("sub_node", sub_fn)
sub_builder.add_edge(START, "sub_node")
sub_builder.add_edge("sub_node", END)

entry_builder = StateGraph(MainState)
def entry_fn(state: MainState):
    return {"main_key": "ok"}
entry_builder.add_node("entry_node", entry_fn)
entry_builder.add_node("my_sub", sub_builder.compile())
entry_builder.add_edge(START, "entry_node")
entry_builder.add_edge("entry_node", "my_sub")
entry_builder.add_edge("my_sub", END)

graph = entry_builder.compile()
"""
        module = cst.parse_module(multi_state_code)
        wrapper = cst.metadata.MetadataWrapper(module)

        analyzer = LangGraphAnalyzer(
            target_var="graph",
            current_file_path=os.path.join(self.workspace_root, "main_graph.py"),
            workspace_root=self.workspace_root
        )
        wrapper.visit(analyzer)

        self.assertEqual(analyzer.builder_state_classes.get((None, "sub_builder")), "SubState")
        self.assertEqual(analyzer.builder_state_classes.get((None, "entry_builder")), "MainState")

        from transform import transform_to_react_flow
        from parser_libcst import ToolCallVisitor
        tool_visitor = ToolCallVisitor()
        module.visit(tool_visitor)
        flow_data = transform_to_react_flow(analyzer, tool_visitor)

        # Confirm there are no validation warnings/errors because each node is validated against its correct schema
        errors = [w for w in flow_data["warnings"] if w["type"] == "error"]
        self.assertEqual(len(errors), 0)

    def test_comet_api_llm_calls(self):
        code_with_llm = """
from langgraph.graph import StateGraph
from typing import TypedDict
from openai import OpenAI

class State(TypedDict):
    input: str
    output: str

comet_client = OpenAI(api_key="mock", base_url="https://api.cometapi.com/v1")

def my_llm_node(state: State):
    res = comet_client.chat.completions.create(
        model="deepseek/deepseek-chat",
        messages=[{"role": "user", "content": state["input"]}]
    )
    return {"output": res.choices[0].message.content}

builder = StateGraph(State)
builder.add_node("llm_node", my_llm_node)
builder.set_entry_point("llm_node")
graph = builder.compile()
"""
        module = cst.parse_module(code_with_llm)
        wrapper = cst.metadata.MetadataWrapper(module)
        analyzer = LangGraphAnalyzer(
            target_var="graph",
            current_file_path=os.path.join(self.workspace_root, "main_graph.py"),
            workspace_root=self.workspace_root
        )
        wrapper.visit(analyzer)

        self.assertIn("my_llm_node", analyzer.function_llm_calls)
        calls = analyzer.function_llm_calls["my_llm_node"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["model"], "deepseek-chat")
        self.assertEqual(calls[0]["provider"], "DeepSeek")
        self.assertEqual(calls[0]["raw_model"], "deepseek/deepseek-chat")
        self.assertTrue(calls[0]["is_comet"])

    def test_langchain_llm_calls(self):
        langchain_code = """
from langgraph.graph import StateGraph
from typing import TypedDict
from langchain_google_genai import ChatGoogleGenerativeAI

class State(TypedDict):
    input: str
    output: str

llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")

def my_langchain_node(state: State):
    res = llm.invoke(state["input"])
    return {"output": res.content}

builder = StateGraph(State)
builder.add_node("lc_node", my_langchain_node)
builder.set_entry_point("lc_node")
graph = builder.compile()
"""
        module = cst.parse_module(langchain_code)
        wrapper = cst.metadata.MetadataWrapper(module)
        analyzer = LangGraphAnalyzer(
            target_var="graph",
            current_file_path=os.path.join(self.workspace_root, "main_graph.py"),
            workspace_root=self.workspace_root
        )
        wrapper.visit(analyzer)

        self.assertIn("my_langchain_node", analyzer.function_llm_calls)
        calls = analyzer.function_llm_calls["my_langchain_node"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["model"], "gemini-2.5-flash")
        self.assertEqual(calls[0]["provider"], "Google")
        self.assertFalse(calls[0]["is_comet"])

if __name__ == "__main__":
    unittest.main()
