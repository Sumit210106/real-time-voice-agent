from fastapi import WebSocket, WebSocketDisconnect
from .sessions import create_session, remove_session ,get_session
import numpy as np
import json
import base64
import logging
import traceback
import asyncio
import time
from app.audio.vad import VoiceActivityDetector
from app.audio.utterance import UtteranceCollector
from app.stt.dummy import DummySTT
from app.audio.wav_util import float32_to_wav_bytes, calculate_duration
from app.stt.deepgram_provider import DeepgramSTT
from app.llm.groq_provider import GroqLLM
from app.tts.deepgram_tts import DeepgramTTS

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
    session_id = create_session(websocket)
    vad = VoiceActivityDetector()
    collector = UtteranceCollector()
    
    try:
        while True:
            message = await websocket.receive()
            
            if message["type"] == "websocket.disconnect":
                break
            
            if "bytes" in message:
                data = message["bytes"]
                samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0

                vad_result = vad.process(samples)
                event = vad_result.get("event") if vad_result else None
                
                session = get_session(session_id)
                
                if event == "speech_start" and session and session.is_playing:
                    if session_id in active_tasks:
                        active_tasks[session_id].cancel()
                        logger.info(f"[{session_id}] Active task cancelled due to Barge-In")
                        
                        if session.is_playing:
                            session.is_playing = False 
                            await websocket.send_json({"type": "interrupt"})
                    
                utterance = collector.process(samples, event)
                
                if utterance is not None:
                    task = asyncio.create_task(_process_utterance(websocket, session_id, utterance, stt_provider, llm_provider, tts_provider))
                    active_tasks[session_id] = task

    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        remove_session(session_id)
 
async def _process_utterance(websocket: WebSocket, session_id: str, utterance: np.ndarray, stt, llm, tts) -> None:
    uid = session_id[-6:]
    pipe_start = time.perf_counter()
    
    dur = len(utterance) / 16000
    print(f"\n{'━'*60}")
    print(f" ▶️  PIPELINE START | ID: {uid} | AUDIO: {dur:.2f}s")
    print(f"{'━'*60}")

    try:
        stt_now = time.perf_counter()
        transcript, lang = await stt.transcribe(float32_to_wav_bytes(utterance))
        stt_lat = time.perf_counter() - stt_now

        if not transcript or not transcript.strip():
            print(f" ❌ STT: [SILENCE/NOISE] ({stt_lat:.3f}s)")
            print(f"{'━'*60}\n")
            return

        print(f" 🟢 STT | \"{transcript}\"")
        print(f"    └─ Latency: {stt_lat:.3f}s")

        print(f" 🟢 LLM | Generating Response...")
        llm_now = time.perf_counter()
        
        session = get_session(session_id)
        if session: session.is_playing = True

        idx = 1
        async for sentence in llm.get_response_stream(transcript, lang, session_id):
            llm_lat = time.perf_counter() - llm_now
            
            tts_now = time.perf_counter()
            audio = await tts.generate_audio(sentence)
            tts_lat = time.perf_counter() - tts_now
            chunk_total = time.perf_counter() - pipe_start

            print(f"    ├─ CHUNK {idx}")
            print(f"    │  📝 Text: {sentence[:50]}{'...' if len(sentence) > 50 else ''}")
            print(f"    │  ⏱️  Latencies: LLM:{llm_lat:.2f}s | TTS:{tts_lat:.2f}s | TTFT:{chunk_total:.2f}s")
            
            if audio:
                await websocket.send_json({
                    "type": "partial_agent_response",
                    "ai_partial": sentence,
                    "stt_latency": stt_lat,
                    "llm_latency": llm_lat,
                    "tts_latency": tts_lat,
                    "total_latency": chunk_total
                })
                await websocket.send_bytes(audio)
            idx += 1

    
        total_time = time.perf_counter() - pipe_start
        print(f"{'─'*60}")
        print(f" ✅ FINISHED | ID: {uid}")
        print(f"    TOTAL PIPELINE TIME: {total_time:.3f}s")
        print(f"    BOTTLENECK: {max([('STT', stt_lat), ('LLM', llm_lat)], key=lambda x: x[1])[0]}")
        print(f"{'━'*60}\n")
        
    except asyncio.CancelledError:
        print(f" 🛑 PIPELINE CANCELLED (Barge-In) | ID: {uid}")
        session = get_session(session_id)
        if session: 
            session.is_playing = False
        raise
    
    except Exception as e:
        print(f" 🛑 PIPELINE ERROR: {e}")
        if session: session.is_playing = False
        
    finally:
        if session_id in active_tasks and active_tasks.get(session_id) == asyncio.current_task():
            del active_tasks[session_id]
            logger.info(f"[{session_id}] Task registry cleaned up.")
            
        
async def _process_final_utterance(websocket: WebSocket, session_id: str, collector, 
                                   stt, llm, tts, last_utterance) -> None:
    """Process any remaining buffered audio on stream end."""
    try:
        utterance_to_process = None
        
        if hasattr(collector, 'buffer') and collector.buffer is not None and len(collector.buffer) > 0:
            try:
                if isinstance(collector.buffer, list):
                    utterance_to_process = np.concatenate(collector.buffer, axis=0) if len(collector.buffer) > 0 else None
                else:
                    utterance_to_process = np.asarray(collector.buffer, dtype=np.float32)
                if utterance_to_process is not None:
                    logger.info(f"[{session_id}] Flushed final buffer: {len(utterance_to_process)} samples")
            except Exception as e:
                logger.warning(f"[{session_id}] Failed to flush buffer: {e}")
        
        if utterance_to_process is None and last_utterance is not None:
            utterance_to_process = last_utterance
            logger.info(f"[{session_id}] Using last collected utterance as fallback")
        
        if utterance_to_process is not None and len(utterance_to_process) > 0:
            logger.info(f"[{session_id}] Starting to process final utterance...")
            await _process_utterance(websocket, session_id, utterance_to_process, stt_provider, llm_provider, tts_provider)
            logger.info(f"[{session_id}] Finished processing final utterance")
        else:
            logger.info(f"[{session_id}] No final utterance to process")
            await websocket.send_json({
                "type": "info",
                "message": "Stream ended with no speech detected"
            })
            
    except Exception as e:
        logger.error(f"[{session_id}] Final utterance processing error: {e}", exc_info=True)