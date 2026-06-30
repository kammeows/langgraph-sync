# LangGraph Sync Visual Builder

LangChain had released their LangGraph Builder which is a browser based canvas where developers can command click to sketch nodes and edges visually to output code scaffolding. However, it is one time code generator which means once you export the code, you cannot sync it back to the visual canvas to continue building or restructuring. So I built LangSync to pick up from here.

`LangSync` is an interactive web tool designed for visualizing, editing and bidirectionally synchronizing LangGraph workflows in real time. By combining a **React Flow Visual Canvas** and a **Monaco Code Editor** with a **FastAPI LibCST AST Parser**, this tool allows developers to modify graph structures visually or via code validating correctness.

When a developer uses LangGraph Studio, it monitors local file changes, and whenever code is modified in VS Code or Cursor, it automatically recompiles the graph on the canvas. But it cannot write code back to the disk.

If a developer realizes during a test run that they need to add a routing node, insert a conditional edge or remove a broken loop back to an agent, they have to manually find the line numbers in their IDE and type out python methods like .add_node() or .add_conditional_edges(). By introducing bidirectional visual editing, LangSync makes life a little easier. Modifying nodes or drawing edges on React Flow doesn't just change state in the browser but mutates the underlying Python script deterministically.

It is a **two-way live visual editor** that runs next to your standard LangGraph development workflow. You edit the visual graph, your Python source code updates. You edit the Python code, the visual graph updates.

---

## How It Works

This builder does not replace LangGraph, rather I'd say it sits next to it. It reads your raw Python files, parses your graphs and serves a visual canvas.

```
┌────────────────────────┐         ┌────────────────────────┐
│  Your LangGraph Code   │ ◄─────► │  React Flow Canvas UI  │
│      (agent.py)        │  Syncs  │   (Visual Node Editor) │
└────────────────────────┘         └────────────────────────┘
            ▲
            │ Runs Mutator
            ▼
┌────────────────────────┐
│  FastAPI Backend Port  │
│  (8000/Local Env port) │
└────────────────────────┘
```

The system uses the existing `langgraph.json`. From there, it maps out the structure, extracts the nodes and edges and serves them.

---

## Technical Explanation

The architecture consists of three core components: the AST preserving parser, the FastAPI microserver and the React visual canvas.

### 1. The Parser: LibCST vs. AST

