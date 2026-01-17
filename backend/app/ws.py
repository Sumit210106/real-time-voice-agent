from fastapi import WebSocket , WebSocketDisconnect
from .sessions import create_session, remove_sessions


async def websocket_handler(websocket :WebSocket):
    await websocket.accept()
    session_id = create_session(websocket)
    
    # send id to client 
    await websocket.send_json({
        "type" : "session" ,
        "session_id" : session_id
    })
    
    try : 
        while True :
            data = await websocket.receive_text()
            # echo back
            await websocket.send_text(f"echo: {data}")
    
    except WebSocketDisconnect: 
        remove_sessions(session_id)
        
        