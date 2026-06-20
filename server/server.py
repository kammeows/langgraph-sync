from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import libcst as cst
import os
from pydantic import BaseModel
from typing import Optional
import traceback

# Import our parser and transformer
from parser_libcst import (
    LangGraphAnalyzer, 
    ToolCallVisitor, 
    RenameNodeTransformer, 
    RemoveEdgeTransformer,
    RemoveNodeTransformer,
    RemoveEntryPointTransformer, # Added
    add_node_to_code,
    add_edge_to_code,
    update_entry_point_in_code,
    add_conditional_edge_to_code
)
from transform import transform_to_react_flow

import json

app = FastAPI()

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

WORKSPACE_ROOT = os.path.join(os.path.dirname(__file__), "..")
LANGGRAPH_JSON_PATH = os.path.join(WORKSPACE_ROOT, "langgraph.json")

def get_available_graphs():
    if os.path.exists(LANGGRAPH_JSON_PATH):
        try:
            with open(LANGGRAPH_JSON_PATH, "r", encoding="utf8") as f:
                data = json.load(f)
            graphs = data.get("graphs", {})
            result = []
            for g_id, path_val in graphs.items():
                # path_val is usually "./agent.py:graph"
                parts = path_val.split(":")
                file_path = parts[0]
                var_name = parts[1] if len(parts) > 1 else "graph"
                result.append({
                    "id": g_id,
                    "file": file_path,
                    "var": var_name
                })
            return result
        except Exception as e:
            print("Error parsing langgraph.json:", e)
    
    # Fallback to default
    return [{"id": "default", "file": "agent.py", "var": "graph"}]

def get_graph_file_path(graph_id: str):
    graphs = get_available_graphs()
    selected = next((g for g in graphs if g["id"] == graph_id), None)
    if not selected:
        selected = graphs[0]
    
    # Resolve relative to workspace root
    file_path = selected["file"]
    if file_path.startswith("./"):
        file_path = file_path[2:]
    return os.path.join(WORKSPACE_ROOT, file_path)

class MutationRequest(BaseModel):
    action: str
    graph_id: Optional[str] = None # Added for multi-graph
    source: Optional[str] = None
    target: Optional[str] = None
    node_id: Optional[str] = None
    new_id: Optional[str] = None
    payload: Optional[dict] = None

class SyncRequest(BaseModel):
    code: str
    graph_id: Optional[str] = None

def parse_code_to_graph(source_code: str, graph_id: Optional[str] = None):

    try:
        module = cst.parse_module(source_code)
        wrapper = cst.metadata.MetadataWrapper(module)

        target_var = None
        if graph_id:
            graphs = get_available_graphs()
            selected = next((g for g in graphs if g["id"] == graph_id), None)
            if selected:
                target_var = selected["var"]

        analyzer = LangGraphAnalyzer(target_var=target_var)
        wrapper.visit(analyzer)

        tool_visitor = ToolCallVisitor()
        module.visit(tool_visitor)

        flow_data = transform_to_react_flow(analyzer, tool_visitor)
        flow_data["code"] = source_code
        return flow_data
    except Exception as e:
        traceback.print_exc()
        # Return a "Broken State" instead of crashing. This lets the UI load.
        return {
            "nodes": [
                {
                    "id": "__start__",
                    "type": "startNode",
                    "position": {"x": 0, "y": 0},
                    "data": {"label": "START", "isEditable": False, "deletable": False}
                }
            ],
            "edges": [],
            "warnings": [{
                "type": "error", 
                "message": f"CRITICAL ERROR: {str(e)}. The graph cannot be parsed. Please check your Python code for syntax errors or inconsistent node names."
            }],
            "code": source_code,
            "state_schema": {"name": "Error", "fields": {}}
        }

@app.post("/api/graph/sync")
async def sync_graph(request: SyncRequest):
    """Sync graph from provided code without saving to file."""
    try:
        # Pass graph_id if provided so parser knows what to look for
        return parse_code_to_graph(request.code, request.graph_id)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Sync failed: {str(e)}")

