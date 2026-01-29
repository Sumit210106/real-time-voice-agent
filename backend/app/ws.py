"""
WebSocket handlers for voice assistant - FIXED VERSION
Implements:
- Proper barge-in with immediate audio stop
- Optimized VAD settings for faster response
- Real-time context updates (Feature #5)
- Comprehensive metrics tracking (Feature #8)
- Multi-user session management (Feature #3)
"""

import time
import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect
from dataclasses import dataclass, asdict
import numpy as np

from .sessions import (
    create_session, 
    remove_session, 
    get_session, 
    update_session_context,
    add_to_history
)
from app.audio.vad import VoiceActivityDetector
from app.audio.utterance import UtteranceCollector
from app.stt.deepgram_stream import DeepgramStreamingSTT
from app.llm.groq_provider import GroqLLM
from app.tts.deepgram_tts import DeepgramTTS

logger = logging.getLogger(__name__)

# Provider instances with error handling
try:
    llm_provider = GroqLLM()
    tts_provider = DeepgramTTS()
except Exception as e:
    logger.error(f"Failed to initialize providers: {e}")
    raise

# Track active tasks and sessions
active_tasks: Dict[str, asyncio.Task] = {}
active_sessions: Dict[str, Dict[str, Any]] = {}

# ---------------------------------------------------------
# METRICS DATA CLASS
# ---------------------------------------------------------
@dataclass
class TurnMetrics:
    """Metrics for a single conversation turn"""
    vad_detection_ms: float
    stt_latency_ms: float
    llm_latency_ms: float
    llm_ttft_ms: float  # Time to first token
    tts_latency_ms: float
    e2e_latency_ms: float
    search_used: bool
    search_latency_ms: Optional[float]
    timestamp: str
    session_id: str
    user_text: str
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------
# CONTROL WEBSOCKET (Feature #5: Real-Time Context Updates)
# ---------------------------------------------------------
async def websocket_handler(websocket: WebSocket):
    """
    Control websocket for real-time context updates and session management.
    This enables pushing context to active voice sessions without interrupting them.
    
    Use cases:
    - Admin dashboard pushing new instructions
    - User preference updates
    - Dynamic context injection during conversation
    """
    await websocket.accept()
    session_id: Optional[str] = None
    uid = "unknown"
    
    logger.info(f"🎛️  [CONTROL WS CONNECTED]")
    
    try:
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_json(), 
                    timeout=300  # 5 min timeout
                )
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await websocket.send_json({"type": "ping"})
                continue
            
            msg_type = data.get("type")
            
            # ============= SESSION INITIALIZATION =============
            if msg_type == "init":
                session_id = data.get("session_id")
                user_id = data.get("user_id", "guest")
                
                if not session_id:
                    session_id = create_session(user_id=user_id)
                
                uid = session_id[-6:]
                
                await websocket.send_json({
                    "type": "ready",
                    "session_id": session_id,
                    "timestamp": datetime.utcnow().isoformat()
                })
                
                logger.info(f"✅ [CONTROL INIT] {uid} - User: {user_id}")
            
            # ============= REAL-TIME CONTEXT UPDATE =============
            elif msg_type == "context_update":
                if not session_id:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Session not initialized"
                    })
                    continue
                
                context = data.get("context", "")
                replace = data.get("replace", False)  # Replace vs append
                
                try:
                    # Update session context - this affects the active voice session
                    success = update_session_context(
                        session_id, 
                        context, 
                        replace=replace
                    )
                    
                    if success:
                        # Cancel active task to apply new context immediately
                        if session_id in active_tasks:
                            task = active_tasks[session_id]
                            if not task.done():
                                task.cancel()
                                logger.info(f"⚡ [TASK CANCELLED] {uid} - Applying new context")
                        
                        await websocket.send_json({
                            "type": "context_updated",
                            "success": True,
                            "session_id": session_id,
                            "timestamp": datetime.utcnow().isoformat()
                        })
                        
                        logger.info(
                            f"📝 [CONTEXT UPDATE] {uid} - "
                            f"{'Replaced' if replace else 'Appended'}: {context[:50]}..."
                        )
                    else:
                        raise Exception("Session not found")
                        
                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Context update failed: {str(e)}"
                    })
                    logger.error(f"❌ [CONTEXT UPDATE FAILED] {uid}: {e}")
            
            # ============= GET ACTIVE METRICS =============
            elif msg_type == "get_metrics":
                metrics = {
                    "type": "system_metrics",
                    "active_sessions": len(active_sessions),
                    "active_tasks": len(active_tasks),
                    "sessions": list(active_sessions.keys()),
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                await websocket.send_json(metrics)
            
            # ============= GET SESSION STATUS =============
            elif msg_type == "get_session_status":
                target_session = data.get("session_id", session_id)
                
                if target_session:
                    sess = get_session(target_session)
                    if sess:
                        await websocket.send_json({
                            "type": "session_status",
                            "session_id": target_session,
                            "status": {
                                "user_id": sess.user_id,
                                "created_at": sess.created_at.isoformat(),
                                "metrics": sess.get_metrics(),
                                "active": target_session in active_sessions
                            },
                            "timestamp": datetime.utcnow().isoformat()
                        })
                    else:
                        await websocket.send_json({
                            "type": "error",
                            "message": "Session not found"
                        })
            
            # ============= CLEAR CONVERSATION HISTORY =============
            elif msg_type == "clear_history":
                if session_id:
                    from .sessions import clear_history
                    success = clear_history(session_id)
                    await websocket.send_json({
                        "type": "history_cleared",
                        "success": success
                    })
                    if success:
                        logger.info(f"🗑️  [HISTORY CLEARED] {uid}")
            
            # ============= HEALTH CHECK =============
            elif msg_type == "ping":
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": datetime.utcnow().isoformat()
                })
            
            else:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unknown message type: {msg_type}"
                })
    
    except WebSocketDisconnect:
        logger.info(f"🔴 [CONTROL WS DISCONNECT] {uid}")
    except Exception as e:
        logger.error(f"❌ [CONTROL WS ERROR] {uid}: {e}", exc_info=True)
    finally:
        # Cleanup
        if session_id and session_id in active_sessions:
            del active_sessions[session_id]


