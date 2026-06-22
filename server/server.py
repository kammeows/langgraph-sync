from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import libcst as cst
import os
from pydantic import BaseModel
from typing import Optional, List
import traceback
import json
from dotenv import load_dotenv
from copilot.service import run_copilot_chat
from git_service import get_git_status, get_git_diff, create_pull_request

class CreatePRRequest(BaseModel):
    title: str
    body: str

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

app = FastAPI()

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

WORKSPACE_ROOT = os.path.join(os.path.dirname(__file__), "..")
load_dotenv(os.path.join(WORKSPACE_ROOT, ".env"))
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

class CopilotChatRequest(BaseModel):
    query: str
    graph_id: str

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

        file_path = None
        if graph_id:
            try:
                file_path = get_graph_file_path(graph_id)
            except Exception:
                pass

        analyzer = LangGraphAnalyzer(target_var=target_var, current_file_path=file_path, workspace_root=WORKSPACE_ROOT)
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

@app.get("/api/git/status")
async def git_status():
    return get_git_status()

@app.get("/api/git/diff")
async def git_diff():
    return {"diff": get_git_diff()}

@app.post("/api/git/create-pr")
async def git_create_pr(request: CreatePRRequest):
    res = create_pull_request(request.title, request.body)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to create PR"))
    return res

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

def apply_mutation_to_source(
    source_code: str,
    action: str,
    node_id: Optional[str] = None,
    new_id: Optional[str] = None,
    source: Optional[str] = None,
    target: Optional[str] = None,
    payload: Optional[dict] = None,
    target_var: Optional[str] = None,
    current_file_path: Optional[str] = None
) -> str:
    if action == "rename":
        module = cst.parse_module(source_code)
        transformer = RenameNodeTransformer(node_id, new_id)
        new_module = module.visit(transformer)
        return new_module.code

    elif action == "add_node":
        module = cst.parse_module(source_code)
        analyzer = LangGraphAnalyzer(target_var=target_var, current_file_path=current_file_path, workspace_root=WORKSPACE_ROOT)
        cst.metadata.MetadataWrapper(module).visit(analyzer)
        existing_nodes = set(analyzer.nodes.keys())
        existing_functions = set(analyzer.functions)

        if new_id:
            if new_id in existing_nodes or new_id in existing_functions:
                raise HTTPException(status_code=400, detail=f"Name '{new_id}' already exists.")
            new_node_id = new_id
        else:
            index = 1
            while f"node{index}" in existing_nodes: index += 1
            new_node_id = f"node{index}"
        
        return add_node_to_code(source_code, new_node_id)
    
    elif action == "delete_node":
        module = cst.parse_module(source_code)
        transformer = RemoveNodeTransformer(node_id)
        new_module = module.visit(transformer)
        return new_module.code

    elif action == "add_edge":
        if source == "__start__":
            return update_entry_point_in_code(source_code, target)
        else:
            # Check for duplication first
            module = cst.parse_module(source_code)
            analyzer = LangGraphAnalyzer(target_var=target_var, current_file_path=current_file_path, workspace_root=WORKSPACE_ROOT)
            cst.metadata.MetadataWrapper(module).visit(analyzer)
            
            if (source, target) in analyzer.edges:
                return source_code
            
            return add_edge_to_code(source_code, source, target)

    elif action == "delete_edge":
        module = cst.parse_module(source_code)
        if source == "__start__":
            transformer = RemoveEntryPointTransformer()
        else:
            condition = payload.get("condition") if payload else None
            transformer = RemoveEdgeTransformer(source, target, condition=condition)
        new_module = module.visit(transformer)
        return new_module.code

    elif action == "add_conditional_edge":
        # payload should contain {source, router_fn, mapping}
        if not payload:
            raise HTTPException(status_code=400, detail="Missing payload for conditional edge.")
        return add_conditional_edge_to_code(
            source_code, 
            source or payload.get("source"), 
            payload.get("router_fn"), 
            payload.get("mapping")
        )

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported mutation action: {action}")


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
        updated_code = apply_mutation_to_source(
            source_code=source_code,
            action=request.action,
            node_id=request.node_id,
            new_id=request.new_id,
            source=request.source,
            target=request.target,
            payload=request.payload,
            target_var=target_var,
            current_file_path=file_path
        )

        with open(file_path, "w", encoding="utf8") as f:
            f.write(updated_code)
            
        return parse_code_to_graph(updated_code, request.graph_id)

    except HTTPException: raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/copilot/chat")
async def copilot_chat(request: CopilotChatRequest):
    print(f"Copilot request received: {request.query}")
    
    file_path = get_graph_file_path(request.graph_id)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Graph file {file_path} not found.")
        
    with open(file_path, "r", encoding="utf8") as f:
        source_code = f.read()
        
    try:
        # Parse graph data to get context
        graph_data = parse_code_to_graph(source_code, request.graph_id)
        nodes_summary = [{"id": n["id"], "type": n.get("type"), "label": n.get("data", {}).get("label")} for n in graph_data.get("nodes", [])]
        edges_summary = [{"source": e["source"], "target": e["target"], "label": e.get("data", {}).get("label")} for e in graph_data.get("edges", [])]
    except Exception as e:
        nodes_summary = []
        edges_summary = []
        graph_data = {"nodes": [], "edges": [], "code": source_code}

    # Run the copilot chat via LLM service module
    try:
        result = await run_copilot_chat(request.query, nodes_summary, edges_summary)
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        return {
            "success": False,
            "message": f"AI service failed: {str(e)}",
            "graph": graph_data
        }

    # Parse response format dynamically
    if isinstance(result, list):
        mutations = result
        rejected = False
        message = "I have successfully applied the requested structural mutations to your graph."
    elif isinstance(result, dict):
        rejected = result.get("rejected", False)
        message = result.get("message", "")
        mutations = result.get("mutations", [])
        # In case the model wrapped mutations in a dictionary but didn't set them as a list
        if not isinstance(mutations, list):
            mutations = []
    else:
        rejected = True
        message = "Unexpected response format from AI service."
        mutations = []

    if rejected or not mutations:
        return {
            "success": False,
            "message": message or "I cannot perform that request as it does not involve a structural graph mutation.",
            "graph": graph_data
        }
    
    try:
        target_var = None
        graphs = get_available_graphs()
        selected = next((g for g in graphs if g["id"] == request.graph_id), None)
        if selected:
            target_var = selected["var"]
            
        current_code = source_code
        for mutation in mutations:
            action = mutation.get("action")
            current_code = apply_mutation_to_source(
                source_code=current_code,
                action=action,
                node_id=mutation.get("node_id"),
                new_id=mutation.get("new_id"),
                source=mutation.get("source"),
                target=mutation.get("target"),
                payload=mutation.get("payload"),
                target_var=target_var,
                current_file_path=file_path
            )

        with open(file_path, "w", encoding="utf8") as f:
            f.write(current_code)
            
        updated_graph = parse_code_to_graph(current_code, request.graph_id)
        return {
            "success": True,
            "message": message or "Mutations applied successfully.",
            "graph": updated_graph
        }
    except Exception as e:
        traceback.print_exc()
        return {
            "success": False,
            "message": f"Failed to apply mutations: {str(e)}",
            "graph": graph_data
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)