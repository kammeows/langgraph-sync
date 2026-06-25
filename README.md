# LangGraph Sync: Interactive Developer Canvas & AST Editor for LangGraph

`LangGraph Sync` is an interactive web tool designed for visualizing, editing and bidirectionally synchronizing LangGraph workflows in real time. By combining a **React Flow Visual Canvas** and a **Monaco Code Editor** with a **FastAPI LibCST AST Parser**, this tool allows developers to modify graph structures visually or via code validating correctness and exporting changes safely.

---

## Core Features

### 1. Interactive Visual Flow Canvas (`React Flow`)

- **Real time Nodes & Edges**: Add, delete and rename graph nodes like agents and tools as well as edges on a live rendered canvas.
- **Smart Edge Routing & Styling**: Loops (self cycles), start edges (highlighted in green) and custom curve handles.
- **Conditional Edge Designer**: An interactive routing modal that parses conditional paths, destination mappings and automatically generates routing functions.

### 2. Bidirectional Monaco Code Editor

- **Live Synchronization**: Edit the Python code in your local repo to see the visual graph update instantly, or edit the canvas to see code updates applied to the python file.
- **Validation Panel**: Highlights syntax errors, unconnected nodes, or mismatching variables in real time, preventing developers from saving broken graph states.
- **State Schema Inspector**: Parses and displays the underlying `AgentState` schema fields and their typing, helping track context states.

### 3. Surgical AST Mutations (`LibCST`)

- Unlike standard LLMs or regex search and replace scripts that rebuild files from scratch (deleting comments and breaking formatting), the FastAPI server uses Python's **LibCST** parser.
- It performs **surgical syntax tree edits** to insert node functions, append entry points and modify dictionary mappings without affecting existing code styles or comments.

### 4. Advanced Multi-File & Import Resolution

- **Recursive Parsing**: Recursively traces, reads and parses imported Python files if nodes, tools, or routing functions are defined in separate modules (e.g. `from agents.extra_module import my_node`).
- **AgentState Resolution**: Evaluates imported class schemas (e.g. `AgentState` defined in a separate file) and merges them cleanly to display schemas and validate state keys.

### 5. Automated GitHub Pull Request Pipeline

- A secure workflow allowing structural changes to be packaged into a PR:
  1. Checks local repository status (`/api/git/status`) and gathers diffs (`/api/git/diff`).
  2. Prompts the user with a dialog to input PR Title and Description, displaying a green/red code diff preview.
  3. On submit, switches the local workspace to a unique branch (`autopilot/change-<uuid>-<timestamp>`).
  4. Stages, commits and pushes to origin using securely masked Personal Access Token (PAT) authentication to prevent secrets leak in logs.
  5. API-triggers a PR creation on GitHub (`POST /repos/{owner}/{repo}/pulls`).
  6. Checkout-reverts local workspaces back to the original active branch and cleans up temporary local files.

---

## Architectural Overview

### File Structure

- **`server/`**: FastAPI backend service
  - **`server.py`**: API endpoints, middleware, and graph sync orchestration
  - **`parser_libcst.py`**: AST parser and transformer implementations
  - **`git_service.py`**: Local git executions and GitHub PR integration
  - **`test_git_service.py`**: Git integration mock tests
  - **`test_parser.py`**: Parser AgentState import tests
- **`frontend/`**: Vite React flow single page application
  - **`src/App.jsx`**: Core UI workspace layout
  - **`src/components/PRModal.jsx`**: Pull Request designer dialog
  - **`src/components/ConditionalRouteModal.jsx`**: Conditional route logic builder
- **`agents/`**: Folder hosting different LangGraph agent python modules

---

## Step-by-Step Setup Guide

You can also simply download the VSIX file in the root folder as an alternative. Take a look at the README_EXTENSION.md for more info.

### 1. Prerequisites

Ensure you have Python 3.10+ and Node.js 18+ installed on your environment.

### 2. Backend Setup

1. Open a terminal in the root directory.
2. Create and activate a Python virtual environment:

   ```bash
   # Windows
   python -m venv venv
   .\venv\Scripts\activate

   # Linux/macOS
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Create a `.env` file in the root folder and configure your variables:
   ```env
   OPENAI_API_KEY=your_openai_key
   GEMINI_API_KEY=your_gemini_key
   GITHUB_PAT=your_github_personal_access_token
   ```

### 3. Frontend Setup

1. Open a new terminal in the `frontend/` directory.
2. Install npm dependencies:
   ```bash
   npm install
   ```

---

## How to Run and Use

### Step 1: Run the Backend Server

Start the FastAPI server from the root directory:

```bash
venv\Scripts\python server/server.py
```

The server starts on `http://localhost:8001`.

### Step 2: Run the Frontend App

Start the Vite developer server from the `frontend/` directory:

```bash
npm run dev
```

The frontend is hosted on `http://localhost:5173`.

### Step 3: Interactive Workflows

- **Load/Select Graphs**: Use the dropdown in the toolbar to select different graph entry files (e.g. `agent.py`, `agent2.py`).
- **Modify Graph visually**:
  - Click **+ Add Node** to insert a new node.
  - Click **+ Add Conditional Route** to configure a routing mapping.
- **Create PR**:
  1. Make structural changes in the editor or canvas.
  2. Click **Create Pull Request** in the toolbar.
  3. Provide Title & Description, review file changes in the diff panel, and click **Create Pull Request** to submit.

---

## Running Unit Tests

A full test suite is available for verifying server operations.

Run all python test cases:

```bash
venv\Scripts\python -m unittest discover -s server -p "test_*.py"
```

The suite runs:

- **Parser Tests**: Verifies recursive class schema resolutions when importing `AgentState` across separate files.
- **Git Tests**: Assures that git statuses, diff generations, and PR push flows perform correctly under mock setups.
