import logging
from fastapi import FastAPI, WebSocket, HTTPException
from .ws import websocket_handler, audio_ws , active_tasks
from pydantic import BaseModel
from app.sessions import get_session
from fastapi.middleware.cors import CORSMiddleware
from app.api.dashboard import router as dashboard_router

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],  
)

app.include_router(dashboard_router)

@app.on_event("startup")
async def startup_event():
    """Initialize critical components on startup."""
    logger.info("🚀 Starting up voice agent...")
    try:
        from .llm.groq_provider import GroqLLM
        llm = GroqLLM()
        logger.info("✅ Groq LLM initialized")
    except Exception as e:
        logger.warning(f"⚠️ Failed to pre-initialize Groq: {e}")

class ContextUpdate(BaseModel):
    context: str
    
@app.get('/health')
def health():
    return {"status": "Backend is running"}

@app.websocket('/ws')
async def websocket_endpoints(ws: WebSocket):
    await websocket_handler(ws)

@app.websocket('/ws/audio')
async def websocket_audio_endpoints(ws: WebSocket):
    await audio_ws(ws)
    
    
@app.post("/session/{session_id}/context")
async def update_voice_context(session_id: str, data: ContextUpdate):
    session = get_session(session_id)
    if not session:
        logger.warning(f"Context update failed: Session {session_id} not found.")
        raise HTTPException(status_code=404, detail="Session not found")
    
    session.system_prompt = data.context
    
    if session_id in active_tasks:
        active_tasks[session_id].cancel()
        logger.info(f"[{session_id}] Interrupted active response to apply new context.")
    
    logger.info(f"[{session_id}] Context successfully updated.")
    
    return {
        "status": "success",
        "session_id": session_id,
        "new_prompt": session.system_prompt
    }
    