from fastapi import WebSocket , WebSocketDisconnect
from .sessions import create_session, remove_session
import numpy as np
import json
from app.audio.vad import VoiceActivityDetector
from app.audio.utterance import UtteranceCollector
from app.stt.dummy import DummySTT

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
                print(f"[{session_id}] Audio chunk received (json mode)")
            
            else:
                print(f"[{session_id}] Unknown message type:", msg_type)
                await websocket.send_json({
                    "type": "error",
                    "message": "Unknown message type"
                })

    except WebSocketDisconnect: 
        remove_sessions(session_id)
        print(f"[{session_id}] Disconnected")
      
      
        
class NoiseHero:
    def __init__(self, alpha:float = 0.95, floor:float = 0.1):
        self.alpha = alpha
        self.floor = floor
        self.noise_memory = None
        self.window = np.hamming(1024)
    
    def suppress(self, raw: np.ndarray) -> np.ndarray:
        if len(raw) != len(self.window):
            self.window = np.hamming(len(raw))


        # domain frequency
        fft_data = np.fft.rfft(raw * self.window)

        magnitude = np.abs(fft_data)
        phase = np.angle(fft_data)
        
        if self.noise_memory is None:
            self.noise_memory = magnitude.copy()
            return raw
        
        # gain
        snr = magnitude / (self.noise_memory + 1e-6)
        gain = snr / (snr + 1.0)
        
        # spectral floor
        gain = np.maximum(gain, self.floor)
        
        # update noise memory
        if np.mean(magnitude) < 0.05:
            self.noise_memory = self.alpha * self.noise_memory + (1 - self.alpha) * magnitude   
        
        # Reconstruct
        clean_mag = magnitude * gain
        clean_fft = clean_mag * np.exp(1j * phase)
        clean = np.fft.irfft(clean_fft, n=len(raw))
        
        return np.clip(clean, -1.0, 1.0).astype(np.float32)
    
    

    
# binary audio ws
async def audio_ws(websocket: WebSocket):
    await websocket.accept()
    print("Audio WS connected")

    noise_hero = NoiseHero()
    vad = VoiceActivityDetector()
    collector = UtteranceCollector()
    stt = DummySTT()
    
    try:
        while True:
            data = await websocket.receive_bytes()
            samples = np.frombuffer(data,dtype = np.float32)
            
            # print(f"samples -> {samples}")
            clean = noise_hero.suppress(samples)
            # print(clean)
            # print(f"clean -> {clean}")
            
            vad_result = vad.process(clean)
            print(f"VAD result: {vad_result}")
            
            event = vad_result["event"] if vad_result else None
            print(f"VAD event: {event}")
            
            utterance = collector.process(clean, event)
            
            if vad_result is not None:
                print("VAD:", vad_result)
        
        
            if utterance is not None:
                text = await stt.transcribe(utterance)
                print("TRANSCRIPT:", text)
                
            rms = np.sqrt(np.mean(clean**2))
            print(f"Chunk received: {len(clean)} samples | RMS: {rms:.5f}")
            
    except WebSocketDisconnect:
        print("Audio WS disconnected")
        
        