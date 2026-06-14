from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import libcst as cst
import os
from pydantic import BaseModel
from typing import Optional
import traceback

# Import our parser and transformer
from parser_libcst import LangGraphAnalyzer, ToolCallVisitor, RenameNodeTransformer
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
    
    if request.action == "rename":
        try:
            with open(AGENT_FILE, "r", encoding="utf8") as f:
                source_code = f.read()
            
            module = cst.parse_module(source_code)
            transformer = RenameNodeTransformer(request.node_id, request.new_id)
            new_module = module.visit(transformer)
            
            with open(AGENT_FILE, "w", encoding="utf8") as f:
                f.write(new_module.code)
                
            return parse_code_to_graph(new_module.code)
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Rename failed: {str(e)}")

    return {"status": "success", "received": request.action}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
