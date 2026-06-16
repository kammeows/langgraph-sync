import React from "react";
import { BaseEdge, getBezierPath, EdgeLabelRenderer } from "@xyflow/react";

export default function SelfLoopEdge({
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
}) {
  // We want the loop to go out to the side
  // For vertical layout, handles are top/bottom. 
  // Let's create a path that goes from Bottom -> Side -> Top
  
  const nodeWidth = 150; 
  const loopWidth = 40;
  const loopHeight = 60;

  // M sourceX sourceY (bottom)
  // C sourceX+nodeWidth/2+loopWidth sourceY, sourceX+nodeWidth/2+loopWidth targetY, targetX targetY (top)
  
  const edgePath = `
    M ${sourceX} ${sourceY}
    C ${sourceX + nodeWidth/2 + loopWidth} ${sourceY + 20},
      ${sourceX + nodeWidth/2 + loopWidth} ${targetY - 20},
      ${targetX} ${targetY}
  `;

  return (
    <>
      <BaseEdge
        path={edgePath}
        markerEnd={markerEnd}
        style={{ ...style, strokeWidth: 2 }}
      />
      <EdgeLabelRenderer>
        <div
          style={{
            position: "absolute",
            transform: `translate(-50%, -50%) translate(${sourceX + nodeWidth/2 + loopWidth}px,${(sourceY + targetY)/2}px)`,
            background: "#1e1e1e",
            color: "#8b5cf6",
            padding: "2px 6px",
            border: "1px solid #444",
            borderRadius: "4px",
            fontSize: "10px",
            fontWeight: "bold",
            pointerEvents: "all"
          }}
          className="nodrag nopan"
        >
          {data?.label || "self"}
          <button 
            onClick={(e) => {
                e.stopPropagation();
                data.onDelete(id);
            }}
            style={{ 
                marginLeft: "5px", 
                background: "none", 
                border: "none", 
                color: "#f87171", 
                cursor: "pointer",
                padding: "0",
                fontSize: "12px"
            }}
          >
            ×
          </button>
        </div>
      </EdgeLabelRenderer>
    </>
  );
}
