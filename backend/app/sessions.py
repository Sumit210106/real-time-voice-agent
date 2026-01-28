import uuid
import datetime
from typing import Dict, List, Optional

class VoiceSession:
    def __init__(self, session_id: str, user_id: str = "guest"):
        self.session_id = session_id
        self.user_id = user_id
        self.created_at = datetime.datetime.now()
        self.last_active = datetime.datetime.now()
        
        self.history: List[Dict] = []
        self.system_prompt: str = (
            "You are a helpful voice assistant. Use search tools for current events. "
            "CRITICAL: Keep spoken responses extremely brief (1-2 sentences). "
            "Never list long strings of numbers unless asked."
        )
        
        self.is_playing: bool = False
        self.metrics = {
            "total_turns": 0,
            "avg_ttft": 0.0,
            "tool_calls_count": 0,
            "last_latency": 0.0
        }

    def update_metrics(self, ttft: float = None, tool_used: bool = False):
        """Update session metrics for tracking performance."""
        if ttft is not None:
            self.metrics["total_turns"] += 1
            prev_avg = self.metrics["avg_ttft"]
            n = self.metrics["total_turns"]
            self.metrics["avg_ttft"] = ((prev_avg * (n - 1)) + ttft) / n
            self.metrics["last_latency"] = ttft
        
        if tool_used:
            self.metrics["tool_calls_count"] += 1
        
        self.last_active = datetime.datetime.now()

    def get_metrics(self) -> Dict:
        """Retrieve session metrics as JSON-serializable dict."""
        return {
            "total_turns": self.metrics["total_turns"],
            "avg_ttft": round(self.metrics["avg_ttft"], 3),
            "tool_calls_count": self.metrics["tool_calls_count"],
            "last_latency": round(self.metrics["last_latency"], 3)
        }

sessions: Dict[str, VoiceSession] = {}

def create_session(user_id: str = "guest") -> str:
    """Create a new session or return existing one for user."""
    for existing_id, s in sessions.items():
        if s.user_id == user_id:
            return existing_id
            
    session_id = str(uuid.uuid4())
    sessions[session_id] = VoiceSession(session_id, user_id)
    return session_id

def get_session(session_id: str) -> Optional[VoiceSession]:
    """Retrieve session and update last_active timestamp."""
    session = sessions.get(session_id)
    if session:
        session.last_active = datetime.datetime.now()
    return session

def remove_session(session_id: str):
    """Remove session from active sessions."""
    if session_id in sessions:
        sessions[session_id].is_playing = False
        del sessions[session_id]