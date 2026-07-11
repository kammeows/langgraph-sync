import React, { useState } from "react";
import "./CometLLMInspectorPanel.css";

const COMET_MODELS = [
  { value: "deepseek/deepseek-chat", label: "DeepSeek V3" },
  { value: "deepseek/deepseek-reasoner", label: "DeepSeek R1" },
  { value: "anthropic/claude-3-5-sonnet", label: "Claude 3.5 Sonnet" },
  { value: "openai/gpt-4o", label: "GPT-4o" },
  { value: "openai/gpt-4o-mini", label: "GPT-4o Mini" },
  { value: "google/gemini-2.5-flash", label: "Gemini 2.5 Flash" },
  { value: "meta-llama/llama-3.1-405b-instruct", label: "Llama 3.1 405B" },
];

const formatCometModelPath = (modelStr, cometModels = []) => {
  if (!modelStr) return "";
  const trimmed = modelStr.trim();

  // If it already has a slash, make sure the provider part is lowercased
  if (trimmed.includes("/")) {
    const parts = trimmed.split("/");
    return `${parts[0].toLowerCase()}/${parts[1].toLowerCase()}`;
  }

  const lower = trimmed.toLowerCase();

  // 1. Try to find a match in the dynamically fetched cometModels list by matching the part after the slash
  if (cometModels && cometModels.length > 0) {
    const matched = cometModels.find((modelId) => {
      const parts = modelId.split("/");
      if (parts.length === 2) {
        return parts[1].toLowerCase() === lower;
      }
      return false;
    });
    if (matched) {
      return matched;
    }
  }

  // 2. Fallback to hardcoded inference rules if not found in the fetched list
  if (lower.includes("deepseek")) {
    return `deepseek/${lower}`;
  }
  if (
    lower.includes("gpt") ||
    lower.startsWith("o1") ||
    lower.startsWith("o3") ||
    lower.includes("text-embedding")
  ) {
    return `openai/${lower}`;
  }
  if (lower.includes("claude")) {
    return `anthropic/${lower}`;
  }
  if (lower.includes("gemini")) {
    return `google/${lower}`;
  }
  if (lower.includes("llama")) {
    return `meta-llama/${lower}`;
  }
  if (lower.includes("qwen")) {
    return `qwen/${lower}`;
  }
  if (lower.includes("mistral") || lower.includes("mixtral")) {
    return `mistral/${lower}`;
  }
  return lower;
};

