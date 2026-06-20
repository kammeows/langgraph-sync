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
import ValidationPanel from "./components/ValidationPanel";
import StateSchemaPanel from "./components/StateSchemaPanel";

import "@xyflow/react/dist/style.css";
import "./App.css";
import dagre from "dagre";

const dagreGraph = new dagre.graphlib.Graph();
dagreGraph.setDefaultEdgeLabel(() => ({}));

const nodeWidth = 172;
const nodeHeight = 36;

const getLayoutedElements = (nodes, edges, direction = "TB") => {
  const isHorizontal = direction === "LR";
  dagreGraph.setGraph({ rankdir: direction, nodesep: 70, ranksep: 100 });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  const newNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    return {
      ...node,
      targetPosition: isHorizontal ? "left" : "top",
      sourcePosition: isHorizontal ? "right" : "bottom",
      position: {
        x: nodeWithPosition.x - nodeWidth / 2,
        y: nodeWithPosition.y - nodeHeight / 2,
      },
    };
  });

  return { nodes: newNodes, edges };
};

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
  const [warnings, setWarnings] = useState([]);
  const [stateSchema, setStateSchema] = useState(null);
  const [code, setCode] = useState("");
  const [isEditorCollapsed, setIsEditorCollapsed] = useState(false);
  const [isCondModalOpen, setIsCondModalOpen] = useState(false);
  const [graphsList, setGraphsList] = useState([]);
  const [selectedGraphId, setSelectedGraphId] = useState("");
  const [showEdgeLabels, setShowEdgeLabels] = useState(true);
  const editorRef = useRef(null);

  useEffect(() => {
    fetch("http://localhost:8000/api/graphs")
      .then((res) => res.json())
      .then((data) => {
        if (data && data.length > 0) {
          setGraphsList(data);
          setSelectedGraphId(data[0].id);
        }
      })
      .catch(console.error);
  }, []);

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

  const onUpdateEdgeData = useCallback(
    (id, newData) => {
      setEdges((eds) =>
        eds.map((edge) => {
          if (edge.id === id) {
            return { ...edge, data: { ...edge.data, ...newData } };
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
            width: 20,
            height: 20,
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
            id: edge.id, // Pass ID for updates
            source: edge.source,
            target: edge.target,
            isConditional,
            label: edge.label || (isConditional ? "Conditional Edge" : ""),
            onDelete: (id) => {
              handlers.onDeleteEdge && handlers.onDeleteEdge(id);
            },
            onRenameLabel: onRenameEdgeLabel,
            onUpdateData: onUpdateEdgeData,
            showLabels: showEdgeLabels,
          },
        };
      });

      const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(
        nodesWithHandlers,
        edgesWithHandlers
      );

      // Ensure markerEnd is preserved or re-applied
      const finalEdges = layoutedEdges.map(e => ({
          ...e,
          markerEnd: {
              type: MarkerType.ArrowClosed,
              color: e.source === "__start__" ? "#22c55e" : "#b1b1b7"
          }
      }));

      setNodes(layoutedNodes);
      setEdges(finalEdges);
      if (data.warnings) {
        setWarnings(data.warnings);
      }
      if (data.state_schema) {
        setStateSchema(data.state_schema);
      }
    },
    [onRenameEdgeLabel, setNodes, setEdges, setWarnings, setStateSchema, showEdgeLabels],
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
            graph_id: selectedGraphId,
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
    [processGraphStateInternal, setCode, selectedGraphId],
  );

  const onDeleteNode = useCallback(
    async (id) => {
      if (!window.confirm(`Are you sure you want to delete node "${id}"?`))
        return;
      try {
        const response = await fetch("http://localhost:8000/api/graph/mutate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action: "delete_node",
            node_id: id,
            graph_id: selectedGraphId,
          }),
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
    [processGraphStateInternal, setCode, selectedGraphId],
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
            graph_id: selectedGraphId,
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
    [edges, processGraphStateInternal, setCode, selectedGraphId],
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
            graph_id: selectedGraphId,
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
    [nodes, processGraphStateInternal, setCode, selectedGraphId],
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
        body: JSON.stringify({ action: "add_node", new_id: validName, graph_id: selectedGraphId }),
      });
      if (response.ok) {
        const data = await response.json();
        if (data.code !== undefined) setCode(data.code);
        processGraphStateInternal(data);
      }
    } catch (error) {
      console.error("Add node failed:", error);
    }
  }, [processGraphStateInternal, setCode, selectedGraphId]);

  const onAddConditionalEdge = useCallback(async (payload) => {
    try {
      const response = await fetch("http://localhost:8000/api/graph/mutate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "add_conditional_edge", payload, graph_id: selectedGraphId }),
      });
      if (response.ok) {
        const data = await response.json();
        if (data.code !== undefined) setCode(data.code);
        processGraphStateInternal(data);
      }
    } catch (error) {
      console.error("Add conditional edge failed:", error);
    }
  }, [processGraphStateInternal, setCode, selectedGraphId]);

  // Keep the handlers ref updated
  useEffect(() => {
    handlersRef.current = {
      onRenameNode,
      onDeleteNode,
      onDeleteEdge,
      onRenameEdgeLabel,
    };
  }, [onRenameNode, onDeleteNode, onDeleteEdge, onRenameEdgeLabel]);

  // Fetch graph whenever selectedGraphId changes
  useEffect(() => {
    if (!selectedGraphId) return;
    fetch(`http://localhost:8000/api/graph?graph_id=${selectedGraphId}`)
      .then((res) => res.json())
      .then((data) => {
        if (data.code !== undefined) setCode(data.code);
        processGraphStateInternal(data);
      });
  }, [selectedGraphId, processGraphStateInternal, setCode]);

  // Sync edge labels visibility state to all edge data objects
  useEffect(() => {
    setEdges((eds) =>
      eds.map((edge) => ({
        ...edge,
        data: {
          ...edge.data,
          showLabels: showEdgeLabels,
        },
      }))
    );
  }, [showEdgeLabels, setEdges]);

  const syncTimerRef = useRef(null);
  const handleEditorChange = (value) => {
    setCode(value);
    if (syncTimerRef.current) clearTimeout(syncTimerRef.current);
    syncTimerRef.current = setTimeout(async () => {
      try {
        const response = await fetch("http://localhost:8000/api/graph/sync", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code: value, graph_id: selectedGraphId }),
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
          {graphsList.length > 0 && (
            <select 
              value={selectedGraphId} 
              onChange={(e) => setSelectedGraphId(e.target.value)}
              className="graph-selector"
              style={{ padding: "6px", borderRadius: "4px", marginRight: "10px", backgroundColor: "#2d2d2d", color: "white", border: "1px solid #444" }}
            >
              {graphsList.map(g => (
                <option key={g.id} value={g.id}>{g.id} ({g.file})</option>
              ))}
            </select>
          )}
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
            style={{ backgroundColor: showEdgeLabels ? "#10b981" : "#4b5563" }}
            onClick={() => setShowEdgeLabels(!showEdgeLabels)}
          >
            {showEdgeLabels ? "👁️ Hide Edge Labels" : "👁️ Show Edge Labels"}
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

        <ValidationPanel warnings={warnings} />
        <StateSchemaPanel schema={stateSchema} />
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
