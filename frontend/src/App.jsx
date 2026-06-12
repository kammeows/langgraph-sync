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

        // Reveal the start line in the center of the editor
        editorRef.current.revealLineInCenter(startLine);

        // Set selection to highlight the code range
        const model = editorRef.current.getModel();
        const maxColumn = model.getLineMaxColumn(endLine);

        editorRef.current.setSelection({
          startLineNumber: startLine,
          startColumn: 1,
          endLineNumber: endLine,
          endColumn: maxColumn,
        });

        // Expand sidebar if it's collapsed
        if (isEditorCollapsed) {
          setIsEditorCollapsed(false);
        }
      } else if (node.data && node.data.functionName && editorRef.current) {
        console.log("Lines missing, searching for functionName:", node.data.functionName);
        const model = editorRef.current.getModel();
        const matches = model.findMatches(`def ${node.data.functionName}`, true, false, true, null, true);
        
        if (matches.length > 0) {
          const match = matches[0];
          editorRef.current.revealLineInCenter(match.range.startLineNumber);
          editorRef.current.setSelection(match.range);
          if (isEditorCollapsed) setIsEditorCollapsed(false);
        }
      } else {
        console.warn("No line data or function name found for node:", node.id);
      }
    },
    [isEditorCollapsed],
  );

  const onDeleteNode = useCallback(
    (id) => {
      setNodes((nds) => nds.filter((node) => node.id !== id));
      setEdges((eds) =>
        eds.filter((edge) => edge.source !== id && edge.target !== id),
      );
    },
    [setNodes, setEdges],
  );

  const onRenameNode = useCallback(
    (id, newLabel) => {
      setNodes((nds) =>
        nds.map((node) => {
          if (node.id === id) {
            return { ...node, data: { ...node.data, label: newLabel } };
          }
          return node;
        }),
      );
    },
    [setNodes],
  );

  const onDeleteEdge = useCallback(
    (id) => {
      setEdges((eds) => eds.filter((edge) => edge.id !== id));
    },
    [setEdges],
  );

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

  const processGraphData = useCallback(
    (data) => {
      console.log("Received graph data:", data);

      // Inject handlers into nodes
      const nodesWithHandlers = data.nodes.map((node) => ({
        ...node,
        data: {
          ...node.data,
          type: node.type,
          onDelete: onDeleteNode,
          onRename: onRenameNode,
        },
      }));

      // Inject handlers and styling into edges
      const edgesWithHandlers = data.edges.map((edge) => {
        const isConditional = edge.id.includes("-cond") || !!edge.label;
        return {
          ...edge,
          type: "deletable",
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 20,
            height: 20,
            color: "#b1b1b7",
          },
          style: {
            strokeWidth: 2,
            stroke: "#b1b1b7",
            ...edge.style,
          },
          data: {
            ...edge.data,
            isConditional,
            label: edge.label || (isConditional ? "Conditional Edge" : ""),
            onDelete: onDeleteEdge,
            onRenameLabel: onRenameEdgeLabel,
          },
        };
      });

      setNodes(nodesWithHandlers);
      setEdges(edgesWithHandlers);

      if (data.code !== undefined) {
        console.log("Setting code state, length:", data.code.length);
        console.log(JSON.stringify(data.code));
        setCode(data.code);
      }
    },
    [
      onDeleteNode,
      onRenameNode,
      onDeleteEdge,
      onRenameEdgeLabel,
      setNodes,
      setEdges,
      setCode,
    ],
  );

  useEffect(() => {
    const fetchGraph = async () => {
      try {
        const response = await fetch("http://localhost:8000/api/graph");
        const data = await response.json();
        processGraphData(data);
      } catch (error) {
        console.error("Error fetching graph data:", error);
      }
    };

    fetchGraph();
  }, [processGraphData]);

  const onUploadClick = () => {
    document.getElementById("code-upload-input").click();
  };

  const onFileChange = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch("http://localhost:8000/api/graph/upload", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json();
        alert(`Upload failed: ${errorData.detail}`);
        return;
      }

      const data = await response.json();
      processGraphData(data);
    } catch (error) {
      console.error("Error uploading file:", error);
      alert("Error uploading file");
    }

    event.target.value = "";
  };

  const onConnect = useCallback(
    (params) => {
      const newEdge = {
        ...params,
        type: "deletable",
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 20,
          height: 20,
          color: "#b1b1b7",
        },
        style: {
          strokeWidth: 2,
          stroke: "#b1b1b7",
        },
        data: {
          isConditional: false,
          label: "",
          onDelete: onDeleteEdge,
          onRenameLabel: onRenameEdgeLabel,
        },
      };
      setEdges((eds) => addEdge(newEdge, eds));
    },
    [setEdges, onDeleteEdge, onRenameEdgeLabel],
  );

  const addNode = useCallback(() => {
    const id = `node_${Date.now()}`;
    const newNode = {
      id,
      type: "agentNode",
      position: { x: Math.random() * 400, y: Math.random() * 400 },
      data: {
        label: "Node",
        type: "agentNode",
        onDelete: onDeleteNode,
        onRename: onRenameNode,
      },
    };
    setNodes((nds) => nds.concat(newNode));
  }, [setNodes, onDeleteNode, onRenameNode]);

  return (
    <div className="main-container">
      <div className="graph-container">
        {nodes.length === 0 && (
          <div className="empty-state-container">
            <h2>No Graph Detected</h2>
            <p>Please upload your LangGraph code to get started.</p>
            <button className="empty-state-upload-btn" onClick={onUploadClick}>
              📁 Upload LangGraph Code
            </button>
          </div>
        )}
        <div className="controls-container">
          <button className="add-node-btn" onClick={addNode}>
            + Add Node
          </button>
          <button className="upload-btn" onClick={onUploadClick}>
            📁 Upload Code
          </button>
          <input
            type="file"
            id="code-upload-input"
            style={{ display: "none" }}
            accept=".py"
            onChange={onFileChange}
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
            // defaultLanguage="python"
            theme="vs-dark"
            value={code}
            onMount={handleEditorDidMount}
            options={{
              readOnly: true,
              minimap: { enabled: false },
              fontSize: 14,
              lineNumbers: "on",
              scrollBeyondLastLine: false,
              automaticLayout: true,
            }}
          />
        </div>
      </div>
    </div>
  );
}

export default App;
