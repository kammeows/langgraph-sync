import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  addEdge,
  MarkerType,
} from '@xyflow/react';

import EditableNode from './components/EditableNode';
import DeletableEdge from './components/DeletableEdge';

import '@xyflow/react/dist/style.css';
import './App.css';

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

  const onDeleteNode = useCallback((id) => {
    setNodes((nds) => nds.filter((node) => node.id !== id));
    setEdges((eds) => eds.filter((edge) => edge.source !== id && edge.target !== id));
  }, [setNodes, setEdges]);

  const onRenameNode = useCallback((id, newLabel) => {
    setNodes((nds) =>
      nds.map((node) => {
        if (node.id === id) {
          return { ...node, data: { ...node.data, label: newLabel } };
        }
        return node;
      })
    );
  }, [setNodes]);

  const onDeleteEdge = useCallback((id) => {
    setEdges((eds) => eds.filter((edge) => edge.id !== id));
  }, [setEdges]);

  const onRenameEdgeLabel = useCallback((id, newLabel) => {
    setEdges((eds) =>
      eds.map((edge) => {
        if (edge.id === id) {
          return { ...edge, data: { ...edge.data, label: newLabel } };
        }
        return edge;
      })
    );
  }, [setEdges]);

  useEffect(() => {
    const fetchGraph = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/graph');
        const data = await response.json();
        
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
          const isConditional = edge.id.includes('-cond') || !!edge.label;
          return {
            ...edge,
            type: 'deletable',
            markerEnd: {
              type: MarkerType.ArrowClosed,
              width: 20,
              height: 20,
              color: '#b1b1b7',
            },
            style: {
              strokeWidth: 2,
              stroke: '#b1b1b7',
              ...edge.style,
            },
            data: {
              ...edge.data,
              isConditional,
              label: edge.label || (isConditional ? 'Conditional Edge' : ''),
              onDelete: onDeleteEdge,
              onRenameLabel: onRenameEdgeLabel,
            },
          };
        });

        setNodes(nodesWithHandlers);
        setEdges(edgesWithHandlers);
      } catch (error) {
        console.error('Error fetching graph data:', error);
      }
    };

    fetchGraph();
  }, [setNodes, setEdges, onDeleteNode, onRenameNode, onDeleteEdge, onRenameEdgeLabel]);

  const onConnect = useCallback(
    (params) => {
      const newEdge = {
        ...params,
        type: 'deletable',
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 20,
          height: 20,
          color: '#b1b1b7',
        },
        style: {
          strokeWidth: 2,
          stroke: '#b1b1b7',
        },
        data: {
          isConditional: false,
          label: '',
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
      type: 'agentNode',
      position: { x: Math.random() * 400, y: Math.random() * 400 },
      data: {
        label: 'Node',
        type: 'agentNode',
        onDelete: onDeleteNode,
        onRename: onRenameNode,
      },
    };
    setNodes((nds) => nds.concat(newNode));
  }, [setNodes, onDeleteNode, onRenameNode]);

  return (
    <div style={{ width: '100vw', height: '100vh' }}>
      <div className="controls-container">
        <button className="add-node-btn" onClick={addNode}>
          + Add Node
        </button>
      </div>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
      >
        <Controls />
        <MiniMap />
        <Background variant="dots" gap={12} size={1} />
      </ReactFlow>
    </div>
  );
}

export default App;
