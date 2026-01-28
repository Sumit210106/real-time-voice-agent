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
        user_list.append({
            "id": str(s.session_id)[-6:],
            "full_id": str(s.session_id), 
            "user_id": str(s.user_id),
            "turns": int(s.metrics.get("total_turns", 0)),
            "avg_ttft": round(float(s.metrics.get("avg_ttft", 0)), 3),
            "last_active": s.last_active.strftime("%H:%M:%S"),
            "is_playing": bool(s.is_playing)
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