const CometLLMInspectorPanel = ({
  node,
  onClose,
  onModelChange,
  cometModels = [],
}) => {
  if (!node) return null;

  const {
    label,
    functionName,
    llmCalls = [],
    inputs = [],
    outputs = [],
  } = node.data || {};
  const hasLLMCalls = llmCalls && llmCalls.length > 0;

  const [editingIndex, setEditingIndex] = useState(null);
  const [customModel, setCustomModel] = useState("");

  const sortedCometModels = cometModels ? [...cometModels].sort() : [];
  const rawList =
    sortedCometModels.length > 0
      ? sortedCometModels.map((modelId) => {
          let label = modelId;
          if (
            modelId.includes("deepseek-chat") ||
            modelId === "deepseek/deepseek-chat"
          )
            label = "DeepSeek V3";
          else if (
            modelId.includes("deepseek-reasoner") ||
            modelId === "deepseek/deepseek-reasoner"
          )
            label = "DeepSeek R1";
          else if (
            modelId.includes("claude-3-5-sonnet") ||
            modelId.includes("claude-3.5-sonnet")
          )
            label = "Claude 3.5 Sonnet";
          else if (modelId.includes("gpt-4o-mini")) label = "GPT-4o Mini";
          else if (modelId.includes("gpt-4o")) label = "GPT-4o";
          else if (modelId.includes("gemini-2.5-flash"))
            label = "Gemini 2.5 Flash";
          return { value: modelId, label };
        })
      : COMET_MODELS;

  const modelsList = rawList.filter(m => {
    const formatted = formatCometModelPath(m.value, cometModels);
    return formatted && formatted.includes("/");
  });

  const getModelCost = (modelPath) => {
    const path = modelPath ? modelPath.toLowerCase() : "";
    if (path.includes("deepseek-chat") || path === "deepseek/deepseek-chat") {
      return "In: $0.14 | Out: $0.28";
    }
    if (
      path.includes("deepseek-reasoner") ||
      path === "deepseek/deepseek-reasoner"
    ) {
      return "In: $0.55 | Out: $2.19";
    }
    if (
      path.includes("claude-3-5-sonnet") ||
      path.includes("claude-3.5-sonnet")
    ) {
      return "In: $2.40 | Out: $12.00";
    }
    if (path.includes("gpt-4o-mini")) {
      return "In: $0.12 | Out: $0.48";
    }
    if (path.includes("gpt-4o")) {
      return "In: $4.00 | Out: $12.00";
    }
    if (path.includes("gemini-2.5-flash")) {
      return "In: $0.06 | Out: $0.24";
    }
    if (path.includes("llama-3.1-405b")) {
      return "In: $2.13 | Out: $2.13";
    }
    return "20% Gateway Discount";
  };

  const getModelLatency = (modelPath) => {
    const path = modelPath ? modelPath.toLowerCase() : "";
    if (
      path.includes("mini") ||
      path.includes("flash") ||
      path.includes("chat")
    ) {
      if (path.includes("deepseek")) return "Fast (~1.2s)";
      return "Ultra Fast (<1.0s)";
    }
    if (
      path.includes("reasoner") ||
      path.includes("thinking") ||
      path.includes("o1")
    ) {
      return "Thinking (~4.0s - 15.0s)";
    }
    if (
      path.includes("sonnet") ||
      path.includes("gpt-4o") ||
      path.includes("405b")
    ) {
      return "Moderate (~1.5s - 2.5s)";
    }
    return "Variable (1.0s - 3.0s)";
  };

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
              const isCometCall = call.is_comet;
              const fullModelPath = call.raw_model || call.model;

              const matchingModel = modelsList.find(
                (m) =>
                  m.value.toLowerCase() === fullModelPath.toLowerCase() ||
                  m.value
                    .toLowerCase()
                    .endsWith("/" + fullModelPath.toLowerCase()) ||
                  fullModelPath
                    .toLowerCase()
                    .endsWith("/" + m.value.toLowerCase()),
              );

              const isPredefined = !!matchingModel;
              const selectValue = matchingModel
                ? matchingModel.value
                : "custom";

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
                    {isCometCall ? (
                      <span className="gateway-badge">Comet Gateway</span>
                    ) : (
                      <span className="gateway-badge direct">Direct API</span>
                    )}
                  </div>

                  {isCometCall ? (
                    <div className="comet-model-selector-container">
                      {editingIndex === idx ? (
                        <div className="custom-model-input-row">
                          <input
                            type="text"
                            className="custom-model-input"
                            value={customModel}
                            onChange={(e) => setCustomModel(e.target.value)}
                            placeholder="e.g. openai/gpt-4o"
                          />
                          <button
                            className="model-action-btn save"
                            onClick={() => {
                              if (customModel.trim() && onModelChange) {
                                const formatted = formatCometModelPath(
                                  customModel.trim(),
                                  cometModels,
                                );
                                onModelChange(functionName, formatted);
                              }
                              setEditingIndex(null);
                            }}
                          >
                            ✓
                          </button>
                          <button
                            className="model-action-btn cancel"
                            onClick={() => setEditingIndex(null)}
                          >
                            ✕
                          </button>
                        </div>
                      ) : (
                        <div className="model-select-row">
                          <span className="model-label">Model:</span>
                          <select
                            className="inspector-model-select"
                            value={selectValue}
                            onChange={(e) => {
                              const val = e.target.value;
                              if (val === "custom") {
                                setCustomModel(fullModelPath);
                                setEditingIndex(idx);
                              } else {
                                if (onModelChange) {
                                  onModelChange(
                                    functionName,
                                    formatCometModelPath(val, cometModels),
                                  );
                                }
                              }
                            }}
                          >
                            {modelsList.map((m) => (
                              <option key={m.value} value={m.value}>
                                {m.label} ({m.value})
                              </option>
                            ))}
                            {!isPredefined && (
                              <option value={fullModelPath}>
                                Current: {fullModelPath}
                              </option>
                            )}
                            <option value="custom">
                              ✏️ Custom Model Path...
                            </option>
                          </select>
                        </div>
                      )}

                      <div className="model-metrics-row">
                        <div className="metric-box">
                          <span className="metric-icon">💰</span>
                          <div className="metric-details">
                            <span className="metric-label">
                              Est. Cost (per M tokens):{" "}
                            </span>
                            <span className="metric-value">
                              {getModelCost(fullModelPath)}
                            </span>
                          </div>
                        </div>
                        <div className="metric-box">
                          <span className="metric-icon">⚡</span>
                          <div className="metric-details">
                            <span className="metric-label">
                              Avg. Latency Class:{" "}
                            </span>
                            <span className="metric-value">
                              {getModelLatency(fullModelPath)}
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <>
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
                    </>
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
