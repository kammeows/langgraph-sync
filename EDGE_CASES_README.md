# LangGraph AST Parser: Edge Case Handling Guide

This guide outlines the specific graph definition edge cases parsed by the libcst analyzer and how mutations (additions, deletions, renames) are structurally applied.

---

## 1. Multiple Graphs & Subgraphs (Scope Isolation)

- **Problem**: When a file contains multiple compiled graphs (e.g., subgraphs like `fa_builder` and `qs_builder` alongside a top-level `entry_builder`), parser state could merge their nodes and edges together.
- **How it is handled**: The AST analyzer maintains scopes using a composite key: `(enclosing_function_name, builder_variable_name)`.
  - Node registration (`add_node`), edges (`add_edge`), and entry points (`set_entry_point`) are recorded under their respective scope key.
  - When the compiler target is resolved (e.g., matching the compiled variable like `graph = entry_builder.compile()`), the analyzer filters the global nodes and edges to only return matching scope keys.
  - Mutation helpers (add node/edge/conditional edge) receive `target_var` to resolve the target builder's variable name rather than guessing.

---

## 2. Parallel / Multi-Node Edges

- **Problem**: Edges can be defined with multiple source nodes using list syntax:
  ```python
  builder.add_edge(["node_a", "node_b"], "node_c")
  ```
- **How it is handled**: The parser checks if the source node argument in `add_edge` is a list or tuple. If so, it expands it internally to generate multiple individual edges (`node_a -> node_c` and `node_b -> node_c`) so they display correctly on the canvas.
- **Mutations**:
  - If a user deletes the edge `node_a -> node_c`, the AST modifier removes `node_a` from the list in `add_edge(["node_a", "node_b"], "node_c")` but preserves the rest.
  - If the list becomes empty, the entire statement is deleted.

---

## 3. List-Based Path Mappings in Conditional Edges

- **Problem**: LangGraph allows setting conditional edges where the path mapping is a list/tuple of strings instead of a key-value dictionary (e.g., when the router returns `Send()` objects):
  ```python
  builder.add_conditional_edges("source", router_fn, ["target_a", "target_b"])
  ```
- **How it is handled**: The parser detects lists and tuples passed as the 3rd argument to `add_conditional_edges` and populates the canvas mapping by mapping each target item to itself (e.g., `{"target_a": "target_a", "target_b": "target_b"}`).
- **Mutations**: Deletion and renaming search inside list/tuple elements to remove or update matching node names.

---

## 4. Router Return Type Parsing

- **Problem**: Conditional edges might omit the path mapping or return destinations dynamically from routing functions.
- **How it is handled**: The analyzer inspects the router function body to extract valid targets:
  - Simple strings (e.g., `return "node_name"`).
  - System tokens (e.g., `return END`).
  - Direct `Send` calls (e.g., `return Send("node_name", state)`).
  - Lists/tuples of `Send` calls.
  - List comprehensions returning `Send` calls (e.g., `[Send("node_name", ...) for x in list]`).

---

## 5. State Schema & Remote Imports Resolution

- **Problem**: The state schema `StateGraph(StateClass)` is often imported from another file:
  ```python
  from my_state import MyState
  ```
- **How it is handled**: The analyzer parses the import declarations to map module aliases to paths. It then uses the workspace path context to open the remote schema file, parses its classes with libcst, and extracts the field typing declarations so validation checks remain accurate.
