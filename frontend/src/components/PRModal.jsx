import React, { useState, useEffect } from "react";
import "./PRModal.css";

const PRModal = ({ isOpen, onClose }) => {
  const [status, setStatus] = useState(null);
  const [diff, setDiff] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitStatus, setSubmitStatus] = useState("");
  const [error, setError] = useState(null);
  const [prUrl, setPrUrl] = useState(null);

  useEffect(() => {
    if (isOpen) {
      fetchStatusAndDiff();
    } else {
      // Reset state when closed
      setTitle("");
      setDescription("");
      setError(null);
      setPrUrl(null);
      setSubmitting(false);
      setSubmitStatus("");
    }
  }, [isOpen]);

  const fetchStatusAndDiff = async () => {
    setLoading(true);
    setError(null);
    try {
      const statusRes = await fetch("http://localhost:8000/api/git/status");
      const statusData = await statusRes.json();
      setStatus(statusData);

      const diffRes = await fetch("http://localhost:8000/api/git/diff");
      const diffData = await diffRes.json();
      setDiff(diffData.diff || "");
    } catch (err) {
      setError("Failed to fetch git repository status or diff.");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!title.trim()) {
      setError("Please enter a Pull Request title.");
      return;
    }

    setSubmitting(true);
    setError(null);
    setSubmitStatus("Creating branch, staging, committing and pushing to remote...");

    try {
      const response = await fetch("http://localhost:8000/api/git/create-pr", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          title,
          body: description,
        }),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Failed to create Pull Request.");
      }

      setPrUrl(data.pr_url);
      setSubmitStatus("PR created successfully!");
    } catch (err) {
      setError(err.message || "An unexpected error occurred.");
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay">
      <div className="pr-modal-content">
        <div className="pr-modal-header">
          <h3>🚀 Submit Changes to GitHub PR</h3>
          <button type="button" className="close-x-btn" onClick={onClose}>×</button>
        </div>

        {loading ? (
          <div className="pr-modal-loading">
            <div className="spinner"></div>
            <p>Scanning repository status and differences...</p>
          </div>
        ) : prUrl ? (
          <div className="pr-modal-success">
            <div className="success-icon">🎉</div>
            <h4>Pull Request Created Successfully!</h4>
            <p className="success-msg">Your changes have been pushed to a remote branch and a PR has been opened.</p>
            <a href={prUrl} target="_blank" rel="noopener noreferrer" className="view-pr-link">
              View Pull Request on GitHub ↗
            </a>
            <div className="modal-actions">
              <button type="button" className="cancel-btn" onClick={onClose}>Close</button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="pr-form">
            {error && (
              <div className="pr-error-banner">
                <span>⚠️ Error: {error}</span>
              </div>
            )}

            {status && (
              <div className="git-repo-info">
                <span className="repo-badge">
                  📍 Branch: <strong>{status.active_branch || "unknown"}</strong>
                </span>
                <span className="repo-badge">
                  📦 Repo: <strong>{status.repo_owner}/{status.repo_name}</strong>
                </span>
                <span className={`status-badge ${status.is_clean ? 'clean' : 'dirty'}`}>
                  {status.is_clean ? "✓ Workspace Clean" : "⚠ Workspace Modified"}
                </span>
              </div>
            )}

            {status && status.is_clean ? (
              <div className="pr-empty-warning">
                <p>No local changes detected in your workspace repository.</p>
                <p className="hint">Make some graph or code modifications first to submit a PR!</p>
              </div>
            ) : (
              <>
                <div className="form-group">
                  <label htmlFor="pr-title">PR Title:</label>
                  <input
                    id="pr-title"
                    type="text"
                    placeholder="e.g. feat: implement router v3 logic"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    required
                    disabled={submitting}
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="pr-desc">Description / Body:</label>
                  <textarea
                    id="pr-desc"
                    placeholder="e.g. Inverted router flow, added validation step to agent layout."
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    rows={3}
                    disabled={submitting}
                  />
                </div>

                <div className="diff-preview-container">
                  <label>Changes Diff Preview:</label>
                  <div className="diff-viewer">
                    {diff ? (
                      <pre className="diff-code">
                        {diff.split("\n").map((line, idx) => {
                          let className = "diff-line";
                          if (line.startsWith("+") && !line.startsWith("+++")) {
                            className += " diff-add";
                          } else if (line.startsWith("-") && !line.startsWith("---")) {
                            className += " diff-del";
                          } else if (line.startsWith("@@")) {
                            className += " diff-header";
                          }
                          return (
                            <div key={idx} className={className}>
                              {line}
                            </div>
                          );
                        })}
                      </pre>
                    ) : (
                      <div className="no-diff-msg">No readable diff.</div>
                    )}
                  </div>
                </div>
              </>
            )}

            {submitting && (
              <div className="pr-submitting-progress">
                <div className="mini-spinner"></div>
                <span>{submitStatus}</span>
              </div>
            )}

            <div className="modal-actions">
              <button type="button" className="cancel-btn" onClick={onClose} disabled={submitting}>
                Cancel
              </button>
              <button
                type="submit"
                className="submit-btn pr-submit-btn"
                disabled={submitting || (status && status.is_clean) || loading}
              >
                {submitting ? "Opening PR..." : "🚀 Create Pull Request"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};

export default PRModal;
