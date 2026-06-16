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
  // Detect if this is a backward edge (cycle)
  const isBackward = sourceY > targetY;
  
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
    curvature: isBackward ? 0.8 : 0.5, // Increase curvature for backward edges
  });

  // For backward edges that would be straight, shift them horizontally
  let finalPath = edgePath;
  let finalLabelX = labelX;
  let finalLabelY = labelY;

  if (isBackward && Math.abs(sourceX - targetX) < 10) {
      const shift = 80;
      finalPath = `M ${sourceX} ${sourceY} C ${sourceX - shift} ${sourceY - 20}, ${targetX - shift} ${targetY + 20}, ${targetX} ${targetY}`;
      finalLabelX = sourceX - shift;
      finalLabelY = (sourceY + targetY) / 2;
  }

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
      <BaseEdge path={finalPath} markerEnd={markerEnd} style={edgeStyle} />
      <EdgeLabelRenderer>
        <div
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${finalLabelX}px,${finalLabelY}px)`,
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
