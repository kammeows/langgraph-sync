import { useState, useEffect, useCallback, useRef } from "react";
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  MarkerType,
  useReactFlow,
} from "@xyflow/react";
import Editor from "@monaco-editor/react";

import EditableNode from "./components/EditableNode";
import DeletableEdge from "./components/DeletableEdge";
import SelfLoopEdge from "./components/SelfLoopEdge";
import ConditionalRouteModal from "./components/ConditionalRouteModal";
import PRModal from "./components/PRModal";
import ValidationPanel from "./components/ValidationPanel";
import StateSchemaPanel from "./components/StateSchemaPanel";
import CometLLMInspectorPanel from "./components/CometLLMInspectorPanel";

import "@xyflow/react/dist/style.css";
import "./App.css";
import dagre from "dagre";

const dagreGraph = new dagre.graphlib.Graph();
dagreGraph.setDefaultEdgeLabel(() => ({}));

const nodeWidth = 172;
const nodeHeight = 36;

const getLayoutedElements = (
  nodes,
  edges,
  savedPositions = {},
  direction = "TB",
) => {
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
    const saved = savedPositions[node.id];
    return {
      ...node,
      targetPosition: isHorizontal ? "left" : "top",
      sourcePosition: isHorizontal ? "right" : "bottom",
      position: saved || {
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
  const [stateSchemas, setStateSchemas] = useState([]);
  const [code, setCode] = useState("");
  const [isEditorCollapsed, setIsEditorCollapsed] = useState(false);
  const [isCondModalOpen, setIsCondModalOpen] = useState(false);
  const [isPRModalOpen, setIsPRModalOpen] = useState(false);
  const [graphsList, setGraphsList] = useState([]);
  const [selectedGraphId, setSelectedGraphId] = useState("");
  const [showEdgeLabels, setShowEdgeLabels] = useState(true);
  const [cometModels, setCometModels] = useState([]);
  const editorRef = useRef(null);
  const rawGraphDataRef = useRef(null);

  const { getViewport, setViewport, fitView } = useReactFlow();
  const restoredGraphIdRef = useRef(null);
  const highlightedGraphIdRef = useRef(null);

  // AI Copilot and resizable panel states
  const [selectedNodeInfo, setSelectedNodeInfo] = useState(null);
  const [editorHeightPercent, setEditorHeightPercent] = useState(50);
  const [isResizing, setIsResizing] = useState(false);
  const sidebarRef = useRef(null);
  const [copilotMessages, setCopilotMessages] = useState([
    {
      sender: "copilot",
      content:
        "Hello! I'm your LangGraph Autopilot. Ask me to make structural graph changes, like adding/renaming nodes, or connecting them together.",
    },
  ]);
  const [copilotInput, setCopilotInput] = useState("");
  const [isCopilotLoading, setIsCopilotLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const handleDividerMouseDown = useCallback((e) => {
    e.preventDefault();
    setIsResizing(true);
  }, []);

  useEffect(() => {
    if (!isResizing) return;

    const handleMouseMove = (e) => {
      if (!sidebarRef.current) return;
      const rect = sidebarRef.current.getBoundingClientRect();
      const relativeY = e.clientY - rect.top;
      const percentage = Math.max(
        0,
        Math.min(100, (relativeY / rect.height) * 100),
      );
      setEditorHeightPercent(percentage);
    };

    const handleMouseUp = () => {
      setIsResizing(false);
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isResizing]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [copilotMessages, isCopilotLoading]);

  useEffect(() => {
    fetch("http://localhost:8000/api/graphs")
      .then((res) => res.json())
      .then((data) => {
        if (data && data.length > 0) {
          setGraphsList(data);
          const savedGraphId = localStorage.getItem("selected-graph-id");
          const hasSavedGraph =
            savedGraphId && data.some((g) => g.id === savedGraphId);
          setSelectedGraphId(hasSavedGraph ? savedGraphId : data[0].id);
        }
      })
      .catch(console.error);
  }, []);

  const selectLinesInEditor = useCallback((node) => {
    if (!node || !editorRef.current) return;
    if (node.data && node.data.lines) {
      const [startLine, endLine] = node.data.lines;
      console.log(`Highlighting lines ${startLine} to ${endLine}`);
      editorRef.current.revealLineInCenter(startLine);
      const model = editorRef.current.getModel();
      if (!model) return;
      const maxColumn = model.getLineMaxColumn(endLine);
      editorRef.current.setSelection({
        startLineNumber: startLine,
        startColumn: 1,
        endLineNumber: endLine,
        endColumn: maxColumn,
      });
    } else if (node.data && node.data.functionName) {
      const model = editorRef.current.getModel();
      if (!model) return;
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
      }
    }
  }, []);

  const handleEditorDidMount = (editor) => {
    editorRef.current = editor;
    if (selectedGraphId && nodes.length > 0) {
      const selectedNode = nodes.find((n) => n.selected);
      if (selectedNode) {
        selectLinesInEditor(selectedNode);
        highlightedGraphIdRef.current = selectedGraphId;
      }
    }
  };

  const onNodeClick = useCallback(
    (event, node) => {
      console.log("Node clicked data:", node.data);
      setSelectedNodeInfo(node);
      selectLinesInEditor(node);
      if (isEditorCollapsed) setIsEditorCollapsed(false);
    },
    [selectLinesInEditor, isEditorCollapsed],
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
      const nodesWithHandlers = data.nodes.map((node) => ({
        ...node,
        data: {
          ...node.data,
          type: node.type,
          onDelete: (id) => {
            if (id === "__start__") return;
            handlersRef.current?.onDeleteNode &&
              handlersRef.current.onDeleteNode(id);
          },
          onRename: (id, label) => {
            if (id === "__start__" || id === "__end__") return;
            handlersRef.current?.onRenameNode &&
              handlersRef.current.onRenameNode(id, label);
          },
          onSubNodeClick: (subNode) => {
            const subNodeWithData = {
              id: subNode.id,
              data: {
                ...subNode.data,
                isSubNode: true
              }
            };
            setSelectedNodeInfo(subNodeWithData);
            selectLinesInEditor(subNode);
          },
          onSubNodeRename: (id, label) => {
            handlersRef.current?.onRenameNode &&
              handlersRef.current.onRenameNode(id, label);
          },
          onSubNodeDelete: (id) => {
            handlersRef.current?.onDeleteNode &&
              handlersRef.current.onDeleteNode(id);
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
              handlersRef.current?.onDeleteEdge &&
                handlersRef.current.onDeleteEdge(id);
            },
            onRenameLabel: onRenameEdgeLabel,
            onUpdateData: onUpdateEdgeData,
            showLabels: showEdgeLabels,
          },
        };
      });

      // Cache the raw data for resetting the layout back to defaults
      rawGraphDataRef.current = data;

      const savedPositions = selectedGraphId
        ? JSON.parse(
            localStorage.getItem(`node-positions-${selectedGraphId}`),
          ) || {}
        : {};

      const { nodes: layoutedNodes, edges: layoutedEdges } =
        getLayoutedElements(
          nodesWithHandlers,
          edgesWithHandlers,
          savedPositions,
        );

      const savedSelectedNodeId = selectedGraphId
        ? localStorage.getItem(`selected-node-${selectedGraphId}`)
        : null;

      const finalNodes = layoutedNodes.map((node) => ({
        ...node,
        selected: node.id === savedSelectedNodeId,
      }));

      const previouslySelected = finalNodes.find((n) => n.selected);
      if (previouslySelected) {
        setSelectedNodeInfo(previouslySelected);
      } else {
        setSelectedNodeInfo(null);
      }

      // Ensure markerEnd is preserved or re-applied
      const finalEdges = layoutedEdges.map((e) => ({
        ...e,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: e.source === "__start__" ? "#22c55e" : "#b1b1b7",
        },
      }));

      setNodes(finalNodes);
      setEdges(finalEdges);
      if (data.warnings) {
        setWarnings(data.warnings);
      }
      if (data.state_schema) {
        setStateSchema(data.state_schema);
      }
      if (data.state_schemas) {
        setStateSchemas(data.state_schemas);
      } else if (data.state_schema) {
        setStateSchemas([data.state_schema]);
      } else {
        setStateSchemas([]);
      }
    },
    [
      onRenameEdgeLabel,
      onUpdateEdgeData,
      setNodes,
      setEdges,
      setWarnings,
      setStateSchema,
      setStateSchemas,
      showEdgeLabels,
      selectedGraphId,
    ],
  );

  const handleSendCopilotMessage = useCallback(
    async (textToPost) => {
      const text = textToPost || copilotInput;
      if (!text.trim() || !selectedGraphId) return;

      setCopilotMessages((prev) => [
        ...prev,
        { sender: "user", content: text },
      ]);
      if (!textToPost) setCopilotInput("");
      setIsCopilotLoading(true);

      try {
        const response = await fetch("http://localhost:8000/api/copilot/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query: text,
            graph_id: selectedGraphId,
            history: copilotMessages,
          }),
        });

        if (response.ok) {
          const data = await response.json();
          if (data.success) {
            setCopilotMessages((prev) => [
              ...prev,
              { sender: "copilot", content: data.message },
            ]);
            if (data.graph) {
              if (data.graph.code !== undefined) setCode(data.graph.code);
              processGraphStateInternal(data.graph);
            }
          } else {
            setCopilotMessages((prev) => [
              ...prev,
              { sender: "copilot", content: data.message, isError: true },
            ]);
          }
        } else {
          setCopilotMessages((prev) => [
            ...prev,
            {
              sender: "copilot",
              content: "Failed to connect to the Copilot service.",
              isError: true,
            },
          ]);
        }
      } catch (error) {
        console.error("Copilot error:", error);
        setCopilotMessages((prev) => [
          ...prev,
          {
            sender: "copilot",
            content: "Error connecting to AI Copilot: " + error.message,
            isError: true,
          },
        ]);
      } finally {
        setIsCopilotLoading(false);
      }
    },
    [copilotInput, selectedGraphId, setCode, processGraphStateInternal],
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

      if (
        !window.confirm(
          `Are you sure you want to delete the edge from "${edge.source}" to "${edge.target}"?`,
        )
      ) {
        return;
      }

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

  const onEdgesDelete = useCallback(
    async (deletedEdges) => {
      const activeNodeIds = new Set(nodes.map((n) => n.id));
      for (const edge of deletedEdges) {
        if (
          !activeNodeIds.has(edge.source) ||
          !activeNodeIds.has(edge.target)
        ) {
          continue;
        }
        if (
          !window.confirm(
            `Are you sure you want to delete the edge from "${edge.source}" to "${edge.target}"?`,
          )
        ) {
          // Restore local edge state from backend
          fetch(`http://localhost:8000/api/graph?graph_id=${selectedGraphId}`)
            .then((res) => res.json())
            .then((data) => processGraphStateInternal(data))
            .catch(console.error);
          continue;
        }
        try {
          const response = await fetch(
            "http://localhost:8000/api/graph/mutate",
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                action: "delete_edge",
                source: edge.source,
                target: edge.target,
                payload: { condition: edge.data?.condition },
                graph_id: selectedGraphId,
              }),
            },
          );
          if (response.ok) {
            const data = await response.json();
            if (data.code !== undefined) setCode(data.code);
            processGraphStateInternal(data);
          }
        } catch (error) {
          console.error("Delete edge failed:", error);
        }
      }
    },
    [nodes, selectedGraphId, processGraphStateInternal, setCode],
  );

  const onNodesDelete = useCallback(
    async (deletedNodes) => {
      for (const node of deletedNodes) {
        if (node.id === "__start__" || node.id === "__end__") {
          continue;
        }
        if (
          !window.confirm(`Are you sure you want to delete node "${node.id}"?`)
        ) {
          // Restore local node state from backend
          fetch(`http://localhost:8000/api/graph?graph_id=${selectedGraphId}`)
            .then((res) => res.json())
            .then((data) => processGraphStateInternal(data))
            .catch(console.error);
          continue;
        }
        try {
          const response = await fetch(
            "http://localhost:8000/api/graph/mutate",
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                action: "delete_node",
                node_id: node.id,
                graph_id: selectedGraphId,
              }),
            },
          );
          if (response.ok) {
            const data = await response.json();
            if (data.code !== undefined) setCode(data.code);
            processGraphStateInternal(data);
          }
        } catch (error) {
          console.error("Delete node failed:", error);
        }
      }
    },
    [selectedGraphId, processGraphStateInternal, setCode],
  );

  const onConnect = useCallback(
    async (params) => {
      console.log("Connect params:", params);

      // Prevent connections to/from virtual sub-tool nodes
      const sourceNode = nodes.find((n) => n.id === params.source);
      const targetNode = nodes.find((n) => n.id === params.target);

      if (
        sourceNode?.type === "subToolNode" ||
        targetNode?.type === "subToolNode"
      ) {
        alert(
          "You cannot manually connect to or from virtual sub-tool nodes. These are inferred from function calls in your code.",
        );
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
        body: JSON.stringify({
          action: "add_node",
          new_id: validName,
          graph_id: selectedGraphId,
        }),
      });
      if (response.ok) {
        const data = await response.json();
        if (data.code !== undefined) setCode(data.code);
        processGraphStateInternal(data);
      } else if (response.status === 409) {
        const errData = await response.json();
        if (
          window.confirm(
            errData.detail ||
              "Implementation already exists. Add this node and tie it to the current implementation?",
          )
        ) {
          // Retry with use_existing: true
          const retryResponse = await fetch(
            "http://localhost:8000/api/graph/mutate",
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                action: "add_node",
                new_id: validName,
                graph_id: selectedGraphId,
                payload: { use_existing: true },
              }),
            },
          );
          if (retryResponse.ok) {
            const data = await retryResponse.json();
            if (data.code !== undefined) setCode(data.code);
            processGraphStateInternal(data);
          } else {
            const finalErr = await retryResponse.json();
            alert(finalErr.detail || "Failed to add node.");
          }
        }
      } else {
        const errData = await response.json();
        alert(errData.detail || "Failed to add node.");
      }
    } catch (error) {
      console.error("Add node failed:", error);
    }
  }, [processGraphStateInternal, setCode, selectedGraphId]);

  const onAddConditionalEdge = useCallback(
    async (payload) => {
      try {
        const response = await fetch("http://localhost:8000/api/graph/mutate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action: "add_conditional_edge",
            payload,
            graph_id: selectedGraphId,
          }),
        });
        if (response.ok) {
          const data = await response.json();
          if (data.code !== undefined) setCode(data.code);
          processGraphStateInternal(data);
        }
      } catch (error) {
        console.error("Add conditional edge failed:", error);
      }
    },
    [processGraphStateInternal, setCode, selectedGraphId],
  );

  const handleModifyNodeModel = useCallback(
    async (functionName, newModel) => {
      try {
        const response = await fetch("http://localhost:8000/api/graph/mutate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action: "change_node_model",
            graph_id: selectedGraphId,
            node_id: selectedNodeInfo?.id,
            payload: {
              function_name: functionName,
              model: newModel,
            },
          }),
        });

        if (response.ok) {
          const data = await response.json();
          if (data.code !== undefined) setCode(data.code);
          processGraphStateInternal(data);

          // Update selectedNodeInfo in UI state so it shows updated model immediately
          if (selectedNodeInfo) {
            const updatedNode = data.nodes.find((n) => n.id === selectedNodeInfo.id);
            if (updatedNode) {
              setSelectedNodeInfo(updatedNode);
            }
          }
        } else {
          const errData = await response.json();
          alert(errData.detail || "Failed to update node model.");
        }
      } catch (error) {
        console.error("Failed to update node model:", error);
      }
    },
    [selectedGraphId, selectedNodeInfo, setCode, processGraphStateInternal]
  );

  const handleInsertBoilerplate = useCallback(
    async (functionName, model, isComet) => {
      try {
        const response = await fetch("http://localhost:8000/api/graph/mutate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action: "add_llm_boilerplate",
            graph_id: selectedGraphId,
            payload: {
              function_name: functionName,
              model: model,
              is_comet: isComet,
            },
          }),
        });

        if (response.ok) {
          const data = await response.json();
          if (data.code !== undefined) setCode(data.code);
          processGraphStateInternal(data);

          if (selectedNodeInfo) {
            const updatedNode = data.nodes.find((n) => n.id === selectedNodeInfo.id);
            if (updatedNode) {
              setSelectedNodeInfo(updatedNode);
            }
          }
        } else {
          const errData = await response.json();
          alert(errData.detail || "Failed to add LLM boilerplate.");
        }
      } catch (error) {
        console.error("Failed to add LLM boilerplate:", error);
      }
    },
    [selectedGraphId, selectedNodeInfo, setCode, processGraphStateInternal]
  );

  const handleRemoveLLMInvocation = useCallback(
    async (functionName) => {
      if (!functionName) return;
      if (!window.confirm(`Are you sure you want to completely delete the LLM invocation code from function "${functionName}"? This will modify your Python source file.`)) return;
      try {
        const response = await fetch("http://localhost:8000/api/graph/mutate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action: "remove_llm_invocation",
            graph_id: selectedGraphId,
            payload: {
              function_name: functionName,
            },
          }),
        });

        if (response.ok) {
          const data = await response.json();
          if (data.code !== undefined) setCode(data.code);
          processGraphStateInternal(data);

          if (selectedNodeInfo) {
            const updatedNode = data.nodes.find((n) => n.id === selectedNodeInfo.id);
            if (updatedNode) {
              setSelectedNodeInfo(updatedNode);
            }
          }
        } else {
          const errData = await response.json();
          alert(errData.detail || "Failed to remove LLM invocation.");
        }
      } catch (error) {
        console.error("Failed to remove LLM invocation:", error);
      }
    },
    [selectedGraphId, selectedNodeInfo, setCode, processGraphStateInternal]
  );

  // Keep the handlers ref updated
  useEffect(() => {
    handlersRef.current = {
      onRenameNode,
      onDeleteNode,
      onDeleteEdge,
      onRenameEdgeLabel,
    };
  }, [onRenameNode, onDeleteNode, onDeleteEdge, onRenameEdgeLabel]);

  // Fetch Comet API models on app load
  useEffect(() => {
    const fetchCometModels = async () => {
      try {
        const response = await fetch("http://localhost:8000/api/comet/models");
        if (response.ok) {
          const data = await response.json();
          if (data.models && data.models.length > 0) {
            setCometModels(data.models);
          }
        }
      } catch (error) {
        console.error("Failed to fetch Comet models:", error);
      }
    };
    fetchCometModels();
  }, []);

  // Fetch graph whenever selectedGraphId changes
  useEffect(() => {
    if (!selectedGraphId) return;
    localStorage.setItem("selected-graph-id", selectedGraphId);

    // Reset viewport and highlight restoration flags for the new graph
    restoredGraphIdRef.current = null;
    highlightedGraphIdRef.current = null;

    fetch(`http://localhost:8000/api/graph?graph_id=${selectedGraphId}`)
      .then((res) => res.json())
      .then((data) => {
        if (data.code !== undefined) setCode(data.code);
        processGraphStateInternal(data);
      });
  }, [selectedGraphId, processGraphStateInternal, setCode]);

  // Restore viewport when graph is loaded and nodes are available
  useEffect(() => {
    if (!selectedGraphId || nodes.length === 0) return;
    if (restoredGraphIdRef.current === selectedGraphId) return;

    restoredGraphIdRef.current = selectedGraphId;

    const savedViewport = localStorage.getItem(`viewport-${selectedGraphId}`);
    if (savedViewport) {
      try {
        const parsed = JSON.parse(savedViewport);
        setTimeout(() => {
          setViewport(parsed);
        }, 0);
      } catch (e) {
        console.error("Failed to restore viewport", e);
      }
    } else {
      setTimeout(() => {
        fitView({ padding: 0.2 });
      }, 0);
    }
  }, [selectedGraphId, nodes, setViewport, fitView]);

  // Auto-highlight selected node in editor on graph change / editor mount
  useEffect(() => {
    if (!editorRef.current || !selectedGraphId || nodes.length === 0) return;
    if (highlightedGraphIdRef.current === selectedGraphId) return;

    const selectedNode = nodes.find((n) => n.selected);
    if (selectedNode) {
      selectLinesInEditor(selectedNode);
    }
    highlightedGraphIdRef.current = selectedGraphId;
  }, [selectedGraphId, nodes, selectLinesInEditor]);

  // Sync edge labels visibility state to all edge data objects
  useEffect(() => {
    setEdges((eds) =>
      eds.map((edge) => ({
        ...edge,
        data: {
          ...edge.data,
          showLabels: showEdgeLabels,
        },
      })),
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

  const onSelectionChange = useCallback(
    ({ nodes: selectedNodes }) => {
      if (!selectedGraphId) return;
      const selectedNode = selectedNodes.find((n) => n.selected);
      if (selectedNode) {
        setSelectedNodeInfo(selectedNode);
        localStorage.setItem(
          `selected-node-${selectedGraphId}`,
          selectedNode.id,
        );
      } else {
        setSelectedNodeInfo((prev) => {
          if (prev && !selectedNodes.some(n => n.id === prev.id) && !prev.data?.isSubNode) {
            return null;
          }
          return prev;
        });
        localStorage.removeItem(`selected-node-${selectedGraphId}`);
      }
    },
    [selectedGraphId],
  );

  const onMoveEnd = useCallback(() => {
    if (!selectedGraphId) return;
    try {
      const viewport = getViewport();
      localStorage.setItem(
        `viewport-${selectedGraphId}`,
        JSON.stringify(viewport),
      );
    } catch (e) {
      console.error("Error getting viewport:", e);
    }
  }, [selectedGraphId, getViewport]);

  const onNodeDragStop = useCallback(() => {
    if (!selectedGraphId) return;
    setNodes((currentNodes) => {
      const positions = {};
      currentNodes.forEach((n) => {
        positions[n.id] = n.position;
      });
      localStorage.setItem(
        `node-positions-${selectedGraphId}`,
        JSON.stringify(positions),
      );
      return currentNodes;
    });
  }, [selectedGraphId, setNodes]);

  const handleResetLayout = useCallback(() => {
    if (!selectedGraphId) return;
    localStorage.removeItem(`node-positions-${selectedGraphId}`);
    localStorage.removeItem(`selected-node-${selectedGraphId}`);
    localStorage.removeItem(`viewport-${selectedGraphId}`);

    // Clear selection state in nodes
    setNodes((nds) => nds.map((n) => ({ ...n, selected: false })));

    if (rawGraphDataRef.current) {
      processGraphStateInternal(rawGraphDataRef.current);
    }

    // Reset viewport to default (fitView)
    setTimeout(() => {
      fitView({ padding: 0.2 });
    }, 0);
  }, [selectedGraphId, processGraphStateInternal, setNodes, fitView]);

  return (
    <div className="main-container">
      <div className="graph-container">
        {nodes.length === 0 && (
          <div className="empty-state-container">
            <h2>No Graph Detected</h2>
            <p>Please configure a valid LangGraph file in your project configuration to get started.</p>
          </div>
        )}
        <div className="controls-container">
          {graphsList.length > 0 && (
            <select
              value={selectedGraphId}
              onChange={(e) => setSelectedGraphId(e.target.value)}
              className="graph-selector"
              style={{
                padding: "4px 8px",
                fontSize: "11px",
                borderRadius: "4px",
                marginRight: "10px",
                backgroundColor: "#2d2d2d",
                color: "white",
                border: "1px solid #444",
              }}
            >
              {graphsList.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.id} ({g.file})
                </option>
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
            style={{ backgroundColor: "#e11d48" }}
            onClick={handleResetLayout}
          >
            🔄 Reset Layout
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
          onNodesDelete={onNodesDelete}
          onEdgesDelete={onEdgesDelete}
          onNodeClick={onNodeClick}
          onNodeDragStop={onNodeDragStop}
          onSelectionChange={onSelectionChange}
          onMoveEnd={onMoveEnd}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView={false}
        >
          <Controls />
          <MiniMap />
          <Background variant="dots" gap={12} size={1} />
        </ReactFlow>

        <div className="canvas-side-panels">
          {selectedNodeInfo && (
            <CometLLMInspectorPanel
              node={selectedNodeInfo}
              onClose={() => setSelectedNodeInfo(null)}
              onModelChange={handleModifyNodeModel}
              onAddBoilerplate={handleInsertBoilerplate}
              onRemoveLLM={handleRemoveLLMInvocation}
              cometModels={cometModels}
            />
          )}
          {stateSchemas && stateSchemas.length > 0 && (
            <div className="state-schemas-container">
              {stateSchemas.map((schema, index) => (
                <StateSchemaPanel key={schema.name || index} schema={schema} />
              ))}
            </div>
          )}
          <ValidationPanel warnings={warnings} />
        </div>
      </div>

      <div
        ref={sidebarRef}
        className={`editor-sidebar ${isEditorCollapsed ? "collapsed" : ""}`}
      >
        <div className="sidebar-panel-container">
          {/* 1. Source Code Panel */}
          <div
            className="editor-panel"
            style={
              editorHeightPercent === 0
                ? { height: 0, display: "none" }
                : editorHeightPercent === 100
                  ? { height: "100%" }
                  : { height: `${editorHeightPercent}%` }
            }
          >
            <div className="editor-header">
              <span>Source Code</span>
              <div style={{ display: "flex", gap: "5px" }}>
                {editorHeightPercent < 100 && (
                  <button
                    className="panel-action-btn"
                    onClick={() => setEditorHeightPercent(100)}
                    title="Maximize Code Editor"
                  >
                    🗖
                  </button>
                )}
                {editorHeightPercent > 0 && editorHeightPercent < 100 && (
                  <button
                    className="panel-action-btn"
                    onClick={() => setEditorHeightPercent(0)}
                    title="Collapse Code Editor"
                  >
                    🗕
                  </button>
                )}
              </div>
            </div>
            <div
              className="monaco-editor-wrapper"
              style={{ height: "calc(100% - 40px)" }}
            >
              <Editor
                height="100%"
                language="python"
                theme="vs-dark"
                value={code}
                onMount={handleEditorDidMount}
                onChange={handleEditorChange}
                options={{
                  readOnly: true,
                  minimap: { enabled: false },
                  fontSize: 12,
                  lineNumbers: "on",
                  scrollBeyondLastLine: false,
                  automaticLayout: true,
                }}
              />
            </div>
          </div>

          {/* 2. Draggable Divider */}
          {editorHeightPercent > 0 && editorHeightPercent < 100 && (
            <div
              className={`sidebar-divider ${isResizing ? "dragging" : ""}`}
              onMouseDown={handleDividerMouseDown}
            />
          )}

          {/* 3. AI Copilot Panel */}
          <div
            className="copilot-panel"
            style={
              editorHeightPercent === 100
                ? { display: "none" }
                : editorHeightPercent === 0
                  ? { height: "100%" }
                  : { height: `${100 - editorHeightPercent}%` }
            }
          >
            <div className="editor-header">
              <span>AI Copilot</span>
              <div style={{ display: "flex", gap: "8px" }}>
                {editorHeightPercent > 0 && (
                  <button
                    className="panel-action-btn"
                    onClick={() => setEditorHeightPercent(0)}
                    title="Maximize AI Copilot"
                  >
                    🗖 Maximize
                  </button>
                )}
                {editorHeightPercent < 100 && editorHeightPercent > 0 && (
                  <button
                    className="panel-action-btn"
                    onClick={() => setEditorHeightPercent(100)}
                    title="Collapse AI Copilot"
                  >
                    🗕 Collapse
                  </button>
                )}
                {editorHeightPercent !== 50 && (
                  <button
                    className="panel-action-btn"
                    onClick={() => setEditorHeightPercent(50)}
                    title="Split 50/50"
                  >
                    ⚖ Split 50/50
                  </button>
                )}
              </div>
            </div>
            <div className="copilot-chat-container">
              <div className="copilot-messages">
                {copilotMessages.map((msg, index) => (
                  <div
                    key={index}
                    className={`copilot-message ${msg.sender} ${msg.isError ? "error" : ""}`}
                  >
                    {msg.content}
                  </div>
                ))}
                {isCopilotLoading && (
                  <div className="typing-indicator">
                    <div className="typing-dot" />
                    <div className="typing-dot" />
                    <div className="typing-dot" />
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>

              <div className="copilot-input-area">
                <div className="copilot-suggestions">
                  <button
                    className="suggestion-chip"
                    onClick={() =>
                      handleSendCopilotMessage(
                        "Add a node called database_lookup",
                      )
                    }
                  >
                    ➕ Add node 'database_lookup'
                  </button>
                  <button
                    className="suggestion-chip"
                    onClick={() =>
                      handleSendCopilotMessage("Connect router_v2 to tool")
                    }
                  >
                    🔗 Connect 'router_v2' to 'tool'
                  </button>
                  <button
                    className="suggestion-chip"
                    onClick={() =>
                      handleSendCopilotMessage(
                        "Rename researcherss to researcher",
                      )
                    }
                  >
                    📝 Rename 'researcherss'
                  </button>
                  <button
                    className="suggestion-chip"
                    onClick={() =>
                      handleSendCopilotMessage(
                        "Modify prompt inside research_agent",
                      )
                    }
                  >
                    ⚠️ Test business logic block
                  </button>
                </div>
                <div className="copilot-input-wrapper">
                  <input
                    type="text"
                    className="copilot-input"
                    placeholder="Ask copilot to change graph structure..."
                    value={copilotInput}
                    onChange={(e) => setCopilotInput(e.target.value)}
                    onKeyDown={(e) =>
                      e.key === "Enter" && handleSendCopilotMessage()
                    }
                    disabled={isCopilotLoading}
                  />
                  <button
                    className="copilot-send-btn"
                    onClick={() => handleSendCopilotMessage()}
                    disabled={isCopilotLoading || !copilotInput.trim()}
                  >
                    Send
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <ConditionalRouteModal
        isOpen={isCondModalOpen}
        onClose={() => setIsCondModalOpen(false)}
        onAdd={onAddConditionalEdge}
        nodes={nodes}
      />

      <PRModal isOpen={isPRModalOpen} onClose={() => setIsPRModalOpen(false)} />
    </div>
  );
}

export default App;
