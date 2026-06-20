import React, { useState, useCallback } from 'react';
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  useReactFlow,
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
  selected,
}) => {
  const { setEdges } = useReactFlow();

  // Curvature from data or default
  const curvature = data?.curvature ?? (sourceY > targetY ? 0.8 : 0.5);
  
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
    curvature: curvature,
  });

  // Handle Smart Shift for direct vertical cycles
  let finalPath = edgePath;
  let finalLabelX = labelX;
  let finalLabelY = labelY;

  if (sourceY > targetY && Math.abs(sourceX - targetX) < 10 && !data?.customPath) {
      const shift = 80;
      finalPath = `M ${sourceX} ${sourceY} C ${sourceX - shift} ${sourceY - 20}, ${targetX - shift} ${targetY + 20}, ${targetX} ${targetY}`;
      finalLabelX = sourceX - shift;
      finalLabelY = (sourceY + targetY) / 2;
  }

  const label = data?.label || '';

  const onEdgeClick = (evt) => {
    evt.stopPropagation();
    if (data && data.onDelete) {
      data.onDelete(id);
    }
  };

  // Dragging logic for curvature
  const onHandleMouseDown = useCallback((event) => {
    event.stopPropagation();
    
    const startX = event.clientX;
    const startY = event.clientY;
    const startCurvature = curvature;

    const onMouseMove = (moveEvent) => {
        const deltaX = moveEvent.clientX - startX;
        const deltaY = moveEvent.clientY - startY;
        
        // Map movement to curvature change
        // Horizontal movement changes curvature, vertical can change shift
        const newCurvature = Math.max(0, Math.min(2, startCurvature + deltaX / 100));
        
        if (data?.onUpdateData) {
            data.onUpdateData(id, { curvature: newCurvature });
        }
    };

    const onMouseUp = () => {
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
    };

    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  }, [id, curvature, data]);

  const edgeStyle = {
    ...style,
    strokeDasharray: data?.isConditional ? '5,5' : 'none',
    stroke: selected ? '#fff' : (style.stroke || '#b1b1b7'),
    strokeWidth: selected ? 3 : (style.strokeWidth || 2),
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
          {selected && (
              <div 
                onMouseDown={onHandleMouseDown}
                style={{
                    width: '12px',
                    height: '12px',
                    backgroundColor: '#3b82f6',
                    borderRadius: '50%',
                    cursor: 'ew-resize',
                    border: '2px solid white',
                    boxShadow: '0 0 5px rgba(0,0,0,0.3)',
                    marginBottom: '5px'
                }}
                title="Drag to change curvature"
              />
          )}

          {data?.showLabels && data?.isConditional && (
            <div className="edge-label-container">
              <div className="edge-label">
                {label || 'Conditional Edge'}
              </div>
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
