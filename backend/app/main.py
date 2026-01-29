import logging
from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import websocket handlers and active tasks
from .ws import websocket_handler, audio_ws, active_tasks
from app.sessions import get_session, update_session_context
from app.api.dashboard import router as dashboard_router

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Voice Assistant API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],  
)

# Include dashboard router
app.include_router(dashboard_router)

@app.on_event("startup")
async def startup_event():
    """Warm up all services on startup for better first-request performance"""
    logger.info("🚀 Starting up voice agent...")

    # Warm up LLM
    try:
        from app.llm.groq_provider import GroqLLM
        llm = GroqLLM()
        
        # Use the new warmup method instead of get_response_stream
        success = await llm.warmup()
        if success:
            logger.info("✅ Groq LLM warmed")
        else:
            logger.warning("⚠️  LLM warmup failed")
    except Exception as e:
        logger.warning(f"⚠️  LLM warmup failed: {e}")

    # Warm up STT
    try:
        from app.stt.deepgram_stream import DeepgramStreamingSTT

        async def _noop(_): 
            pass

        stt = DeepgramStreamingSTT(on_transcript=_noop)
        await stt.connect()
        await stt.disconnect()

        logger.info("✅ Deepgram STT warmed")
    except Exception as e:
        logger.warning(f"⚠️  STT warmup failed: {e}")

    # Warm up TTS
    try:
        from app.tts.deepgram_tts import DeepgramTTS

        tts = DeepgramTTS()
        await tts.generate_audio("Hello")

        logger.info("✅ Deepgram TTS warmed")
    except Exception as e:
        logger.warning(f"⚠️  TTS warmup failed: {e}")

    logger.info("🔥 Startup warmup complete")


# ---------------------------------------------------------
# API MODELS
# ---------------------------------------------------------
class ContextUpdate(BaseModel):
    """Model for context update requests"""
    context: str
    replace: bool = False  # If True, replace; if False, append

    
# ---------------------------------------------------------
# HTTP ENDPOINTS
# ---------------------------------------------------------
@app.get('/health')
def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "voice-assistant-backend"
    }


@app.get('/status')
def status():
    """Get system status and metrics"""
    from app.sessions import get_session_count, get_all_sessions
    
    sessions = get_all_sessions()
    
    return {
        "active_sessions": get_session_count(),
        "active_tasks": len(active_tasks),
        "sessions": [
            {
                "session_id": sid,
                "user_id": sess.user_id,
                "turns": sess.metrics.get("total_turns", 0),
                "created_at": sess.created_at.isoformat(),
                "last_active": sess.last_active.isoformat()
            }
            for sid, sess in sessions.items()
        ]
    }


@app.post("/session/{session_id}/context")
async def update_voice_context(session_id: str, data: ContextUpdate):
    """
    Update session context in real-time (Feature #5).
    
    This endpoint allows updating the context of an active voice session
    without interrupting it. The new context will be used in subsequent
    LLM calls.
    
    Args:
        session_id: The session ID to update
        data: Context update data (context string and replace flag)
        
    Returns:
        Success status and updated context info
    """
    session = get_session(session_id)
    if not session:
        logger.warning(f"Context update failed: Session {session_id} not found.")
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Update context using the new function
    success = update_session_context(session_id, data.context, replace=data.replace)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update context")
    
    # Optionally cancel active task to apply new context immediately
    if session_id in active_tasks:
        task = active_tasks[session_id]
        if not task.done():
            task.cancel()
            logger.info(f"⚡ [{session_id[-6:]}] Interrupted active response to apply new context.")
    
    logger.info(f"✅ [{session_id[-6:]}] Context successfully updated.")
    
    return {
        "status": "success",
        "session_id": session_id,
        "context_replaced": data.replace,
        "new_context": session.get_full_system_prompt() if hasattr(session, 'get_full_system_prompt') else session.system_prompt
    }


@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and cleanup resources"""
    from app.sessions import remove_session
    
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Cancel any active tasks
    if session_id in active_tasks:
        task = active_tasks[session_id]
        if not task.done():
            task.cancel()
    
    remove_session(session_id)
    
    return {
        "status": "success",
        "session_id": session_id,
        "message": "Session deleted"
    }


@app.get("/session/{session_id}/metrics")
async def get_session_metrics(session_id: str):
    """Get detailed metrics for a specific session"""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "session_id": session_id,
        "user_id": session.user_id,
        "metrics": session.get_metrics(),
        "created_at": session.created_at.isoformat(),
        "last_active": session.last_active.isoformat()
    }


# ---------------------------------------------------------
# WEBSOCKET ENDPOINTS
# ---------------------------------------------------------
@app.websocket('/ws')
async def websocket_control_endpoint(ws: WebSocket):
    """
    Control WebSocket for session management and real-time context updates.
    
    This websocket handles:
    - Session initialization
    - Real-time context updates (Feature #5)
    - System metrics queries
    - Session status checks
    """
    await websocket_handler(ws)


@app.websocket('/ws/audio')
async def websocket_audio_endpoint(ws: WebSocket):
    """
    Audio WebSocket for voice conversation.
    
    This websocket handles:
    - Audio streaming (PCM 16-bit, 16kHz)
    - Voice Activity Detection
    - Speech-to-Text
    - LLM processing
    - Text-to-Speech
    - Barge-in detection
    - Real-time captions
    - Latency metrics
    """
    await audio_ws(ws)


@app.on_event("startup")
async def start_cleanup_task():
    """Start background task to cleanup inactive sessions"""
    import asyncio
    from app.sessions import cleanup_inactive_sessions
    
    async def cleanup_loop():
        while True:
            await asyncio.sleep(300)  
            try:
                removed = cleanup_inactive_sessions(max_idle_seconds=3600)
                if removed > 0:
                    logger.info(f"🧹 Cleaned up {removed} inactive sessions")
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
    
    asyncio.create_task(cleanup_loop())
    logger.info("🧹 Started session cleanup task")