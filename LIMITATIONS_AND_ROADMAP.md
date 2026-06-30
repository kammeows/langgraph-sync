# Limitations, Shortcomings, and Roadmap

Let’s be real: this tool is a huge step forward for bridging the gap between code and visual design, but it’s not magic, and it has some clear limits. If you write highly dynamic, non-standard, or highly nested Python code, the parser *will* trip up. 

If you want to contribute, fork the project, or just understand where it might fail on your codebase, here is the honest list of limitations, shortcomings, and how we can make it better.

---

## 1. Where It Fails & Shortcomings

### Dynamic Graph Definitions
The parser [parser_libcst.py](file:///D:/uni/agentic_ai/server/parser_libcst.py) relies on static analysis of the Concrete Syntax Tree (CST). It expects code to look like standard LangGraph setups:
```python
builder.add_node("agent", agent_node)
builder.add_edge("agent", "tool")
```
If you start doing things like this:
```python
# Fails to parse visually
for node_name, node_func in my_nodes.items():
    builder.add_node(node_name, node_func)
```
The parser will not detect these nodes. It cannot execute your Python code to resolve dynamic loops or runtime dictionary configurations. If your graph construction logic is dynamic, the visual canvas will either be empty or show incomplete structures.

### Complex Routing Functions
We parse conditional edges by looking at the dictionary mapping inside `builder.add_conditional_edges()`:
```python
builder.add_conditional_edges(
    "router",
    route_fn,
    {"continue": "agent", "end": END}
)
```
However, if the `route_fn` returns dynamic values that aren't mapped in that dictionary, or if you don't provide a literal dictionary mapping (e.g., you pass a variable `mapping_dict` defined elsewhere), the visual editor won't know where those conditional routes lead. It can visually edit the dictionary literal arguments inside the call, but it cannot analyze or modify the actual branching logic inside the Python function body of `route_fn`.

### Dynamic Interrupts (Human-in-the-Loop)
We parse compiler flags in `builder.compile()` to find `interrupt_before` and `interrupt_after` lists:
```python
# Parses successfully
graph = builder.compile(interrupt_before=["human_node"])
```
If you define your interrupts dynamically, like:
```python
# Fails to parse or update
my_interrupts = get_interrupt_nodes()
graph = builder.compile(interrupt_before=my_interrupts)
```
The parser won't know which nodes have interrupts, and attempting to edit node names visually won't update the references in `my_interrupts`.

### Edit Conflicts & Race Conditions
There is no collaborative state locking. If you have the visual builder open in your browser and you are concurrently editing the same Python file inside VS Code:
* If you make a change in VS Code, the browser polls or reloads the state, but if you edit the code at the exact millisecond the browser sends a mutation back to the backend, one of the edits will overwrite the other.
* We need file-system watching (`watchdog`) combined with active web-socket locks to prevent write conflicts.

---

## 2. Technical Limitations

### Monolithic Prebuilt Agents
When parsing prebuilt helpers like `create_react_agent`, we treat the resulting agent as a single, opaque node block on the canvas. 
* You can't drill down into it to visually inspect its internal prompts, system instructions, or individual tool bindings. 
* To modify the prebuilt agent, you still have to manually change its Python arguments.

### Static Graph Parsing vs. State Schema Validation
LangGraph is highly dependent on State schemas (passing variables through `State` dicts or TypedDicts). 
* Our editor maps the layout structure, but it does **not** validate your State schema. 
* If you connect `node_a` to `node_b` visually, the code updates. But if `node_b` expects a key in the state that `node_a` never writes, the graph will compile statically but throw a validation error or crash at runtime.

---

## 3. How to Make It Better (The Roadmap)

### Active State & Value Validation
* **Schema Checking**: Parse the `TypedDict` or `Pydantic` State class definitions and check if variables passed between nodes align. If a node reads a field that no previous node writes, highlight the node in red on the canvas with a warning.
* **Dry-Run Executor**: Add a "Test Run" dashboard inside the UI that lets you inject dummy state and step through the compiled graph node-by-node, visualizing how variables flow through the state keys in real time.

### Bidirectional Lock & Collaborative Sync
* **WebSockets & Watchdog**: Replace simple HTTP polling with a persistent WebSocket connection. Use a python file watcher on the backend. The moment a file changes in VS Code, visually flash the updated nodes/edges in React Flow instantly.
* **Conflict Prevention**: If the user is typing in VS Code, lock the corresponding visual node on the canvas to prevent overlapping edits.

### Visual Routing Logic Editor
* Instead of typing Python code inside the Monaco editor sidebar to write conditional router logic, build a visual conditional builder. Let users drag comparison blocks (e.g., `If tool_calls is empty -> END else -> tools`) and auto-generate the routing function logic underneath via LibCST.

### Support for Subgraphs
* Introduce a "Nested Graph" node type. Double-clicking a subgraph node should open a nested React Flow canvas, allowing you to build and modify parent-child agent topologies visually.
