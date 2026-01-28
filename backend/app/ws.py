import time
import asyncio
from fastapi import WebSocket, WebSocketDisconnect
from .sessions import create_session, remove_session, get_session
from app.audio.vad import VoiceActivityDetector
from app.stt.deepgram_stream import DeepgramStreamingSTT
from app.llm.groq_provider import GroqLLM
from app.tts.deepgram_tts import DeepgramTTS
from app.stt.deepgram_provider import DeepgramSTT
from app.audio.vad import VoiceActivityDetector
from app.audio.wav_util import float32_to_wav_bytes, calculate_duration
import numpy as np
import logging

logger = logging.getLogger(__name__)

stt_provider = DeepgramSTT()
llm_provider = GroqLLM()
tts_provider = DeepgramTTS()

active_tasks = {}

'''
Websocket Protocol 

Control Messages (Client -> Server)
   - { "type": "control", "action": "start" } 
   - { "type": "control", "action": "stop" } 

Status & VAD (Server -> Client)
   - { "type": "status", "state": "listening" }  
   - { "type": "vad", "event": "speech_start" }  
   - { "type": "vad", "event": "speech_end" }    

Audio Data (Bi-directional)
   - Client -> Server: Binary PCM Chunks (bytes)
   - Server -> Client: { "type": "partial_agent_response", "audio": "base64...", "ai_partial": "text..." }

Interrupts (Server -> Client)
   - { "type": "interrupt" } 
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
        remove_session(session_id)
        print(f"[{session_id}] Disconnected")
      
      
        
class NoiseHero:
    def __init__(self, alpha:float = 0.95, floor:float = 0.1):
        self.alpha = alpha
        self.floor = floor
        self.noise_memory = None
        self.window = np.hamming(1024)
    
    def suppress(self, raw: np.ndarray) -> np.ndarray:
        FRAME_SIZE = 1024

        if len(raw) != FRAME_SIZE:
            raw = raw[:FRAME_SIZE] if len(raw) > FRAME_SIZE else np.pad(
                raw, (0, FRAME_SIZE - len(raw))
            )

        if self.noise_memory is None:
            self.noise_memory = np.zeros(FRAME_SIZE // 2 + 1)

        fft = np.fft.rfft(raw)
        mag = np.abs(fft)
        phase = np.angle(fft)

        snr = mag / (self.noise_memory + 1e-6)
        gain = snr / (snr + 1.0)

        self.noise_memory = 0.95 * self.noise_memory + 0.05 * mag

        clean_fft = gain * mag * np.exp(1j * phase)
        clean = np.fft.irfft(clean_fft, n=FRAME_SIZE)

        return clean.astype(np.float32)
    
async def audio_ws(websocket: WebSocket):
    await websocket.accept()
    session_id = create_session(user_id="guest_user")
    uid = session_id[-6:] 
    
    print(f"\n🟢 [CONNECTION] WebSocket Accepted | ID: {uid}")
    
    vad = VoiceActivityDetector()
    noise_hero = NoiseHero()
    
    last_speech_time = time.perf_counter()
    is_user_speaking = False
    current_transcript = "" 
    turn_anchor = None  

    async def handle_transcript(transcript: str):
        nonlocal current_transcript
        if transcript.strip():
            current_transcript = transcript 
            print(f"   📝 [TRANSCRIPTING] {uid}: \"{transcript}\"")
            await websocket.send_json({
                "type": "caption", 
                "text": transcript,
                "role": "user" 
            })
    
    stt_stream = DeepgramStreamingSTT(on_transcript=handle_transcript)
    await stt_stream.connect()
    
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            
            if "bytes" in message:
                data = message["bytes"]
                samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0

                clean_samples = noise_hero.suppress(samples)
                vad_result = vad.process(clean_samples)
                event = vad_result.get("event") if vad_result else None
                
                await stt_stream.send_audio(data)

                if event == "speech_start":
                    is_user_speaking = True
                    print(f"🎤 [VAD] User is SPEAKING... | ID: {uid}")
                    if session_id in active_tasks:
                        active_tasks[session_id].cancel()
                        await websocket.send_json({"type": "interrupt"})
                        print(f"🛑 [INTERRUPT] Barge-in detected, killing old task.")

                if event == "speech_end":
                    is_user_speaking = False
                    last_speech_time = time.perf_counter()
                    turn_anchor = time.perf_counter()  # THE ANCHOR: Set when speech ends
                    print(f"😶 [VAD] User stopped speaking (ANCHOR SET). Waiting for turn trigger...")

                silence_duration = time.perf_counter() - last_speech_time
                if not is_user_speaking and silence_duration > 0.8 and current_transcript.strip():
                    final_input = current_transcript
                    current_transcript = "" 
                    
                    print(f"\n🚀 [PIPELINE TRIGGER] Processing User Request: \"{final_input}\"")
                    
                    task = asyncio.create_task(
                        _process_text_to_audio(websocket, session_id, final_input, turn_anchor)
                    )
                    active_tasks[session_id] = task

    except Exception as e:
        print(f"💥 [SYSTEM ERROR] {e}")
    finally:
        print(f"🔴 [DISCONNECT] Closing Session: {uid}")
        try:
            await stt_stream.disconnect()
        except:
            pass
        remove_session(session_id)

async def _process_text_to_audio(websocket, session_id, transcript, turn_anchor):
    """
    Process user input through the full pipeline with streaming TTS.
    turn_anchor: absolute time when user stopped speaking (the "truth" anchor)
    """
    uid = session_id[-6:]
    session = get_session(session_id)
    if session: session.is_playing = True
    
    try:
        stt_start = turn_anchor
        llm_start = time.perf_counter()
        
        stt_latency = (llm_start - stt_start) * 1000
        
        first_sentence = True
        first_audio_sent = False
        tts_latency = 0
        tool_used = False
        
        print(f"   🧠 [LLM] Requesting response from Groq...")
        
        async for sentence in llm_provider.get_response_stream(transcript, "en", session_id):
            if first_sentence:
                tool_used = (sentence.lower().count("check") > 0 or 
                            sentence.lower().count("search") > 0)
                first_sentence = False
            
            print(f"   💬 [LLM SENTENCE] \"{sentence}\"")
            
            tts_start = time.perf_counter()
            audio = await tts_provider.generate_audio(sentence)
            tts_latency = (time.perf_counter() - tts_start) * 1000

            if audio and not first_audio_sent:
                llm_latency = (tts_start - llm_start) * 1000  
                actual_e2e = (time.perf_counter() - turn_anchor) * 1000  
                
                if session:
                    session.update_metrics(ttft=llm_latency/1000, tool_used=tool_used)
                
                await websocket.send_json({
                    "type": "pipeline_metrics",
                    "metrics": {
                        "vad": 300,  
                        "stt": round(stt_latency, 0),
                        "llm": round(llm_latency, 0),
                        "tts": round(tts_latency, 0),
                        "e2e": round(actual_e2e, 0),
                        "search": "Tavily" if tool_used else "None"
                    }
                })
                
                print(f"   📊 [METRICS] VAD: {300}ms | STT: {stt_latency:.0f}ms | LLM: {llm_latency:.0f}ms | TTS: {tts_latency:.0f}ms | E2E: {actual_e2e:.0f}ms")
                first_audio_sent = True

            if audio:
                await websocket.send_bytes(audio)
                
                await websocket.send_json({
                    "type": "partial_agent_response",
                    "ai_partial": sentence
                })
        
        total_time = (time.perf_counter() - turn_anchor) * 1000
        print(f"✅ [PIPELINE COMPLETE] Total Time from User Input: {total_time:.0f}ms\n")
                
    except asyncio.CancelledError:
        print(f"✂️  [PIPELINE CANCELLED] ID: {uid}")
    finally:
        if session: session.is_playing = False