import React, { useState } from 'react';
import { Handle, Position } from '@xyflow/react';

const EditableNode = ({ data, id, selected }) => {
  const [label, setLabel] = useState(data.label || id);
  const [isEditing, setIsEditing] = useState(false);

  const onLabelChange = (evt) => {
    setLabel(evt.target.value);
    if (data.onRename) {
      data.onRename(id, evt.target.value);
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
            onBlur={() => setIsEditing(false)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') setIsEditing(false);
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
