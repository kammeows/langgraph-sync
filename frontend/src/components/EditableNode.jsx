import React, { useState, useEffect } from 'react';
import { Handle, Position } from '@xyflow/react';

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

  return (
    <div className={`editable-node-container ${data.type || ''} ${selected ? 'selected' : ''}`}>
      <Handle type="target" position={Position.Top} />
      
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
          <div className="node-label" onDoubleClick={() => setIsEditing(true)}>
            {label}
          </div>
        )}
        
        <button className="delete-node-btn nodrag" onClick={onDelete}>
          &times;
        </button>
      </div>

      <Handle type="source" position={Position.Bottom} />
    </div>
  );
};

export default EditableNode;
