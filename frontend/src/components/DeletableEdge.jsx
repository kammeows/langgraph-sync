import React, { useState } from 'react';
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
} from '@xyflow/react';

const DeletableEdge = ({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style = {},
  markerEnd,
  data,
}) => {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const [label, setLabel] = useState(data?.label || '');
  const [isEditing, setIsEditing] = useState(false);

  const onEdgeClick = (evt) => {
    evt.stopPropagation();
    if (data && data.onDelete) {
      data.onDelete(id);
    }
  };

  const onLabelChange = (evt) => {
    setLabel(evt.target.value);
    if (data?.onRenameLabel) {
      data.onRenameLabel(id, evt.target.value);
    }
  };

  // Merge custom style with conditional styling
  const edgeStyle = {
    ...style,
    strokeDasharray: data?.isConditional ? '5,5' : 'none',
  };

  return (
    <>
      <BaseEdge path={edgePath} markerEnd={markerEnd} style={edgeStyle} />
      <EdgeLabelRenderer>
        <div
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            fontSize: 12,
            pointerEvents: 'all',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '4px'
          }}
          className="nodrag nopan"
        >
          {data?.isConditional && (
            <div className="edge-label-container">
              {isEditing ? (
                <input
                  className="edge-label-input"
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
                <div className="edge-label" onDoubleClick={() => setIsEditing(true)}>
                  {label || 'Conditional Edge'}
                </div>
              )}
            </div>
          )}
          <button className="delete-edge-btn" onClick={onEdgeClick}>
            &times;
          </button>
        </div>
      </EdgeLabelRenderer>
    </>
  );
};

export default DeletableEdge;