# ---------------------------------------------------------
# AUDIO WEBSOCKET (Main Voice Pipeline)
# ---------------------------------------------------------
async def audio_ws(websocket: WebSocket):
    """
    Main audio websocket handler for voice conversation pipeline.
    
    Pipeline: Audio → VAD → STT → LLM → TTS → Audio
    
    Features:
    - Voice Activity Detection with custom thresholds
    - Barge-in support for natural interruption
    - Real-time transcription and captions
    - Comprehensive latency metrics
    - Multi-user session isolation
    
    FIXES:
    - Optimized VAD parameters for faster response
    - Proper barge-in with immediate audio stop
    - Reduced latency in speech detection
    """
    await websocket.accept()
    
    # Initialize session
    session_id = create_session(user_id="guest")
    uid = session_id[-6:]
    
    # Track session state
    active_sessions[session_id] = {
        "connected_at": datetime.utcnow().isoformat(),
        "turns": 0,
        "interruptions": 0,
        "total_latency": 0
    }
    
    logger.info(f"🟢 [AUDIO WS CONNECTED] {uid}")
    
    # Initialize pipeline components with OPTIMIZED settings
    vad = VoiceActivityDetector(
        noise_alpha=0.95,  # Faster noise adaptation
        threshold_multiplier=2.0,  # More sensitive
        min_speech_frames=2,  # Faster speech detection (was 3)
        hangover_frames=5  # Quicker silence detection (was 8)
    )
    collector = UtteranceCollector()
    
    # Agent state tracking
    agent_task: Optional[asyncio.Task] = None
    agent_speaking = False
    
    # Barge-in detection
    barge_start_ts: Optional[float] = None
    ai_speech_start_ts: Optional[float] = None
    
    # OPTIMIZED Barge-in configuration
    BARGE_IGNORE_AFTER_TTS = 1.5  # Reduced from 2.0 - faster barge-in
    BARGE_MIN_SPEECH = 0.5  # Reduced from 0.8 - more responsive (250ms)
    
    # Turn tracking
    first_speech_ts: Optional[float] = None
    last_final_ts: Optional[float] = None
    vad_end_ts: Optional[float] = None
    current_transcript = ""
    
    # Metrics tracking
    turn_count = 0
    
    async def on_transcript(text: str, is_final: bool = True):
        """Callback for STT transcription results"""
        nonlocal current_transcript, last_final_ts
        
        if not text.strip():
            return
        
        if is_final:
            current_transcript = text
            last_final_ts = time.perf_counter()
            
            # Send live captions to frontend (Feature #10)
            await websocket.send_json({
                "type": "user_transcription",
                "transcription": text,
                "is_final": True,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # Signal completion
            await websocket.send_json({
                "type": "user_transcription_complete",
                "timestamp": datetime.utcnow().isoformat()
            })
        else:
            # Send partial transcripts for real-time feedback
            await websocket.send_json({
                "type": "user_transcription",
                "transcription": text,
                "is_final": False,
                "timestamp": datetime.utcnow().isoformat()
            })
    
    # Initialize STT with streaming
    stt: Optional[DeepgramStreamingSTT] = None
    
    try:
        stt = DeepgramStreamingSTT(on_transcript=on_transcript)
        await stt.connect()
        
        # Main audio processing loop
        while True:
            msg = await websocket.receive()
            
            # Handle disconnection
            if msg.get("type") == "websocket.disconnect":
                break
            
            # Handle JSON control messages
            if "text" in msg:
                try:
                    data = await websocket.receive_json()
                    
                    # Handle client-side interrupt signal
                    if data.get("type") == "interrupt":
                        logger.info(f"⚡ [CLIENT INTERRUPT] {uid}")
                        
                        # Cancel agent task
                        if agent_task and not agent_task.done():
                            agent_task.cancel()
                            try:
                                await agent_task
                            except asyncio.CancelledError:
                                pass
                        
                        # Reset state
                        agent_task = None
                        agent_speaking = False
                        barge_start_ts = None
                        ai_speech_start_ts = None
                        
                        # Acknowledge interrupt
                        await websocket.send_json({
                            "type": "interrupt_ack",
                            "timestamp": datetime.utcnow().isoformat()
                        })
                        
                        continue
                except:
                    pass
            
            # Process audio bytes
            if "bytes" not in msg:
                continue
            
            pcm = msg["bytes"]
            
            # Convert to numpy array for processing
            samples = (
                np.frombuffer(pcm, dtype=np.int16)
                .astype(np.float32) / 32768.0
            )
            
            # Voice Activity Detection
            is_speech = vad.is_speech(samples)
            
            # Track first speech for latency metrics
            if is_speech and first_speech_ts is None:
                first_speech_ts = time.perf_counter()
                
                # Send visual feedback to user
                await websocket.send_json({
                    "type": "status",
                    "status": "listening",
                    "timestamp": datetime.utcnow().isoformat()
                })
            
            # Process utterance collection (handles turn detection)
            result = collector.process(
                samples,
                is_speech,
                len(samples) / 16000.0
            )
            
            # Send audio to STT
            await stt.send_audio(pcm)
            
            # ============= EARLY INTENT DETECTION =============
            # Don't process if collector indicates early detection
            if isinstance(result, str) and result == "EARLY":
                logger.debug(f"⚡ [EARLY-INTENT] {uid}")
                continue
            
            # ============= BARGE-IN DETECTION (IMPROVED) =============
            if agent_speaking:
                now = time.perf_counter()
                
                # Ignore barge-in immediately after TTS starts
                # (prevents false triggers from audio feedback)
                if ai_speech_start_ts and (now - ai_speech_start_ts) < BARGE_IGNORE_AFTER_TTS:
                    continue
                
                if is_speech:
                    # Start barge-in timer
                    if barge_start_ts is None:
                        barge_start_ts = now
                        logger.debug(f"🎤 [BARGE-IN DETECTION STARTED] {uid}")
                    
                    # Trigger barge-in after minimum speech duration
                    elif (now - barge_start_ts) >= BARGE_MIN_SPEECH:
                        logger.info(f"⚡ [BARGE-IN TRIGGERED] {uid} - "
                                  f"{(now - barge_start_ts):.2f}s of speech detected")
                        
                        # STEP 1: Send interrupt signal to frontend FIRST
                        await websocket.send_json({
                            "type": "interrupt",
                            "timestamp": datetime.utcnow().isoformat()
                        })
                        
                        # STEP 2: Cancel current agent response task
                        if agent_task and not agent_task.done():
                            agent_task.cancel()
                            try:
                                await agent_task
                            except asyncio.CancelledError:
                                pass
                        
                        # STEP 3: Update session metrics
                        session = get_session(session_id)
                        if session:
                            session.metrics["interruptions"] += 1
                        
                        active_sessions[session_id]["interruptions"] += 1
                        
                        # STEP 4: Reset agent state IMMEDIATELY
                        agent_task = None
                        agent_speaking = False
                        barge_start_ts = None
                        ai_speech_start_ts = None
                        
                        # STEP 5: CRITICAL - Send stop signal to clear any queued audio
                        await websocket.send_json({
                            "type": "stop_audio",
                            "reason": "barge_in",
                            "timestamp": datetime.utcnow().isoformat()
                        })
                        
                        logger.debug(f"🛑 [AUDIO STOP SIGNAL SENT] {uid}")
                        
                        # STEP 6: Brief pause to ensure clean state
                        await asyncio.sleep(0.1)
                else:
                    # Reset barge-in timer if silence detected
                    barge_start_ts = None
            
            # ============= TURN COMPLETION DETECTION =============
            if isinstance(result, np.ndarray):
                # Record VAD end time for metrics
                vad_end_ts = time.perf_counter()
                
                # Only process if we have valid transcript
                if not current_transcript.strip():
                    logger.debug(f"⚠️  [EMPTY TRANSCRIPT] {uid} - Skipping turn")
                    continue
                
                turn_count += 1
                active_sessions[session_id]["turns"] = turn_count
                
                logger.info(
                    f"🚀 [TURN #{turn_count}] {uid}: "
                    f"\"{current_transcript[:60]}{'...' if len(current_transcript) > 60 else ''}\""
                )
                
                # Send thinking status
                await websocket.send_json({
                    "type": "status",
                    "status": "thinking",
                    "timestamp": datetime.utcnow().isoformat()
                })
                
                # Create turn processing task
                agent_task = asyncio.create_task(
                    process_turn(
                        websocket=websocket,
                        session_id=session_id,
                        text=current_transcript,
                        first_speech_ts=first_speech_ts,
                        vad_end_ts=vad_end_ts,
                        last_final_ts=last_final_ts,
                        turn_number=turn_count
                    )
                )
                
                # Track active task
                active_tasks[session_id] = agent_task
                agent_speaking = True
                
                # Update AI speech start time
                ai_speech_start_ts = time.perf_counter()
                
                # Reset turn state
                current_transcript = ""
                first_speech_ts = None
                vad_end_ts = None
                barge_start_ts = None
    
    except WebSocketDisconnect:
        logger.info(f"🔴 [AUDIO WS DISCONNECT] {uid}")
    except Exception as e:
        logger.error(f"❌ [AUDIO WS ERROR] {uid}: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "message": "Internal server error occurred",
                "timestamp": datetime.utcnow().isoformat()
            })
        except:
            pass
    finally:
        # Cleanup
        try:
            if stt:
                await stt.disconnect()
        except Exception as e:
            logger.error(f"Error disconnecting STT: {e}")
        
        # Cancel any active agent task
        if agent_task and not agent_task.done():
            agent_task.cancel()
            try:
                await agent_task
            except asyncio.CancelledError:
                pass
        
        # Remove from tracking
        active_tasks.pop(session_id, None)
        active_sessions.pop(session_id, None)
        remove_session(session_id)
        
        logger.info(f"🔴 [AUDIO WS CLEANUP COMPLETE] {uid}")


# ---------------------------------------------------------
# TURN PROCESSING (LLM + TTS Pipeline)
# ---------------------------------------------------------
async def process_turn(
    websocket: WebSocket,
    session_id: str,
    text: str,
    first_speech_ts: Optional[float],
    vad_end_ts: Optional[float],
    last_final_ts: Optional[float],
    turn_number: int
):
    """
    Process a complete conversation turn through LLM and TTS.
    
    Implements:
    - Streaming LLM responses
    - Sentence-by-sentence TTS
    - Comprehensive metrics tracking
    - Real-time captions
    - Error handling with fallbacks
    """
    uid = session_id[-6:]
    
    # Timing metrics
    turn_start = time.perf_counter()
    vad_latency = 0
    stt_latency = 0
    llm_latency = 0
    llm_ttft = 0
    tts_latency = 0
    search_latency: Optional[float] = None
    search_used = False
    
    # Track if this is first audio chunk (for TTFT)
    first_audio = True
    full_response = ""
    
    try:
        # ============= CALCULATE VAD LATENCY =============
        if first_speech_ts and vad_end_ts:
            vad_latency = (vad_end_ts - first_speech_ts) * 1000
        
        # ============= CALCULATE STT LATENCY =============
        if first_speech_ts and last_final_ts:
            stt_latency = (last_final_ts - first_speech_ts) * 1000
        
        # ============= LLM PROCESSING =============
        llm_start = time.perf_counter()
        
        # Send speaking status
        await websocket.send_json({
            "type": "status",
            "status": "speaking",
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Stream response from LLM (sentence by sentence)
        async for sentence in llm_provider.get_response_stream(
            text=text,
            language="en",
            session_id=session_id
        ):
            if not sentence or not sentence.strip():
                continue
            
            full_response += sentence + " "
            
            # ============= TTS PROCESSING =============
            tts_start = time.perf_counter()
            
            try:
                audio = await tts_provider.generate_audio(sentence)
                tts_latency = (time.perf_counter() - tts_start) * 1000
            except Exception as e:
                logger.error(f"❌ [TTS ERROR] {uid}: {e}")
                # Continue with next sentence on TTS error
                continue
            
            # ============= FIRST CHUNK METRICS =============
            if first_audio:
                llm_ttft = (tts_start - llm_start) * 1000
                llm_latency = llm_ttft  # For first token
                
                # Calculate total E2E latency
                e2e_latency = (time.perf_counter() - turn_start) * 1000
                
                # Update session metrics
                session = get_session(session_id)
                if session:
                    session.update_metrics(
                        ttft=llm_ttft,
                        vad_latency=vad_latency,
                        stt_latency=stt_latency,
                        llm_latency=llm_latency,
                        tts_latency=tts_latency,
                        e2e_latency=e2e_latency
                    )
                
                # Send comprehensive metrics (Feature #8: Observability Dashboard)
                await websocket.send_json({
                    "type": "pipeline_metrics",
                    "metrics": {
                        "vad": round(vad_latency, 0),
                        "stt": round(stt_latency, 0),
                        "llm": round(llm_latency, 0),
                        "tts": round(tts_latency, 0),
                        "e2e": round(e2e_latency, 0),
                        "search": "AUTO"
                    },
                    "turn_number": turn_number
                })
                
                # Update session aggregate metrics
                if session_id in active_sessions:
                    active_sessions[session_id]["total_latency"] += e2e_latency
                
                # Log metrics for observability
                logger.info(
                    f"📊 [METRICS] {uid} Turn #{turn_number} - "
                    f"VAD: {vad_latency:.0f}ms | "
                    f"STT: {stt_latency:.0f}ms | "
                    f"LLM: {llm_ttft:.0f}ms | "
                    f"TTS: {tts_latency:.0f}ms | "
                    f"E2E: {e2e_latency:.0f}ms"
                )
                
                first_audio = False
            
            # ============= STREAM AUDIO TO CLIENT =============
            await websocket.send_bytes(audio)
            
            # ============= SEND LIVE CAPTIONS (partial) =============
            await websocket.send_json({
                "type": "partial_agent_response",
                "ai_partial": full_response.strip(),
                "timestamp": datetime.utcnow().isoformat()
            })
        
        # ============= TURN COMPLETE =============
        # Add to history
        add_to_history(session_id, "user", text)
        add_to_history(session_id, "assistant", full_response.strip())
        
        # Send agent response complete signal
        await websocket.send_json({
            "type": "agent_response_complete",
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Send completion signal
        await websocket.send_json({
            "type": "turn_complete",
            "turn_number": turn_number,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        logger.info(f"✅ [TURN COMPLETE] {uid} Turn #{turn_number}")
    
    except asyncio.CancelledError:
        # Barge-in interruption
        logger.info(f"✂️  [TURN CANCELLED] {uid} Turn #{turn_number} - Barge-in detected")
        
        # Send partial response as final if we have any
        if full_response.strip():
            await websocket.send_json({
                "type": "agent_response_complete",
                "timestamp": datetime.utcnow().isoformat()
            })
        
        await websocket.send_json({
            "type": "turn_cancelled",
            "reason": "barge_in",
            "turn_number": turn_number,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        raise  # Re-raise to properly handle cancellation
    
    except Exception as e:
        logger.error(f"❌ [TURN ERROR] {uid} Turn #{turn_number}: {e}", exc_info=True)
        
        try:
            await websocket.send_json({
                "type": "error",
                "message": "Failed to process turn",
                "turn_number": turn_number,
                "timestamp": datetime.utcnow().isoformat()
            })
        except:
            pass
    
    finally:
        # Cleanup task tracking
        active_tasks.pop(session_id, None)
        
        # Reset status
        try:
            await websocket.send_json({
                "type": "status",
                "status": "idle",
                "timestamp": datetime.utcnow().isoformat()
            })
        except:
            pass