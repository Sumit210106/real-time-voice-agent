from fastapi import FastAPI , WebSocket 
from .ws import websocket_handler , audio_ws

app = FastAPI()

@app.get('/')
def health():
    return {"status" : "Backend is running"}

@app.websocket('/ws')
async def websocket_endpoints(ws : WebSocket):
    await websocket_handler(ws)
    
    
@app.websocket('/ws/audio')
async def websocket_audio_endpoints(ws: WebSocket):
    await audio_ws(ws)
    
    