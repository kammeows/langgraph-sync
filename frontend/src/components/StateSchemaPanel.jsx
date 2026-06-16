import React, { useState } from "react";
import "./StateSchemaPanel.css";

const StateSchemaPanel = ({ schema }) => {
  const [isCollapsed, setIsCollapsed] = useState(false);

  if (!schema || !schema.name) return null;

  return (
    <div className={`state-schema-panel ${isCollapsed ? "collapsed" : ""}`}>
      <div className="schema-header" onClick={() => setIsCollapsed(!isCollapsed)}>
        <span>State: {schema.name}</span>
        <span className="collapse-icon">{isCollapsed ? "▲" : "▼"}</span>
      </div>
      {!isCollapsed && (
        <div className="schema-content">
          {Object.entries(schema.fields || {}).map(([key, type]) => (
            <div key={key} className="schema-field">
              <span className="field-key">{key}:</span>
              <span className="field-type">{type}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default StateSchemaPanel;
