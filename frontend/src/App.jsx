import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  addEdge,
  MarkerType,
} from "@xyflow/react";
import Editor from "@monaco-editor/react";

import EditableNode from "./components/EditableNode";
import DeletableEdge from "./components/DeletableEdge";

import "@xyflow/react/dist/style.css";
import "./App.css";

const nodeTypes = {
  agentNode: EditableNode,
  toolNode: EditableNode,
  subToolNode: EditableNode,
};

const edgeTypes = {
  deletable: DeletableEdge,
};

function App() {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [code, setCode] = useState("");
  const [isEditorCollapsed, setIsEditorCollapsed] = useState(false);
  const editorRef = useRef(null);

  const handleEditorDidMount = (editor, monaco) => {
    editorRef.current = editor;
  };

  const onNodeClick = useCallback(
    (event, node) => {
      console.log("Node clicked data:", node.data);
      if (node.data && node.data.lines && editorRef.current) {
        const [startLine, endLine] = node.data.lines;
        console.log(`Highlighting lines ${startLine} to ${endLine}`);
        editorRef.current.revealLineInCenter(startLine);
        const model = editorRef.current.getModel();
        const maxColumn = model.getLineMaxColumn(endLine);
        editorRef.current.setSelection({
          startLineNumber: startLine,
          startColumn: 1,
          endLineNumber: endLine,
          endColumn: maxColumn,
        });
        if (isEditorCollapsed) setIsEditorCollapsed(false);
      } else if (node.data && node.data.functionName && editorRef.current) {
        const model = editorRef.current.getModel();
        const matches = model.findMatches(`def ${node.data.functionName}`, true, false, true, null, true);
        if (matches.length > 0) {
          const match = matches[0];
          editorRef.current.revealLineInCenter(match.range.startLineNumber);
          editorRef.current.setSelection(match.range);
          if (isEditorCollapsed) setIsEditorCollapsed(false);
        }
      }
    },
    [isEditorCollapsed],
  );

  // 1. Basic State Updaters (local only)
  const onRenameEdgeLabel = useCallback(
    (id, newLabel) => {
      setEdges((eds) =>
        eds.map((edge) => {
          if (edge.id === id) {
            return { ...edge, data: { ...edge.data, label: newLabel } };
          }
          return edge;
        }),
      );
    },
    [setEdges],
  );

  const onDeleteNodeLocal = useCallback(
    (id) => {
      setNodes((nds) => nds.filter((node) => node.id !== id));
      setEdges((eds) => eds.filter((edge) => edge.source !== id && edge.target !== id));
    },
    [setNodes, setEdges]
  );

  // 2. The Core State Processor
  // It takes all handlers as arguments to avoid circularity during definition
  const processGraphStateInternal = useCallback(
    (data, handlers) => {
      const nodesWithHandlers = data.nodes.map((node) => ({
        ...node,
        data: {
          ...node.data,
          type: node.type,
          onDelete: handlers.onDeleteNode,
          onRename: handlers.onRenameNode,
        },
      }));

      const edgesWithHandlers = data.edges.map((edge) => {
        const isConditional = edge.id.includes("-cond") || !!edge.label;
        return {
          ...edge,
          type: "deletable",
          markerEnd: { type: MarkerType.ArrowClosed, width: 20, height: 20, color: "#b1b1b7" },
          style: { strokeWidth: 2, stroke: "#b1b1b7", ...edge.style },
          data: {
            ...edge.data,
            isConditional,
            label: edge.label || (isConditional ? "Conditional Edge" : ""),
            onDelete: handlers.onDeleteEdge,
            onRenameLabel: handlers.onRenameEdgeLabel,
          },
        };
      });

      setNodes(nodesWithHandlers);
      setEdges(edgesWithHandlers);
    },
    [setNodes, setEdges]
  );

  // 3. Backend-Calling Handlers
  // They will use a reference to themselves or a common process function
  
  const onRenameNode = useCallback(
    async (id, newLabel) => {
      try {
        const response = await fetch("http://localhost:8000/api/graph/mutate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "rename", node_id: id, new_id: newLabel }),
        });
        if (response.ok) {
          const data = await response.json();
          if (data.code !== undefined) setCode(data.code);
          // Re-inject the same handlers
          processGraphStateInternal(data, { onRenameNode, onDeleteNode: onDeleteNodeLocal, onDeleteEdge, onRenameEdgeLabel });
        }
      } catch (error) { console.error("Rename failed:", error); }
    },
    [processGraphStateInternal, onDeleteNodeLocal, onRenameEdgeLabel] // Note: onDeleteEdge is used here, so it must be defined
  );

  const onDeleteEdge = useCallback(
    async (id) => {
      setEdges((eds) => {
        const edge = eds.find(e => e.id === id);
        if (edge) {
          fetch("http://localhost:8000/api/graph/mutate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action: "delete_edge", source: edge.source, target: edge.target }),
          }).then(res => res.json()).then(data => {
            if (data.code !== undefined) setCode(data.code);
            processGraphStateInternal(data, { onRenameNode, onDeleteNode: onDeleteNodeLocal, onDeleteEdge, onRenameEdgeLabel });
          });
        }
        return eds.filter(e => e.id !== id);
      });
    },
    [processGraphStateInternal, onRenameNode, onDeleteNodeLocal, onRenameEdgeLabel]
  );

  const onConnect = useCallback(
    async (params) => {
      try {
        const response = await fetch("http://localhost:8000/api/graph/mutate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "add_edge", source: params.source, target: params.target }),
        });
        if (response.ok) {
          const data = await response.json();
          if (data.code !== undefined) setCode(data.code);
          processGraphStateInternal(data, { onRenameNode, onDeleteNode: onDeleteNodeLocal, onDeleteEdge, onRenameEdgeLabel });
        }
      } catch (error) { console.error("Connect failed:", error); }
    },
    [processGraphStateInternal, onRenameNode, onDeleteNodeLocal, onDeleteEdge, onRenameEdgeLabel]
  );

  const addNode = useCallback(async () => {
    const nodeName = window.prompt("Enter a name for the new node:", "my_agent");
    if (!nodeName) return;
    const validName = nodeName.trim().replace(/\s+/g, "_");
    try {
      const response = await fetch("http://localhost:8000/api/graph/mutate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "add_node", new_id: validName }),
      });
      if (response.ok) {
        const data = await response.json();
        if (data.code !== undefined) setCode(data.code);
        processGraphStateInternal(data, { onRenameNode, onDeleteNode: onDeleteNodeLocal, onDeleteEdge, onRenameEdgeLabel });
      }
    } catch (error) { console.error("Add node failed:", error); }
  }, [processGraphStateInternal, onRenameNode, onDeleteNodeLocal, onDeleteEdge, onRenameEdgeLabel]);

  // Initial load
  useEffect(() => {
    fetch("http://localhost:8000/api/graph")
      .then(res => res.json())
      .then(data => {
        if (data.code !== undefined) setCode(data.code);
        processGraphStateInternal(data, { onRenameNode, onDeleteNode: onDeleteNodeLocal, onDeleteEdge, onRenameEdgeLabel });
      });
  }, [processGraphStateInternal, onRenameNode, onDeleteNodeLocal, onDeleteEdge, onRenameEdgeLabel]);

  const syncTimerRef = useRef(null);
  const handleEditorChange = (value) => {
    setCode(value);
    if (syncTimerRef.current) clearTimeout(syncTimerRef.current);
    syncTimerRef.current = setTimeout(async () => {
      try {
        const response = await fetch("http://localhost:8000/api/graph/sync", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code: value }),
        });
        if (response.ok) {
          const data = await response.json();
          processGraphStateInternal(data, { onRenameNode, onDeleteNode: onDeleteNodeLocal, onDeleteEdge, onRenameEdgeLabel });
        }
      } catch (error) { console.error("Sync failed:", error); }
    }, 800);
  };

  return (
    <div className="main-container">
      <div className="graph-container">
        {nodes.length === 0 && (
          <div className="empty-state-container">
            <h2>No Graph Detected</h2>
            <p>Please upload your LangGraph code to get started.</p>
            <button className="empty-state-upload-btn" onClick={() => document.getElementById("code-upload-input").click()}>
              📁 Upload LangGraph Code
            </button>
          </div>
        )}
        <div className="controls-container">
          <button className="add-node-btn" onClick={addNode}>+ Add Node</button>
          <button className="upload-btn" onClick={() => document.getElementById("code-upload-input").click()}>📁 Upload Code</button>
          <input type="file" id="code-upload-input" style={{ display: "none" }} accept=".py" onChange={async (e) => {
            const file = e.target.files[0];
            if (!file) return;
            const formData = new FormData();
            formData.append("file", file);
            const res = await fetch("http://localhost:8000/api/graph/upload", { method: "POST", body: formData });
            if (res.ok) {
              const data = await res.json();
              if (data.code !== undefined) setCode(data.code);
              processGraphStateInternal(data, { onRenameNode, onDeleteNode: onDeleteNodeLocal, onDeleteEdge, onRenameEdgeLabel });
            }
          }} />
        </div>

        <button className="toggle-editor-btn" onClick={() => setIsEditorCollapsed(!isEditorCollapsed)}>
          {isEditorCollapsed ? "← Show Code" : "Hide Code →"}
        </button>

        <ReactFlow
          nodes={nodes} edges={edges}
          onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
          onConnect={onConnect} onNodeClick={onNodeClick}
          nodeTypes={nodeTypes} edgeTypes={edgeTypes} fitView
        >
          <Controls />
          <MiniMap />
          <Background variant="dots" gap={12} size={1} />
        </ReactFlow>
      </div>

      <div className={`editor-sidebar ${isEditorCollapsed ? "collapsed" : ""}`}>
        <div className="editor-header"><span>Source Code</span></div>
        <div className="monaco-editor-wrapper">
          <Editor
            height="100%" language="python" theme="vs-dark" value={code}
            onMount={handleEditorDidMount} onChange={handleEditorChange}
            options={{ readOnly: false, minimap: { enabled: false }, fontSize: 14, lineNumbers: "on", scrollBeyondLastLine: false, automaticLayout: true }}
          />
        </div>
      </div>
    </div>
  );
}

export default App;
