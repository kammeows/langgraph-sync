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
  const isSelfLoop = data?.source === data?.target;

  if (isSelfLoop) {
    // Parameters for the loop arc
    const radiusX = 40;
    const radiusY = 30;

    // We want the loop to go out from the right handle and come back to the top/bottom
    // Or just a standard arc on the right side
    // const edgePath = `M ${sourceX} ${sourceY} C ${sourceX + radiusX} ${sourceY - radiusY}, ${sourceX + radiusX} ${sourceY + radiusY}, ${sourceX} ${sourceY + 5}`;

    const loopRadius = 45;

    const edgePath = `
  M ${sourceX} ${sourceY}
  A ${loopRadius} ${loopRadius}
    0 1 1
    ${targetX} ${targetY}
`;
    return (
      <>
        <BaseEdge
          path={edgePath}
          markerEnd={markerEnd}
          style={{ ...style, strokeWidth: 2 }}
        />
        {data?.label && (
          <EdgeLabelRenderer>
            <div
              style={{
                position: "absolute",
                transform: `translate(-50%, -50%) translate(${sourceX + radiusX}px,${sourceY}px)`,
                background: "white",
                padding: "2px 4px",
                borderRadius: "4px",
                fontSize: "10px",
                fontWeight: "bold",
              }}
              className="nodrag nopan"
            >
              {data.label}
            </div>
          </EdgeLabelRenderer>
        )}
      </>
    );
  }

  // Fallback to standard bezier for non-self loops if this type is used
  const [path] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  return <BaseEdge path={path} markerEnd={markerEnd} style={style} />;
}
