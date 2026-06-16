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
import SelfLoopEdge from "./components/SelfLoopEdge";
import ConditionalRouteModal from "./components/ConditionalRouteModal";

import "@xyflow/react/dist/style.css";
import "./App.css";

const nodeTypes = {
  agentNode: EditableNode,
  toolNode: EditableNode,
  subToolNode: EditableNode,
  startNode: EditableNode,
};

const edgeTypes = {
  deletable: DeletableEdge,
  selfLoop: SelfLoopEdge,
};

function App() {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [code, setCode] = useState("");
  const [isEditorCollapsed, setIsEditorCollapsed] = useState(false);
  const [isCondModalOpen, setIsCondModalOpen] = useState(false);
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
        const matches = model.findMatches(
          `def ${node.data.functionName}`,
          true,
          false,
          true,
          null,
          true,
        );
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

  // 1. Handlers Reference to break circularity
  const handlersRef = useRef({});

  // 2. Local State Updaters
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

  // 3. The Core State Processor
  // Uses handlersRef.current for injection to avoid dependency cycles
  const processGraphStateInternal = useCallback(
    (data) => {
      const handlers = handlersRef.current || {};
      const nodesWithHandlers = data.nodes.map((node) => ({
        ...node,
        data: {
          ...node.data,
          type: node.type,
          onDelete: (id) => {
            if (id === "__start__") return;
            handlers.onDeleteNode && handlers.onDeleteNode(id);
          },
          onRename: (id, label) => {
            if (id === "__start__" || id === "__end__") return;
            handlers.onRenameNode && handlers.onRenameNode(id, label);
          },
        },
      }));

      const edgesWithHandlers = data.edges.map((edge) => {
        const isConditional = edge.id.includes("-cond") || !!edge.label;
        const isStartEdge = edge.source === "__start__";
        const isSelfLoop = edge.source === edge.target;

        return {
          ...edge,
          type: isSelfLoop ? "selfLoop" : "deletable",
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 25,
            height: 25,
            color: isStartEdge ? "#22c55e" : "#b1b1b7",
          },
          style: {
            strokeWidth: isStartEdge ? 3 : 2,
            stroke: isStartEdge ? "#22c55e" : "#b1b1b7",
            ...edge.style,
          },
          deletable: true,
          data: {
            ...edge.data,
            source: edge.source,
            target: edge.target,
            isConditional,
            label: edge.label || (isConditional ? "Conditional Edge" : ""),
            onDelete: (id) => {
              handlers.onDeleteEdge && handlers.onDeleteEdge(id);
            },
            onRenameLabel: onRenameEdgeLabel,
          },
        };
      });

      setNodes(nodesWithHandlers);
      setEdges(edgesWithHandlers);
    },
    [onRenameEdgeLabel, setNodes, setEdges],
  );

  // 4. Backend-Calling Handlers

  const onRenameNode = useCallback(
    async (id, newLabel) => {
      try {
        const response = await fetch("http://localhost:8000/api/graph/mutate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action: "rename",
            node_id: id,
            new_id: newLabel,
          }),
        });
        if (response.ok) {
          const data = await response.json();
          if (data.code !== undefined) setCode(data.code);
          processGraphStateInternal(data);
        }
      } catch (error) {
        console.error("Rename failed:", error);
      }
    },
    [processGraphStateInternal, setCode],
  );

  const onDeleteNode = useCallback(
    async (id) => {
      if (!window.confirm(`Are you sure you want to delete node "${id}"?`))
        return;
      try {
        const response = await fetch("http://localhost:8000/api/graph/mutate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "delete_node", node_id: id }),
        });
        if (response.ok) {
          const data = await response.json();
          if (data.code !== undefined) setCode(data.code);
          processGraphStateInternal(data);
        }
      } catch (error) {
        console.error("Delete node failed:", error);
      }
    },
    [processGraphStateInternal, setCode],
  );

  const onDeleteEdge = useCallback(
    async (id) => {
      const edge = edges.find((e) => e.id === id);
      if (!edge) return;

      try {
        const response = await fetch("http://localhost:8000/api/graph/mutate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action: "delete_edge",
            source: edge.source,
            target: edge.target,
            payload: { condition: edge.data?.condition },
          }),
        });
        if (response.ok) {
          const data = await response.json();
          if (data.code !== undefined) setCode(data.code);
          processGraphStateInternal(data);
        }
      } catch (error) {
        console.error("Delete edge failed:", error);
      }
    },
    [edges, processGraphStateInternal, setCode],
  );

  const onConnect = useCallback(
    async (params) => {
      console.log("Connect params:", params);
      
      // Prevent connections to/from virtual sub-tool nodes
      const sourceNode = nodes.find((n) => n.id === params.source);
      const targetNode = nodes.find((n) => n.id === params.target);
      
      if (sourceNode?.type === "subToolNode" || targetNode?.type === "subToolNode") {
        alert("You cannot manually connect to or from virtual sub-tool nodes. These are inferred from function calls in your code.");
        return;
      }

      if (params.target === "__start__") {
        alert("The START node cannot have incoming edges.");
        return;
      }
      if (params.source === "__end__") {
        alert("The END node cannot have outgoing edges.");
        return;
      }

      try {
        const response = await fetch("http://localhost:8000/api/graph/mutate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action: "add_edge",
            source: params.source,
            target: params.target,
          }),
        });
        if (response.ok) {
          const data = await response.json();
          if (data.code !== undefined) setCode(data.code);
          processGraphStateInternal(data);
        }
      } catch (error) {
        console.error("Connect failed:", error);
      }
    },
    [nodes, processGraphStateInternal, setCode],
  );

  const addNode = useCallback(async () => {
    const nodeName = window.prompt(
      "Enter a name for the new node:",
      "my_agent",
    );
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
        processGraphStateInternal(data);
      }
    } catch (error) {
      console.error("Add node failed:", error);
    }
  }, [processGraphStateInternal, setCode]);

  const onAddConditionalEdge = useCallback(async (payload) => {
    try {
      const response = await fetch("http://localhost:8000/api/graph/mutate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "add_conditional_edge", payload }),
      });
      if (response.ok) {
        const data = await response.json();
        if (data.code !== undefined) setCode(data.code);
        processGraphStateInternal(data);
      }
    } catch (error) {
      console.error("Add conditional edge failed:", error);
    }
  }, [processGraphStateInternal, setCode]);

  // Keep the handlers ref updated
  useEffect(() => {
    handlersRef.current = {
      onRenameNode,
      onDeleteNode,
      onDeleteEdge,
      onRenameEdgeLabel,
    };
  }, [onRenameNode, onDeleteNode, onDeleteEdge, onRenameEdgeLabel]);

  // Initial load
  useEffect(() => {
    fetch("http://localhost:8000/api/graph")
      .then((res) => res.json())
      .then((data) => {
        if (data.code !== undefined) setCode(data.code);
        processGraphStateInternal(data);
      });
  }, [processGraphStateInternal, setCode]);

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
          processGraphStateInternal(data);
        }
      } catch (error) {
        console.error("Sync failed:", error);
      }
    }, 800);
  };

  return (
    <div className="main-container">
      <div className="graph-container">
        {nodes.length === 0 && (
          <div className="empty-state-container">
            <h2>No Graph Detected</h2>
            <p>Please upload your LangGraph code to get started.</p>
            <button
              className="empty-state-upload-btn"
              onClick={() =>
                document.getElementById("code-upload-input").click()
              }
            >
              📁 Upload LangGraph Code
            </button>
          </div>
        )}
        <div className="controls-container">
          <button className="add-node-btn" onClick={addNode}>
            + Add Node
          </button>
          <button 
            className="add-node-btn" 
            style={{ backgroundColor: "#8b5cf6" }}
            onClick={() => setIsCondModalOpen(true)}
          >
            + Add Conditional Route
          </button>
          <button
            className="add-node-btn"
            style={{ backgroundColor: "#f87171" }}
            onClick={() => {
              // Manually add the END node if it doesn't exist
              setNodes((nds) => {
                if (nds.find((n) => n.id === "__end__")) return nds;
                const endNode = {
                  id: "__end__",
                  type: "startNode",
                  position: { x: 800, y: 200 },
                  data: {
                    label: "END",
                    isEditable: false,
                    deletable: true,
                  },
                };
                return nds.concat(endNode);
              });
            }}
          >
            + END Node
          </button>
          <button
            className="upload-btn"
            onClick={() => document.getElementById("code-upload-input").click()}
          >
            📁 Upload Code
          </button>
          <input
            type="file"
            id="code-upload-input"
            style={{ display: "none" }}
            accept=".py"
            onChange={async (e) => {
              const file = e.target.files[0];
              if (!file) return;
              const formData = new FormData();
              formData.append("file", file);
              const res = await fetch(
                "http://localhost:8000/api/graph/upload",
                { method: "POST", body: formData },
              );
              if (res.ok) {
                const data = await res.json();
                if (data.code !== undefined) setCode(data.code);
                processGraphStateInternal(data);
              }
            }}
          />
        </div>

        <button
          className="toggle-editor-btn"
          onClick={() => setIsEditorCollapsed(!isEditorCollapsed)}
        >
          {isEditorCollapsed ? "← Show Code" : "Hide Code →"}
        </button>

        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={onNodeClick}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView
        >
          <Controls />
          <MiniMap />
          <Background variant="dots" gap={12} size={1} />
        </ReactFlow>
      </div>

      <div className={`editor-sidebar ${isEditorCollapsed ? "collapsed" : ""}`}>
        <div className="editor-header">
          <span>Source Code</span>
        </div>
        <div className="monaco-editor-wrapper">
          <Editor
            height="100%"
            language="python"
            theme="vs-dark"
            value={code}
            onMount={handleEditorDidMount}
            onChange={handleEditorChange}
            options={{
              readOnly: false,
              minimap: { enabled: false },
              fontSize: 14,
              lineNumbers: "on",
              scrollBeyondLastLine: false,
              automaticLayout: true,
            }}
          />
        </div>
      </div>

      <ConditionalRouteModal 
        isOpen={isCondModalOpen}
        onClose={() => setIsCondModalOpen(false)}
        onAdd={onAddConditionalEdge}
        nodes={nodes}
      />
    </div>
  );
}

export default App;
