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
    print("Audio WS connected")
    session_id = create_session(websocket)
    print(f"[{session_id}] Session created")
    
    noise_hero = NoiseHero()
    vad = VoiceActivityDetector()
    collector = UtteranceCollector()
    
    last_utterance = None  
    
    try:
        while True:
            try:
                message = await websocket.receive()
                
                if message["type"] == "websocket.disconnect":
                    logger.info(f"[{session_id}] WebSocket disconnect signal received")
                    break
                
                if "text" in message:
                    try:
                        msg = json.loads(message["text"])
                    except json.JSONDecodeError as e:
                        logger.warning(f"Invalid JSON received: {e}")
                        await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                        continue
                    
                    msg_type = msg.get("type")
                    
                    if msg_type == "audio_end":
                        logger.info(f"[{session_id}] Audio stream ended by client")
                        await _process_final_utterance(websocket, session_id, collector, stt_provider, llm_provider, tts_provider, last_utterance)
                    else:
                        logger.debug(f"[{session_id}] Received control message: {msg_type}")
                
                elif "bytes" in message:
                    data = message["bytes"]
                    
                    if len(data) < 2:
                        logger.warning(f"Received invalid audio chunk size: {len(data)}")
                        continue
                    
                    try:
                        samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                    except Exception as e:
                        logger.error(f"Audio conversion error: {e}")
                        continue
                    
                    clean = noise_hero.suppress(samples)
                    
                    vad_result = vad.process(clean)
                    event = vad_result.get("event") if vad_result else None
                    session = get_session(session_id)
                    
                    if event == "speech_start":
                        active_speech = True
                        if session and session.is_playing:
                            logger.info(f"[{session_id}] 🛑 Barge-in detected! Sending interrupt.")
                            session.is_playing = False 
                            await websocket.send_json({
                                "type": "interrupt",
                                "message": "User interrupted AI speech"
                            })
                    elif event == "speech_end":
                        active_speech = False
                    
                    utterance = collector.process(clean, event)
                    
                    if event in ["speech_start", "speech_end"]:
                        await websocket.send_json({
                            "type": "vad",
                            "event": event,
                            "timestamp": message.get("time", 0)
                        })
                    
                    if utterance is not None:
                        asyncio.create_task(_process_utterance(websocket, session_id, utterance, stt_provider, llm_provider, tts_provider))
                
                else:
                    logger.warning(f"[{session_id}] Unknown message type: {message}")
                    
            except WebSocketDisconnect:
                logger.info(f"[{session_id}] Client disconnected")
                break
            except Exception as e:
                logger.error(f"[{session_id}] Error processing message: {e}", exc_info=True)
                try:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Internal server error"
                    })
                except Exception as send_error:
                    logger.error(f"Failed to send error message: {send_error}")
                    break

    except WebSocketDisconnect:
        logger.info(f"[{session_id}] WebSocket disconnected")
    except Exception as e:
        logger.error(f"[{session_id}] Critical error: {e}", exc_info=True)
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except Exception as close_error:
            logger.error(f"Error closing WebSocket: {close_error}")
            
            
async def _process_utterance(websocket: WebSocket, session_id: str, utterance: np.ndarray, 
                             stt, llm, tts) -> None:
    """
    Handles the end-to-end voice pipeline: STT -> LLM -> TTS.
    Optimized for sub-second latency via parallel sentence-level TTS streaming.
    """
    start_time = time.perf_counter()
    uid = session_id[-6:]
    
    try:
        # 1. Basic Audio Validation
        duration = len(utterance) / 16000 
        if duration < 0.4: 
            return # Ignore micro-noises to save API costs

        print(f"\n[🚀 START PIPELINE | ID: {uid} | Audio: {duration:.2f}s]")

        # 2. STEP 1: STT (Speech to Text)
        wav_data = float32_to_wav_bytes(utterance)
        transcript, lang = await stt.transcribe(wav_data)
        
        if not transcript or not transcript.strip():
            print(f"DEBUG 🎙️  | {uid} | STT: [EMPTY]")
            return
        
        print(f"DEBUG 🎙️  | {uid} | STT: '{transcript}' | {time.perf_counter()-start_time:.2f}s")

        # 3. SET SESSION STATE (For Barge-in Detection)
        # We tell the session manager the AI is now generating a response
        session = get_session(session_id)
        if session:
            session.is_playing = True

        # 4. STEP 2 & 3: LLM & PARALLEL TTS
        print(f"DEBUG 🧠 | {uid} | LLM: Starting Stream...")
        
        # Helper function to generate audio and send via WebSocket concurrently
        async def generate_and_send(sentence_text):
            try:
                # Generate audio for just this sentence
                audio_bytes = await tts.generate_audio(sentence_text)
                
                if audio_bytes:
                    audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
                    await websocket.send_json({
                        "type": "partial_agent_response",
                        "text": transcript,
                        "ai_partial": sentence_text,
                        "audio": audio_b64
                    })
                    print(f"DEBUG 📡 | {uid} | Sent chunk | {time.perf_counter()-start_time:.2f}s")
            except Exception as tts_err:
                logger.error(f"TTS Parallel Task Error: {tts_err}")

        async for sentence in llm.get_response_stream(transcript, lang, session_id):
            asyncio.create_task(generate_and_send(sentence))

        print(f"DEBUG ✅ | {uid} | PIPELINE HANDED TO TASKS | Total: {time.perf_counter()-start_time:.2f}s")

    except Exception as e:
        print(f"DEBUG 🛑 | {uid} | ERROR: {str(e)}")
        session = get_session(session_id)
        if session:
            session.is_playing = False
             
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