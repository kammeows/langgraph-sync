import React, { useState } from "react";
import "./ConditionalRouteModal.css";

const ConditionalRouteModal = ({ isOpen, onClose, onAdd, nodes }) => {
  const [source, setSource] = useState("");
  const [routerFn, setRouterFn] = useState("route_after_router");
  const [routes, setRoutes] = useState([{ key: "", target: "" }]);

  if (!isOpen) return null;

  const handleAddRoute = () => {
    setRoutes([...routes, { key: "", target: "" }]);
  };

  const handleRouteChange = (index, field, value) => {
    const newRoutes = [...routes];
    newRoutes[index][field] = value;
    setRoutes(newRoutes);
  };

  const handleRemoveRoute = (index) => {
    setRoutes(routes.filter((_, i) => i !== index));
  };

  const handleSubmit = () => {
    if (!source || !routerFn || routes.some(r => !r.key || !r.target)) {
        alert("Please fill all fields");
        return;
    }
    
    const mapping = {};
    routes.forEach(r => {
        mapping[r.key] = r.target;
    });

    onAdd({ source, router_fn: routerFn, mapping });
    onClose();
  };

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <h3>Add Conditional Route</h3>
        
        <div className="form-group">
          <label>Source Node:</label>
          <select value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="">Select Source</option>
            {nodes.filter(n => n.type === "agentNode" || n.type === "toolNode").map(n => (
              <option key={n.id} value={n.id}>{n.id}</option>
            ))}
          </select>
        </div>

        <div className="form-group">
          <label>Routing Function:</label>
          <input 
            type="text" 
            value={routerFn} 
            onChange={(e) => setRouterFn(e.target.value)}
            placeholder="e.g. route_after_router"
          />
        </div>

        <div className="routes-section">
          <div className="routes-header">
            <span>Route Key</span>
            <span>Destination</span>
          </div>
          {routes.map((route, index) => (
            <div key={index} className="route-row">
              <input 
                type="text" 
                value={route.key} 
                onChange={(e) => handleRouteChange(index, "key", e.target.value)}
                placeholder="key"
              />
              <select 
                value={route.target} 
                onChange={(e) => handleRouteChange(index, "target", e.target.value)}
              >
                <option value="">Select Destination</option>
                <option value="__end__">END</option>
                {nodes.filter(n => n.type === "agentNode" || n.type === "toolNode").map(n => (
                  <option key={n.id} value={n.id}>{n.id}</option>
                ))}
              </select>
              <button className="remove-route-btn" onClick={() => handleRemoveRoute(index)}>×</button>
            </div>
          ))}
          <button className="add-row-btn" onClick={handleAddRoute}>+ Add Route Mapping</button>
        </div>

        <div className="modal-actions">
          <button className="cancel-btn" onClick={onClose}>Cancel</button>
          <button className="submit-btn" onClick={handleSubmit}>Add Route</button>
        </div>
      </div>
    </div>
  );
};

export default ConditionalRouteModal;
