import React, { useState } from "react";
import "./ValidationPanel.css";

const ValidationPanel = ({ warnings }) => {
  const [isCollapsed, setIsCollapsed] = useState(false);

  // Deduplicate warnings by type and message to prevent duplicates in the panel
  const uniqueWarnings = [];
  const seen = new Set();
  for (const w of warnings) {
    if (w && w.message) {
      const key = `${w.type || "warning"}||${w.message}`;
      if (!seen.has(key)) {
        seen.add(key);
        uniqueWarnings.push(w);
      }
    }
  }

  return (
    <div className={`validation-panel ${isCollapsed ? "collapsed" : ""}`}>
      <div className="validation-header" onClick={() => setIsCollapsed(!isCollapsed)}>
        <span>Validation ({uniqueWarnings.length})</span>
        <span className="collapse-icon">{isCollapsed ? "▲" : "▼"}</span>
      </div>
      {!isCollapsed && (
        <div className="validation-content">
          {uniqueWarnings.length === 0 ? (
            <div className="no-warnings">No issues detected.</div>
          ) : (
            uniqueWarnings.map((warning, index) => (
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
