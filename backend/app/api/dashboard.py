from fastapi import APIRouter, HTTPException
from ..sessions import sessions
import datetime
from pydantic import BaseModel

router = APIRouter(prefix="/api/admin", tags=["dashboard"])

class ContextUpdate(BaseModel):
    session_id: str
    context: str

@router.get("/stats")
async def get_system_stats():
    """
    Returns global metrics across all active users/sessions.
    """
    total_sessions = len(sessions)
    active_now = len([s for s in sessions.values() if s.is_playing])
    
    all_ttfts = [
        s.metrics["avg_ttft"] 
        for s in sessions.values() 
        if s.metrics.get("avg_ttft", 0) > 0
    ]
    avg_system_latency = sum(all_ttfts) / len(all_ttfts) if all_ttfts else 0
    
    total_tool_calls = sum([s.metrics.get("tool_calls_count", 0) for s in sessions.values()])
    
    user_list = []
    for s in sessions.values():

        last_u = ""
        last_a = ""
        if s.history:

            user_msgs = [m["content"] for m in s.history if m.get("role") == "user"]
            ai_msgs = [m["content"] for m in s.history if m.get("role") == "assistant"]
            if user_msgs: 
                last_u = user_msgs[-1][:100]  
            if ai_msgs: 
                last_a = ai_msgs[-1][:100]    
        
        user_list.append({
            "id": str(s.session_id)[-6:],
            "full_id": str(s.session_id), 
            "user_id": str(s.user_id),
            "turns": int(s.metrics.get("total_turns", 0)),
            "avg_ttft": round(float(s.metrics.get("avg_ttft", 0)), 3),
            "last_active": s.last_active.strftime("%H:%M:%S"),
            "is_playing": bool(s.is_playing),
            "last_transcript": last_u,  
            "last_response": last_a     
        })

    return {
        "timestamp": datetime.datetime.now().isoformat(),
        "sessions": {
            "total_created": total_sessions,
            "currently_speaking": active_now,
        },
        "performance": {
            "avg_ttft_seconds": round(avg_system_latency, 3),
            "total_web_searches": total_tool_calls
        },
        "active_users": user_list
    }

@router.post("/update-context")
async def update_agent_context(data: ContextUpdate):
    """
    Allows the admin to change the system prompt of a live session.
    Matches against either the full UUID or the 6-character Short ID.
    """
    target_session = None
    
    for sid, s in sessions.items():
        if sid == data.session_id or sid.endswith(data.session_id):
            target_session = s
            break
            
    if not target_session:
        raise HTTPException(status_code=404, detail="Session not found")
    target_session.system_prompt = data.context
    
    print(f"🛠️  [ADMIN] Context updated for session {target_session.session_id[:6]}")
    return {
        "status": "success", 
        "message": f"Context updated for session {data.session_id}",
        "new_prompt": target_session.system_prompt
    }

@router.get("/session/{session_id}/history")
async def get_user_history(session_id: str):
    """
    Retrieve conversation history for a specific session.
    Matches against either the full UUID or the 6-character short ID.
    """
    target_session = None
    
    # Try to find session by full ID or short ID
    for sid, s in sessions.items():
        if sid == session_id or sid.endswith(session_id) or sid[-6:] == session_id:
            target_session = s
            break
    
    if not target_session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    
    return {
        "session_id": target_session.session_id,
        "user_id": target_session.user_id,
        "created_at": target_session.created_at.isoformat(),
        "last_active": target_session.last_active.isoformat(),
        "metrics": target_session.get_metrics(),
        "messages": [
            {
                "role": msg.get("role", "unknown"),
                "content": msg.get("content", ""),
                "timestamp": msg.get("timestamp", "")
            }
            for msg in target_session.history
        ]
    }

@router.get("/sessions")
async def list_all_sessions():
    """
    Return all active sessions with their current status.
    """
    session_list = []
    
    for session_id, session in sessions.items():
        session_list.append({
            "id": session_id[-6:],
            "full_id": session_id,
            "user_id": session.user_id,
            "status": "speaking" if session.is_playing else "idle",
            "turns": session.metrics.get("total_turns", 0),
            "avg_ttft": round(session.metrics.get("avg_ttft", 0), 3),
            "last_active": session.last_active.isoformat()
        })
    
    return {
        "total_sessions": len(session_list),
        "sessions": session_list
    }