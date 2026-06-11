from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import libcst as cst
import os
from pydantic import BaseModel
from typing import Optional
import traceback

# Import our parser and transformer
from parser_libcst import LangGraphAnalyzer, ToolCallVisitor
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
    payload: Optional[dict] = None

def parse_code_to_graph(source_code: str):
    try:
        module = cst.parse_module(source_code)

        analyzer = LangGraphAnalyzer()
        module.visit(analyzer)

        tool_visitor = ToolCallVisitor()
        module.visit(tool_visitor)

        flow_data = transform_to_react_flow(analyzer, tool_visitor)
        # Include source code in the response
        flow_data["code"] = source_code
        return flow_data
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=422, detail=f"Failed to parse code: {str(e)}")

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
    print(f"Payload: {request.model_dump()}")
    return {"status": "success", "received": request.action}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
