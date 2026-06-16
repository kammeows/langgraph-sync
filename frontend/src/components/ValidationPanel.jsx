import React, { useState } from "react";
import "./ValidationPanel.css";

const ValidationPanel = ({ warnings }) => {
  const [isCollapsed, setIsCollapsed] = useState(false);

  return (
    <div className={`validation-panel ${isCollapsed ? "collapsed" : ""}`}>
      <div className="validation-header" onClick={() => setIsCollapsed(!isCollapsed)}>
        <span>Validation ({warnings.length})</span>
        <span className="collapse-icon">{isCollapsed ? "▲" : "▼"}</span>
      </div>
      {!isCollapsed && (
        <div className="validation-content">
          {warnings.length === 0 ? (
            <div className="no-warnings">No issues detected.</div>
          ) : (
            warnings.map((warning, index) => (
              <div key={index} className={`warning-item ${warning.type}`}>
                <span className="warning-icon">
                  {warning.type === "error" ? "❌" : "⚠️"}
                </span>
                <span className="warning-message">{warning.message}</span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
};

export default ValidationPanel;