The absolute core of this project is [parser_libcst.py](file:///D:/uni/agentic_ai/server/parser_libcst.py).

Most code-generation tools use Python’s built-in `ast` module. The problem is that standard AST is **destructive**. When you convert a file to AST, modify it and print it back to source code, you lose all comments, docstrings, empty lines and custom formatting.

To solve this, we use **LibCST** (Concrete Syntax Tree). LibCST maintains a full, format preserving representation of Python code. It treats comments and indentation as first class citizens.

When you make a visual change:

1. The frontend sends a mutation request (e.g., `rename_node`, `add_edge`, `delete_conditional_route`) to the backend.
2. The backend uses LibCST’s `CSTTransformer` classes to surgically locate the exact line where `builder.add_node()`, `builder.add_edge()`, or `builder.compile()` is defined.
3. The parser updates the string values, arguments or dictionary mappings inline, leaving your custom logic, functions, imports and comments completely untouched.

For example, when renaming a node, [parser_libcst.py](file:///D:/uni/agentic_ai/server/parser_libcst.py) doesn't just replace strings blindly. It matches the node name inside:

- Node registrations: `builder.add_node("old_name", ...)`
- Standard edge definitions: `builder.add_edge("old_name", "target")`
- Conditional edge target mappings: `{"key": "old_name"}`
- Compiler configuration: `interrupt_before=["old_name"]`

### 2. The Visual Canvas (React Flow + Monaco)

The frontend is built with React and Vite.

- **Graph Visualization**: We use `@xyflow/react` (React Flow) combined with a `dagre` layout engine. This automatically calculates a clean hierarchical structure
- **Custom Nodes**: We render different shapes and colors depending on the LangGraph node type.
- **Inline Editor**: We embed Microsoft's `Monaco Editor` (the core of VS Code) directly in the UI. When you select a node, the implementation of it gets highlighted (if it is in the same file) and shows all changes. However, you cannot edit it directly.

### 3. The FastAPI Server

The backend [server.py](file:///D:/uni/agentic_ai/server/server.py) is a FastAPI microservice that runs locally.

- **Port auto-binding**: The server runs on port `8000` (or falls back dynamically using the `PORT` environment variable).
- **Workspace Resolution**: It monitors your active folder root (`WORKSPACE_ROOT`) and parses the active file defined in `langgraph.json`.
- **Copilot Agent**: Uses the `google-genai` SDK to run natural-language instructions against your graph structure

---

## Core features

### 1. Interactive Visual Flow Canvas (`React Flow`)

- **Real time Nodes & Edges**: Add, delete and rename graph nodes like agents and tools as well as edges on a live rendered canvas.
- **Smart Edge Routing & Styling**: Loops (self cycles), start edges (highlighted in green) and custom curve handles.
- **Conditional Edge Designer**: An interactive routing modal that parses conditional paths, destination mappings and automatically generates routing functions.

### 2. Bidirectional Monaco Code Editor

- **Live Synchronization**: Edit the Python code in your local repo to see the visual graph update instantly, or edit the canvas to see code updates applied to the python file
- **Validation Panel**: Highlights syntax errors, unconnected nodes or mismatching variables in real time, preventing developers from saving broken graph states.
- **State Schema Inspector**: Parses and displays the underlying `AgentState` schema fields and their typing, helping track context states.

### 3. AST Mutations (`LibCST`)

- Unlike standard LLMs or regex search and replace scripts that rebuild files from scratch (deleting comments and breaking formatting), the FastAPI server uses Python's **LibCST** parser.
- It performs **surgical syntax tree edits** to insert node functions, append entry points and modify dictionary mappings without affecting existing code styles or comments.

### 4. Advanced Multi-File & Import Resolution

- **Recursive Parsing**: Recursively traces, reads and parses imported Python files if nodes, tools, or routing functions are defined in separate modules (e.g. `from agents.extra_module import my_node`).
- **AgentState Resolution**: Evaluates imported class schemas (e.g. `AgentState` defined in a separate file) and merges them cleanly to display schemas and validate state keys.

### 5. Validation Panel and State Schema Panel

- **Validation Panel**:
  - **Structure & Edge Analysis**: Performs real time static checks on graph connectivity. It flags missing entry points (`builder.set_entry_point()`), dead ends (nodes without outgoing edges) and disconnected routes.
  - **Conditional Logic Validation**: Evaluates target routing keys. If a conditional router function returns keys that aren't mapped in your `add_conditional_edges` call, it flags them.
  - **State Key Consistency**: Interrogates what variables each node function writes back to state. If a node returns a dictionary key that is not defined in your state schema, the panel shows a warning
  - **Cycle/Loop Highlighting**: Automatically calculates execution paths to detect self-loops and active recursive cycles, displaying cycle paths inside the panel.
- **State Schema Panel**:
  - **Automatic Class Resolution**: Locates the state class passed during instantiation (e.g. `StateGraph(AgentState)`). If `AgentState` is imported from a separate module, the backend recursively parses imports to resolve the original class block.
  - **Schema Field Inspector**: Extracts and maps out the schema keys and typing annotations (e.g., `messages: list`, `next: str`). It displays them in an interactive sidebar tab so developers can monitor context schemas dynamically as they build.

### 6. AI Copilot for Structural Graph Editing

- **Structural graph changes only:** Provide your Gemini or OpenAI API key and the AI Copilot can modify your graph through natural language commands. It supports adding, deleting, modifying the nodes, creating or removing edges and updating graph connectivity. However, it is intentionally **restricted from modifying any business logic** or Python code. If you ask it to change implementation logic, it will reject the request. The Copilot translates your instructions into backend API calls and so all graph mutations are performed by the backend rather than the AI directly.

- **Upcoming functionality:** I'm working on a sandboxed code editing workflow that will allow the AI to safely modify business logic in an isolated environment. After generating and validating the proposed changes, it will automatically create a GitHub Pull Request for review, enabling AI assisted code changes without affecting your main codebase until they're approved.

### 7. VS Code Extension Integration

The VS Code extension launcher [extension.ts](file:///D:/uni/agentic_ai/vscode-extension/src/extension.ts) automates the process:

1. It looks for a local virtual environment in your project. If it doesn't find one, it builds a private `venv` inside the extension's global storage directory and installs the dependencies (`libcst`, `fastapi`, `uvicorn`, `requests`) silently.
2. It launches the [server.py](file:///D:/uni/agentic_ai/vscode-extension/server/server.py) background process on port `8000`.
3. It opens your system browser directly to the builder UI at `http://localhost:8000`.

---

## Detailed Feature Implementation

### Two-Way Visual Sync

When you load the visual editor, the backend parses the target Python script and constructs a JSON schema representing the graph's nodes, edges, entry point, and compiler flags. React Flow reads this schema and draws the graph.

If you add an edge in React Flow:

1. React Flow fires `onConnect`.
2. The frontend triggers a `POST` to `/api/graph/mutate` with action type `add_edge`.
3. LibCST parses the file, finds the compiled graph builder section, and appends `builder.add_edge("source", "target")` right below the existing edges.
4. The backend returns the updated code and updated schema, immediately updating the visual UI and Monaco editor.

### Prebuilt Agent Support

If your code defines agents using standard LangGraph helpers like `create_react_agent` or `create_agent`, the CST parser is smart enough to recognize them. It translates these prebuilt blocks into dedicated agent nodes and connects them to their specified tools automatically.

### Conditional Routing & Key Mappings

LangGraph conditional edges rely on a routing function and a dictionary mapping keys to destination nodes:

```python
builder.add_conditional_edges(
    "router",
    route_function,
    {
        "continue": "agent_node",
        "end": END
    }
)
```

The visual builder translates this into a specialized conditional router node with labeled outgoing paths. If you add, edit, or delete a route mapping in the UI, the LibCST parser updates the corresponding dictionary literal in your Python file.

### Human-In-The-Loop Interrupts

In LangGraph, state graphs are compiled with checkpointers and interrupt conditions:

```python
graph = builder.compile(
    interrupt_before=["human_node"]
)
```

The parser reads the `interrupt_before` and `interrupt_after` lists in the `.compile()` call. In the UI, any node listed in these lists gets highlighted with an "Interrupt/HITL" status badge. If you rename the node, the parser automatically renames the reference inside the compiler list so your state persistence doesn't break.
