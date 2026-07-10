import React from "react";
import "./CometLLMInspectorPanel.css";

const CometLLMInspectorPanel = ({ node, onClose }) => {
  if (!node) return null;

  const {
    label,
    functionName,
    llmCalls = [],
    inputs = [],
    outputs = [],
  } = node.data || {};
  const hasLLMCalls = llmCalls && llmCalls.length > 0;

  // Map providers to colors/logos
  const getProviderStyle = (provider) => {
    const p = provider ? provider.toLowerCase() : "";
    if (p.includes("openai"))
      return {
        bg: "rgba(16, 163, 127, 0.15)",
        border: "#10a37f",
        text: "#10a37f",
        icon: "🟢",
      };
    if (p.includes("anthropic"))
      return {
        bg: "rgba(217, 119, 6, 0.15)",
        border: "#d97706",
        text: "#f59e0b",
        icon: "🟠",
      };
    if (p.includes("google"))
      return {
        bg: "rgba(59, 130, 246, 0.15)",
        border: "#3b82f6",
        text: "#60a5fa",
        icon: "🔵",
      };
    if (p.includes("deepseek"))
      return {
        bg: "rgba(59, 76, 246, 0.2)",
        border: "#4f46e5",
        text: "#818cf8",
        icon: "🔮",
      };
    if (p.includes("meta"))
      return {
        bg: "rgba(29, 78, 216, 0.15)",
        border: "#1d4ed8",
        text: "#3b82f6",
        icon: "🔵",
      };
    if (p.includes("mistral"))
      return {
        bg: "rgba(236, 72, 153, 0.15)",
        border: "#ec4899",
        text: "#f472b6",
        icon: "🌸",
      };
    return {
      bg: "rgba(107, 114, 128, 0.15)",
      border: "#6b7280",
      text: "#9ca3af",
      icon: "⚙️",
    };
  };

  return (
    <div className="comet-inspector-panel">
      <div className="comet-inspector-header">
        <div className="comet-inspector-title-container">
          <span className="comet-inspector-title">LLM Inspector</span>
        </div>
        <button
          className="comet-close-btn"
          onClick={onClose}
          title="Deselect Node"
        >
          ×
        </button>
      </div>

      <div className="comet-inspector-content">
        <div className="node-info-section">
          <div className="info-row">
            <span className="info-label">Node:</span>
            <span className="info-value highlight">{label || node.id}</span>
          </div>
          {functionName && (
            <div className="info-row">
              <span className="info-label">Function:</span>
              <span className="info-value code-font">{functionName}</span>
            </div>
          )}
        </div>

        <div className="llm-calls-section">
          <div className="section-title">
            LLM INVOCATIONS ({llmCalls.length})
          </div>

          {!hasLLMCalls ? (
            <div className="no-llm-calls">
              <span className="info-icon">🛈</span> No LLM calls detected in this
              node's function body.
            </div>
          ) : (
            llmCalls.map((call, idx) => {
              const style = getProviderStyle(call.provider);
              return (
                <div
                  key={idx}
                  className="llm-call-card"
                  style={{
                    backgroundColor: style.bg,
                    borderLeft: `3px solid ${style.border}`,
                  }}
                >
                  <div className="llm-call-header">
                    <span
                      className="provider-badge"
                      style={{ color: style.text }}
                    >
                      {style.icon} {call.provider || "Unknown"}
                    </span>
                    {call.is_comet ? (
                      <span className="gateway-badge">Comet Gateway</span>
                    ) : (
                      <span className="gateway-badge direct">Direct API</span>
                    )}
                  </div>
                  <div className="model-name-row">
                    <span className="model-label">Model:</span>
                    <span className="model-value">{call.model}</span>
                  </div>
                  {call.raw_model && call.raw_model !== call.model && (
                    <div className="raw-model-row">
                      <span className="raw-label">Code Ref:</span>
                      <span className="raw-value">{call.raw_model}</span>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        {(inputs.length > 0 || outputs.length > 0) && (
          <div className="state-keys-section">
            <div className="section-title">STATE TRANSACTIONS</div>
            {inputs.length > 0 && (
              <div className="keys-row">
                <span className="keys-label">Reads:</span>
                <div className="keys-list">
                  {inputs.map((k) => (
                    <span key={k} className="key-badge read">
                      {k}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {outputs.length > 0 && (
              <div className="keys-row">
                <span className="keys-label">Writes:</span>
                <div className="keys-list">
                  {outputs.map((k) => (
                    <span key={k} className="key-badge write">
                      {k}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default CometLLMInspectorPanel;