@app.get("/api/graphs")
async def list_graphs():
    return get_available_graphs()

@app.get("/api/graph")
async def get_graph(graph_id: Optional[str] = None):
    try:
        file_path = get_graph_file_path(graph_id)
        if not os.path.exists(file_path):
            return {"nodes": [], "edges": [], "code": ""}
            
        with open(file_path, "r", encoding="utf8") as f:
            source_code = f.read()

        return parse_code_to_graph(source_code, graph_id)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/graph/upload")
async def upload_code(file: UploadFile = File(...)):
    if not file.filename.endswith('.py'):
        raise HTTPException(status_code=400, detail="Only .py files are allowed")
    
    try:
        content = await file.read()
        source_code = content.decode("utf-8")
        return parse_code_to_graph(source_code)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/graph/mutate")
async def mutate_graph(request: MutationRequest):
    print(f"Mutation received: {request.action}")
    
    file_path = get_graph_file_path(request.graph_id)
    if not os.path.exists(file_path):
         raise HTTPException(status_code=404, detail=f"{file_path} not found")

    with open(file_path, "r", encoding="utf8") as f:
        source_code = f.read()
    
    target_var = None
    if request.graph_id:
        graphs = get_available_graphs()
        selected = next((g for g in graphs if g["id"] == request.graph_id), None)
        if selected:
            target_var = selected["var"]
    
    try:
        if request.action == "rename":
            module = cst.parse_module(source_code)
            transformer = RenameNodeTransformer(request.node_id, request.new_id)
            new_module = module.visit(transformer)
            updated_code = new_module.code

        elif request.action == "add_node":
            module = cst.parse_module(source_code)
            analyzer = LangGraphAnalyzer(target_var=target_var)
            cst.metadata.MetadataWrapper(module).visit(analyzer)
            existing_nodes = set(analyzer.nodes.keys())
            existing_functions = set(analyzer.functions)

            if request.new_id:
                if request.new_id in existing_nodes or request.new_id in existing_functions:
                    raise HTTPException(status_code=400, detail=f"Name '{request.new_id}' already exists.")
                new_node_id = request.new_id
            else:
                index = 1
                while f"node{index}" in existing_nodes: index += 1
                new_node_id = f"node{index}"
            
            updated_code = add_node_to_code(source_code, new_node_id)
        
        elif request.action == "delete_node":
            module = cst.parse_module(source_code)
            transformer = RemoveNodeTransformer(request.node_id)
            new_module = module.visit(transformer)
            updated_code = new_module.code

        elif request.action == "add_edge":
            if request.source == "__start__":
                updated_code = update_entry_point_in_code(source_code, request.target)
            else:
                # Check for duplication first
                module = cst.parse_module(source_code)
                analyzer = LangGraphAnalyzer(target_var=target_var)
                cst.metadata.MetadataWrapper(module).visit(analyzer)
                
                if (request.source, request.target) in analyzer.edges:
                    return parse_code_to_graph(source_code, request.graph_id)
                
                updated_code = add_edge_to_code(source_code, request.source, request.target)

        elif request.action == "delete_edge":
            module = cst.parse_module(source_code)
            if request.source == "__start__":
                transformer = RemoveEntryPointTransformer()
            else:
                condition = request.payload.get("condition") if request.payload else None
                transformer = RemoveEdgeTransformer(request.source, request.target, condition=condition)
            new_module = module.visit(transformer)
            updated_code = new_module.code

        elif request.action == "add_conditional_edge":
            # payload should contain {source, router_fn, mapping}
            payload = request.payload
            updated_code = add_conditional_edge_to_code(
                source_code, 
                payload["source"], 
                payload["router_fn"], 
                payload["mapping"]
            )

        else:
            return {"status": "success", "received": request.action}

        with open(file_path, "w", encoding="utf8") as f:
            f.write(updated_code)
            
        return parse_code_to_graph(updated_code, request.graph_id)

    except HTTPException: raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)