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
    add_node_to_code,
    add_edge_to_code
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

AGENT_FILE = os.path.join(os.path.dirname(__file__), "..", "agent.py")

class MutationRequest(BaseModel):
    action: str
    source: Optional[str] = None
    target: Optional[str] = None
    node_id: Optional[str] = None
    new_id: Optional[str] = None # Added for rename
    payload: Optional[dict] = None

class SyncRequest(BaseModel):
    code: str

def parse_code_to_graph(source_code: str):
    try:
        module = cst.parse_module(source_code)
        wrapper = cst.metadata.MetadataWrapper(module)

        analyzer = LangGraphAnalyzer()
        wrapper.visit(analyzer)

        tool_visitor = ToolCallVisitor()
        module.visit(tool_visitor)

        flow_data = transform_to_react_flow(analyzer, tool_visitor)
        # Include source code in the response
        flow_data["code"] = source_code
        return flow_data
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=422, detail=f"Failed to parse code: {str(e)}")

@app.post("/api/graph/sync")
async def sync_graph(request: SyncRequest):
    """Sync graph from provided code without saving to file."""
    try:
        return parse_code_to_graph(request.code)
    except Exception as e:
        # If code has syntax errors, we might want to return 422 or similar
        # but for robustness, we could just return the last known good state 
        # (handled by frontend usually, or we can catch here)
        raise HTTPException(status_code=422, detail=f"Sync failed: {str(e)}")

@app.get("/api/graph")
async def get_graph():
    try:
        if not os.path.exists(AGENT_FILE):
            return {"nodes": [], "edges": [], "code": ""}
            
        with open(AGENT_FILE, "r", encoding="utf8") as f:
            source_code = f.read()

        return parse_code_to_graph(source_code)
        
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
    
    if not os.path.exists(AGENT_FILE):
         raise HTTPException(status_code=404, detail="agent.py not found")

    with open(AGENT_FILE, "r", encoding="utf8") as f:
        source_code = f.read()
    
    try:
        if request.action == "rename":
            module = cst.parse_module(source_code)
            transformer = RenameNodeTransformer(request.node_id, request.new_id)
            new_module = module.visit(transformer)
            updated_code = new_module.code

        elif request.action == "add_node":
            module = cst.parse_module(source_code)
            analyzer = LangGraphAnalyzer()
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

        elif request.action == "add_edge":
            # Check for duplication first
            module = cst.parse_module(source_code)
            analyzer = LangGraphAnalyzer()
            cst.metadata.MetadataWrapper(module).visit(analyzer)
            
            if (request.source, request.target) in analyzer.edges:
                return parse_code_to_graph(source_code)
            
            updated_code = add_edge_to_code(source_code, request.source, request.target)

        elif request.action == "delete_edge":
            module = cst.parse_module(source_code)
            transformer = RemoveEdgeTransformer(request.source, request.target)
            new_module = module.visit(transformer)
            updated_code = new_module.code

        else:
            return {"status": "success", "received": request.action}

        with open(AGENT_FILE, "w", encoding="utf8") as f:
            f.write(updated_code)
            
        return parse_code_to_graph(updated_code)

    except HTTPException: raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
