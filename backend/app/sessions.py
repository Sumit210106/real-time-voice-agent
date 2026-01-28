import uuid
import datetime

from typing import Dict, List, Optional

class VoiceSession:
    def __init__(self, session_id: str, ws):
        self.session_id = session_id
        self.ws = ws
        self.created_at = datetime.datetime.now()
        
        self.history: List[Dict] = []
        self.system_prompt: str = "You are a helpful, concise AI voice assistant."
        
        self.is_playing : bool = False
    

sessions: Dict[str, VoiceSession] = {}

def create_session(ws):
    session_id = str(uuid.uuid4())
    sessions[session_id] = VoiceSession(session_id, ws)
    return session_id

def remove_session(session_id):
    if session_id in sessions:
        del sessions[session_id]
    
def get_session(session_id) -> Optional[VoiceSession]:
    return sessions.get(session_id)