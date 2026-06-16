import React, { useState, useEffect } from "react";
import { Handle, Position } from "@xyflow/react";

const EditableNode = ({ data, id, selected }) => {
  const [label, setLabel] = useState(data.label || id);
  const [isEditing, setIsEditing] = useState(false);

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

  const isStart = id === "__start__";
  const isEnd = id === "__end__";

  return (
    <div className={`editable-node-container ${data.type || ''} ${selected ? 'selected' : ''}`}>
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
        
        {data.deletable !== false && (
          <button className="delete-node-btn nodrag" onClick={onDelete}>
            &times;
          </button>
        )}

        {/* State Flow Panel */}
        {selected && !isStart && !isEnd && (
          <div className="state-flow-panel">
            <div className="state-flow-header">STATE FLOW</div>
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
          </div>
        )}
      </div>

      {/* Source handle at the Bottom - arrows start FROM here */}
      {!isEnd && <Handle type="source" position={Position.Bottom} />}
    </div>
  );
};

export default EditableNode;
