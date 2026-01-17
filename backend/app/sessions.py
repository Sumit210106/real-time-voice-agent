import uuid
import datetime

sessions = {}

def create_session(ws):
    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "ws":  ws,
        "context" : "" ,
        "state":  "idle" ,
        "created_at": datetime.datetime.now()
    }
    return session_id


def remove_sessions(session_id):
    if session_id in sessions:
        del sessions[session_id]
    

def get_sessions(session_id):
    return sessions.get(session_id)

