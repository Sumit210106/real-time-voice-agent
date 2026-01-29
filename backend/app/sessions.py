import uuid
import datetime
import logging
import threading
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class VoiceSession:
    def __init__(self, session_id: str, user_id: str = "guest"):
        self.session_id = session_id
        self.user_id = user_id
        self.created_at = datetime.datetime.now()
        self.last_active = datetime.datetime.now()
        
        self.history: List[Dict] = []
        self.system_prompt: str = (
            "You are a helpful voice assistant. Use search tools for current events. "
            "Never list long strings of numbers unless asked."
        )
        
        self.dynamic_context: str = ""
        
        self.is_playing: bool = False
        self.metrics = {
            "total_turns": 0,
            "avg_ttft": 0.0,
            "tool_calls_count": 0,
            "last_latency": 0.0,
            "interruptions": 0,
            "vad_latency": 0.0,
            "stt_latency": 0.0,
            "llm_latency": 0.0,
            "tts_latency": 0.0,
            "e2e_latency": 0.0
        }

    def update_metrics(self, ttft: float = None, tool_used: bool = False, **kwargs):
        """Update session metrics for tracking performance."""
        if ttft is not None:
            self.metrics["total_turns"] += 1
            prev_avg = self.metrics["avg_ttft"]
            n = self.metrics["total_turns"]
            self.metrics["avg_ttft"] = ((prev_avg * (n - 1)) + ttft) / n
            self.metrics["last_latency"] = ttft
        
        if tool_used:
            self.metrics["tool_calls_count"] += 1
        
        for key, value in kwargs.items():
            if key in self.metrics and value is not None:
                self.metrics[key] = value
        
        self.last_active = datetime.datetime.now()

    def get_metrics(self) -> Dict:
        """Retrieve session metrics as JSON-serializable dict."""
        return {
            "total_turns": self.metrics["total_turns"],
            "avg_ttft": round(self.metrics["avg_ttft"], 3),
            "tool_calls_count": self.metrics["tool_calls_count"],
            "last_latency": round(self.metrics["last_latency"], 3),
            "interruptions": self.metrics["interruptions"],
            "vad_latency": round(self.metrics.get("vad_latency", 0.0), 2),
            "stt_latency": round(self.metrics.get("stt_latency", 0.0), 2),
            "llm_latency": round(self.metrics.get("llm_latency", 0.0), 2),
            "tts_latency": round(self.metrics.get("tts_latency", 0.0), 2),
            "e2e_latency": round(self.metrics.get("e2e_latency", 0.0), 2)
        }
    
    def get_full_system_prompt(self) -> str:
        """Get system prompt with dynamic context appended."""
        if self.dynamic_context:
            return f"{self.system_prompt}\n\nAdditional Context:\n{self.dynamic_context}"
        return self.system_prompt

sessions: Dict[str, VoiceSession] = {}
_sessions_lock = threading.Lock()

def create_session(user_id: str = "guest") -> str:
    """Create a new session or return existing one for user."""
    with _sessions_lock:
        
        session_id = str(uuid.uuid4())
        sessions[session_id] = VoiceSession(session_id, user_id)
        logger.info(f"✨ [SESSION CREATED] {session_id[-6:]} - User: {user_id}")
        return session_id

def get_session(session_id: str) -> Optional[VoiceSession]:
    """Retrieve session and update last_active timestamp."""
    with _sessions_lock:
        session = sessions.get(session_id)
        if session:
            session.last_active = datetime.datetime.now()
        return session

def remove_session(session_id: str):
    """Remove session from active sessions."""
    with _sessions_lock:
        if session_id in sessions:
            session = sessions[session_id]
            session.is_playing = False
            
            duration = (datetime.datetime.now() - session.created_at).total_seconds()
            logger.info(
                f"🗑️  [SESSION REMOVED] {session_id[-6:]} - "
                f"Duration: {duration:.0f}s, Turns: {session.metrics['total_turns']}"
            )
            
            del sessions[session_id]

