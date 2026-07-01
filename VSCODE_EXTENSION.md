# LangGraph Sync Visual Builder - VS Code Extension Guide

The extension bundles a background FastAPI backend server and static React frontend assets, launching them on your local machine.

---

## 🛠️ Prerequisites

To run the builder, you only need:

1. **Python 3.9+** installed globally on your system.
2. **VS Code (v1.85.0+)** installed.

---

## 📥 Installation

You can install the extension directly from the releases section: https://github.com/kammeows/langgraph-sync/releases/tag/v1.0.0

After the download is complete, follow the steps below:

1. Open **VS Code**.
2. Open the **Extensions** view (`Ctrl + Shift + X` on Windows/Linux or `Cmd + Shift + X` on macOS).
3. Click the `...` (Views and More Actions) menu button in the top-right corner of the Extensions panel.
4. Select **Install from VSIX...**.
5. Select the packaged extension file: `langgraph-sync-0.0.1.vsix`.
6. After installation, reload VS Code (or run the command `Developer: Reload Window` from the Command Palette).

---

## 🚀 Zero-Configuration Out of the Box

The extension is designed to run automatically with **zero manual setup**:

### 1. Automatic Python Dependency Setup

When you launch the visual builder, the extension automatically:

- Checks if a suitable local environment exists.
- If not, it creates a private virtual environment inside its global storage directory.
- It automatically downloads and installs all necessary backend libraries (`libcst`, `fastapi`, `uvicorn`, `python-dotenv`) in the background.
- Shows a VS Code progress notification during the one-time installation.

### 2. Smart Workspace Validation & `langgraph.json` Setup

Before starting the builder, the extension checks if `langgraph.json` is present in your workspace root:

- **If found**: It uses your configuration.
- **If missing**:
  - It scans your workspace for Python files containing `StateGraph` definitions.
  - It automatically identifies the python filename and the compiled graph variable name (e.g. `graph = builder.compile()`).
  - It prompts you with a VS Code dialog: _"No langgraph.json configuration file was found in your workspace root. Would you like to automatically generate one?"_
  - Clicking **Yes, generate default** creates the `langgraph.json` file for you automatically.
  - If no python files are found, it alerts you with a clear warning explaining how to get started.

---

## 🚀 How to Run the Extension

### 1. Launch the Visual Builder

1. Open any Python file (`.py`) containing a LangGraph definition in VS Code.
2. Click the **LangGraph: Open Visual Builder** icon in the editor title menu bar (top-right corner of the editor window).
3. Alternatively:
   - Open the VS Code Command Palette (`F1` or `Ctrl + Shift + P` / `Cmd + Shift + P`).
   - Run the command: **`LangGraph: Open Visual Builder`**.
4. The extension will start the background server on `http://localhost:8000` and automatically open the application in your system's default browser.

### 2. Stop the Server

When you are done editing, you can stop the server:

- Open the Command Palette and run: **`LangGraph: Stop Visual Builder Server`**.
- _Note: Closing the VS Code window or workspace automatically shuts down the background server process._

---

## ⚙️ Custom Configuration (Optional)

If you want to bypass the automatic setup and use a specific Python interpreter, you can set it in VS Code Settings:

1. Open VS Code Settings (`Ctrl + ,` or `Cmd + ,`).
2. Search for `LangGraph Sync`.
3. Set **LangGraph Sync: Python Path** to your custom python executable (e.g., `C:\path\to\venv\Scripts\python.exe`).
