from fastapi import FastAPI , WebSocket 
from .ws import websocket_handler

app = FastAPI()

@app.get('/')
def health():
    return {"status" : "Backend is running"}

@app.websocket('/ws')
async def websocket_endpoints(ws : WebSocket):
    await websocket_handler(ws)
    
    