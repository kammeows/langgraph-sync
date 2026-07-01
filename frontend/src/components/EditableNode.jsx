import React, { useState, useEffect } from "react";
import { Handle, Position } from "@xyflow/react";

const EditableNode = ({ data, id, selected }) => {
  const [label, setLabel] = useState(data.label || id);
  const [isEditing, setIsEditing] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [editingSubNodeId, setEditingSubNodeId] = useState(null);
  const [subNodeLabel, setSubNodeLabel] = useState("");

  // Keep local label in sync with external updates (e.g. from code sync)
  useEffect(() => {
    if (!isEditing) {
      setLabel(data.label || id);
    }
  }, [data.label, id, isEditing]);

  const onLabelChange = (evt) => {
    setLabel(evt.target.value);
  };

  const commitRename = () => {
    setIsEditing(false);
    // Only trigger rename if the label actually changed
    if (data.onRename && label !== data.label) {
      data.onRename(id, label);
    }
  };

  const onDelete = () => {
    if (data.onDelete) {
      data.onDelete(id);
    }
  };

  const startSubNodeRename = (subNodeId, currentLabel) => {
    setEditingSubNodeId(subNodeId);
    setSubNodeLabel(currentLabel);
  };

  const commitSubNodeRename = (subNodeId) => {
    setEditingSubNodeId(null);
    if (data.onSubNodeRename && subNodeLabel !== subNodeId) {
      data.onSubNodeRename(subNodeId, subNodeLabel);
    }
  };

  const isStart = id === "__start__";
  const isEnd = id === "__end__";

  return (
    <div className={`editable-node-container ${data.type || ''} ${selected ? 'selected' : ''} ${isExpanded ? 'expanded' : ''}`}>
      {/* Target handle at the Top - arrows point HERE */}
      {!isStart && <Handle type="target" position={Position.Top} />}
      
      <div className="editable-node-body">
        {isEditing ? (
          <input
            className="nodrag"
            type="text"
            value={label}
            onChange={onLabelChange}
            onBlur={commitRename}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitRename();
            }}
            autoFocus
          />
        ) : (
          <div 
            className="node-label" 
            onDoubleClick={() => {
              if (data.isEditable !== false) {
                setIsEditing(true);
              }
            }}
          >
            {label}
          </div>
        )}
        
        {data.isSubgraph && (
          <button 
            className="expand-subgraph-btn nodrag" 
            onClick={() => setIsExpanded(!isExpanded)}
            title={isExpanded ? "Collapse Subgraph" : "Expand Subgraph"}
          >
            ⇳
          </button>
        )}

        {data.deletable !== false && (
          <button className="delete-node-btn nodrag" onClick={onDelete}>
            &times;
          </button>
        )}

        {/* State Flow Panel (Expanded to Node Details) */}
        {selected && !isStart && !isEnd && (
          <div className="state-flow-panel">
            <div className="state-flow-header">NODE DETAILS</div>
            
            <div className="state-flow-section">
                <div className="state-flow-title implementation">IMPLEMENTATION</div>
                <div className="state-flow-keys">
                    {data.functionName ? `${data.functionName}()` : "none"}
                </div>
            </div>

            <div className="state-flow-section">
              <div className="state-flow-title inputs">INPUTS</div>
              <div className="state-flow-keys">
                {data.inputs?.length > 0 ? data.inputs.join(", ") : "none"}
              </div>
            </div>

            <div className="state-flow-section">
              <div className="state-flow-title outputs">OUTPUTS</div>
              <div className="state-flow-keys">
                {data.outputs?.length > 0 ? data.outputs.join(", ") : "none"}
              </div>
            </div>

            <div className="state-flow-section">
                <div className="state-flow-title incoming">INCOMING EDGES</div>
                <div className="state-flow-keys">
                    {data.incoming?.length > 0 ? data.incoming.join(", ") : "none"}
                </div>
            </div>

            <div className="state-flow-section">
                <div className="state-flow-title outgoing">OUTGOING EDGES</div>
                <div className="state-flow-keys">
                    {data.outgoing?.length > 0 ? data.outgoing.map(o => o === "__end__" ? "END" : o).join(", ") : "none"}
                </div>
            </div>

            {data.cycle && (
                <div className="state-flow-section">
                    <div className="state-flow-title cycle">CYCLE DETECTED</div>
                    <div className="state-flow-keys" style={{ color: "#f87171", fontWeight: "bold" }}>
                        {data.cycle}
                    </div>
                </div>
            )}
          </div>
        )}
      </div>

      {/* Subgraph Preview */}
      {isExpanded && data.subgraph && (
        <div className="subgraph-preview-container nodrag">
          <div className="subgraph-preview-title">SUBGRAPH</div>
          <div className="subgraph-preview-flow">
            {data.subgraph.nodes
              .filter(node => node.id !== "__start__" && node.id !== "__end__")
              .map((node, index) => {
                const isEditingSub = editingSubNodeId === node.id;
                return (
                  <React.Fragment key={node.id}>
                    {index > 0 && <span className="subgraph-arrow">→</span>}
                    <span 
                      className="subgraph-preview-node clickable"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (!isEditingSub && data.onSubNodeClick) {
                          data.onSubNodeClick(node);
                        }
                      }}
                      onDoubleClick={(e) => {
                        e.stopPropagation();
                        startSubNodeRename(node.id, node.id);
                      }}
                    >
                      {isEditingSub ? (
                        <input
                          className="nodrag subnode-rename-input"
                          type="text"
                          value={subNodeLabel}
                          onChange={(e) => setSubNodeLabel(e.target.value)}
                          onBlur={() => commitSubNodeRename(node.id)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') commitSubNodeRename(node.id);
                          }}
                          autoFocus
                          onClick={(e) => e.stopPropagation()}
                        />
                      ) : (
                        <>
                          <span className="subnode-label">{node.id}</span>
                          <span 
                            className="subnode-delete-btn"
                            onClick={(e) => {
                              e.stopPropagation();
                              if (data.onSubNodeDelete) {
                                data.onSubNodeDelete(node.id);
                              }
                            }}
                          >
                            &times;
                          </span>
                        </>
                      )}
                    </span>
                  </React.Fragment>
                );
              })
            }
          </div>
        </div>
      )}

      {/* Source handle at the Bottom - arrows start FROM here */}
      {!isEnd && <Handle type="source" position={Position.Bottom} />}
    </div>
  );
};

export default EditableNode;