def update_session_context(session_id: str, context: str, replace: bool = False) -> bool:
    """
    Update session's dynamic context in real-time (Feature #5).
    
    This allows pushing new context/instructions to an active voice session
    without restarting it. The context will be used in subsequent LLM calls.
    
    Args:
        session_id: Session identifier
        context: New context to add/replace
        replace: If True, replace existing dynamic context; if False, append
        
    Returns:
        True if update successful, False otherwise
    """
    with _sessions_lock:
        session = sessions.get(session_id)
        
        if not session:
            logger.warning(f"⚠️  [SESSION NOT FOUND] {session_id[-6:]}")
            return False
        
        if replace:
            session.dynamic_context = context
            logger.info(f"🔄 [CONTEXT REPLACED] {session_id[-6:]}: {context[:50]}...")
        else:
            if session.dynamic_context:
                session.dynamic_context += "\n\n" + context
            else:
                session.dynamic_context = context
            logger.info(f"➕ [CONTEXT APPENDED] {session_id[-6:]}: {context[:50]}...")
        
        session.last_active = datetime.datetime.now()
        
        return True

def add_to_history(session_id: str, role: str, content: str, metadata: Optional[Dict] = None) -> bool:
    """
    Add a message to conversation history.
    
    Args:
        session_id: Session identifier
        role: Message role ('user' or 'assistant')
        content: Message content
        metadata: Optional metadata (latency, tokens, etc.)
        
    Returns:
        True if successful, False otherwise
    """
    with _sessions_lock:
        session = sessions.get(session_id)
        
        if not session:
            return False
        
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        
        session.history.append(message)
        session.last_active = datetime.datetime.now()
        
        return True

def get_conversation_history(session_id: str, max_messages: Optional[int] = None) -> List[Dict]:
    """
    Get conversation history for a session.
    
    Args:
        session_id: Session identifier
        max_messages: Maximum number of recent messages to return
        
    Returns:
        List of messages (most recent first)
    """
    with _sessions_lock:
        session = sessions.get(session_id)
        
        if not session:
            return []
        
        history = session.history
        
        if max_messages:
            return history[-max_messages:]
        
        return history

def clear_history(session_id: str) -> bool:
    """
    Clear conversation history for a session.
    
    Args:
        session_id: Session identifier
        
    Returns:
        True if successful, False otherwise
    """
    with _sessions_lock:
        session = sessions.get(session_id)
        
        if not session:
            return False
        
        session.history = []
        session.metrics["total_turns"] = 0
        logger.info(f"🗑️  [HISTORY CLEARED] {session_id[-6:]}")
        
        return True

def get_all_sessions() -> Dict[str, VoiceSession]:
    """
    Get all active sessions (admin/monitoring use).
    
    Returns:
        Dictionary of all sessions
    """
    with _sessions_lock:
        return dict(sessions)

def get_session_count() -> int:
    """
    Get count of active sessions.
    
    Returns:
        Number of active sessions
    """
    with _sessions_lock:
        return len(sessions)

def cleanup_inactive_sessions(max_idle_seconds: int = 3600) -> int:
    """
    Remove sessions that have been inactive for too long.
    
    Args:
        max_idle_seconds: Maximum idle time before cleanup
        
    Returns:
        Number of sessions removed
    """
    now = datetime.datetime.now()
    removed_count = 0
    
    with _sessions_lock:
        sessions_to_remove = []
        
        for session_id, session in sessions.items():
            idle_time = (now - session.last_active).total_seconds()
            
            if idle_time > max_idle_seconds:
                sessions_to_remove.append(session_id)
        
        for session_id in sessions_to_remove:
            sessions.pop(session_id)
            removed_count += 1
            logger.info(f"🧹 [CLEANUP] Removed inactive session {session_id[-6:]}")
    
    if removed_count > 0:
        logger.info(f"🧹 [CLEANUP] Removed {removed_count} inactive sessions")
    
    return removed_count