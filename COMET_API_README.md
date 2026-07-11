# Comet API & LangGraph Visualizer Integration

This document outlines the architecture like the backend capabilities and frontend features built to integrate **CometAPI** and direct LLM telemetry into LangGraph-Sync.

---

## Table of Contents

1. [Overview](#-overview)
2. [Scope-Aware AST Parsing Architecture](#-scope-aware-ast-parsing-architecture)
   - [Method Chaining Resolution](#method-chaining-resolution)
   - [Prebuilt Agent Interception](#prebuilt-agent-interception)
3. [Surgical Node-Local Model Mutation](#-surgical-node-local-model-mutation)
4. [Secure Backend Model Proxy & Fallbacks](#-secure-backend-model-proxy--fallbacks)
5. [Frontend LLM Inspector Panel](#-frontend-llm-inspector-panel)
   - [Gateway vs. Direct Badges](#gateway-vs-direct-badges)
   - [Model Selector Dropdown & Custom Inputs](#model-selector-dropdown--custom-inputs)
   - [Cost & Latency Telemetry Metrics](#cost--latency-telemetry-metrics)
6. [Examples & Test Suites](#-examples--test-suites)

---

## Overview

The **Comet API Integration** extends the LangGraph-Sync platform to parse and display LLM models used within individual graph nodes. It supports:

- Distinguishing between **Comet API Gateway** calls (routed through the aggregator base URL) and **Direct API** calls (running via native OpenAI/Gemini/Anthropic credentials)
- Intercepting chained declarations like `.bind_tools(...)` or `.with_structured_output(...)` to resolve model parameters
- Changing model selections interactively from the UI and applying mutations directly to the source code without restarting the server

Do make sure you have COMETAPI_KEY defined in your .env file. To use this feature, you will have to clone the repo and use it locally. The updated VSIX extension file will be released soon.

---

## Scope-Aware AST Parsing Architecture

The core of the system is the `LangGraphAnalyzer` inside `server/parser_libcst.py`. It uses **LibCST** to visit assignments (`visit_Assign`) and calls (`visit_Call`) to extract model references.

### Scope-Aware Variable Resolution

To handle shadowed variable declarations (e.g. where different node functions define local variables named `model` or `llm`), variables are tracked using scope keys:

- **Format:** `(function_scope, variable_name)` (where `function_scope` is `None` for global imports and assignments, or the function name for local definitions).
- **Lookup Flow:** The visitor searches for assignments locally first and falls back to global scopes to find the model class and arguments.

### Method Chaining Resolution

Many LangChain workflows modify existing LLM variables via method chains. The parser handles this by propagating model properties through assignment chains:

```python
# The analyzer resolves that `llm_with_tools` inherits model: "gpt-4.1" and provider: "OpenAI"
llm_with_tools = _llm_instance.bind_tools(tools)
```

- **Supported chains:** `.bind_tools(...)`, `.with_structured_output(...)`, `.bind(...)`, `.with_config(...)`, etc.

### Prebuilt Agent Interception

For nodes that construct agents dynamically via LangGraph's prebuilt functions (e.g. `create_react_agent`), the parser scans positional and keyword parameters to identify the wrapped LLM variable:

```python
# The analyzer traces `model` to find provider metadata and associates it with `sql_agent`
sql_agent = create_react_agent(model, [execute_sql], ...)
```

---

## Node-Local Model Mutation

When you change a node's model via the inspector panel, the platform performs a surgical AST mutation on the source file using the `ChangeNodeModelTransformer`:

1. **Target Identification:** Finds only the `FunctionDef` node matching the active node function (e.g. `def leo(state):`).
2. **Local Scan:** Searches only within that function's children for calls (`cst.Call`) containing a keyword argument named `model`.
3. **AST Transformation:** Replaces the existing string literal node with a `cst.SimpleString` representation of the new model path.
4. **Safety Guarantee:** By restricting the transformation to the local node function scope, global settings or other graph nodes remain entirely untouched to prevent unintended side effects.

---

## Secure Backend Model Proxy & Fallbacks

To protect your `COMETAPI_KEY` from exposure in the client browser, the platform handles model queries on the server side:

- **Proxy Endpoint (`GET /api/comet/models`):** The backend queries CometAPI's endpoint `https://api.cometapi.com/v1/models` using authorization headers powered securely by `os.getenv("COMETAPI_KEY")`.
- **Intelligent Fallbacks:** If the API key is not configured, expired (401 status), or the machine is offline, the backend gracefully returns an empty list.

---

## Frontend LLM Inspector Panel

Clicking a node in the graph opens the **LLM Inspector Panel** on the right side of the canvas.

### Gateway vs. Direct Badges

The dashboard shows a clear visual badge next to each LLM call:

- <span style="background-color: rgba(168, 85, 247, 0.15); color: #d8b4fe; border: 1px solid rgba(168, 85, 247, 0.3); padding: 1px 4px; border-radius: 3px; font-size: 10px; font-weight: 500;">Comet Gateway</span> for completions routed through the Comet API endpoint.
- <span style="background-color: rgba(59, 130, 246, 0.15); color: #93c5fd; border: 1px solid rgba(59, 130, 246, 0.3); padding: 1px 4px; border-radius: 3px; font-size: 10px; font-weight: 500;">Direct API</span> for native integrations (e.g. LangChain models).

### Model Selector Dropdown & Custom Inputs

If the model is hosted via Comet Gateway, you can hot-swap it:

- Use the dropdown list of active models.
- Choose **✏️ Custom Model Path...** to show an input field where you can type any of the 500+ model configurations supported by the Comet API gateway. Clicking `✓` applies it instantly.

### Cost & Latency Telemetry Metrics

For all Comet API models, the panel renders estimated costs and latency bounds:

- **Est. Cost (per M tokens):** Displays input and output token pricing (reflecting Comet's 20% gateway volume discount).
- **Avg. Latency Class:** Categorizes response speeds (`Ultra Fast`, `Fast`, `Moderate`, `Thinking`).

---

## Examples & Test Suites

### Comet Usecases

Robust multi-agent and single-agent configurations demonstrating Comet API integration can be found in:

- **[comet_multi_agent.py](file:///D:/uni/agentic_ai/agents/comet_api_usecases/comet_multi_agent.py):** Implements multi-model coordination (`gpt-4o`, `claude-3-5-sonnet`, `deepseek-chat`).
- **[comet_single_agent.py](file:///D:/uni/agentic_ai/agents/comet_api_usecases/comet_single_agent.py):** Uses reasoning models (`deepseek-reasoner` / R1) for complex analysis.

### Testing Mutations & AST Parsers

Run the complete python test suites to verify compile behaviors:

```bash
# Run parser test cases
python -m unittest server/test_parser.py

# Run mutation test cases
python -m unittest server/test_mutations.py
```
