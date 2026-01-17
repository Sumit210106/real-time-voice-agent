from fastapi import WebSocket , WebSocketDisconnect
from .sessions import create_session, remove_session

import json

'''websocket message will be like this -> 

{ "type": "control", "action": "start" }
{ "type": "status", "state": "listening" }
{ "type": "audio", "data": "..." }
{ "type": "transcript", "text": "hello" }

'''

async def websocket_handler(websocket :WebSocket):
    await websocket.accept()
    session_id = create_session(websocket)
    
    await websocket.send_json({
        "type" : "session" ,
        "session_id" : session_id
    })
    
    try : 
        while True :
            raw = await websocket.receive_text()
            
            try : 
                msg = json.loads(raw)
            
            except Exception : 
                await websocket.send_json({
                    "type" : "error" ,
                    "message" : "Invalid JSON"
                })
                continue
        
            msg_type = msg.get("type")
            
            if msg_type == 'control' :
                action = msg.get("action")
                print(f"[{session_id}] Control message:", action)

                if action == 'start':
                    await websocket.send_json({
                        "type" : "status",
                        "state" : "listening"
                    })
                
                elif action == 'stop':
                    await websocket.send_json({
                        "type" : "status",
                        "state" : "idle"
                    })
                    
            elif msg_type == 'audio':
                # audio logic 
                print(f"[{session_id}] Audio chunk received")
            
            else:
                print(f"[{session_id}] Unknown message type:", msg_type)
                await websocket.send_json({
                    "type": "error",
                    "message": "Unknown message type"
                })

    except WebSocketDisconnect: 
        remove_sessions(session_id)
        
        