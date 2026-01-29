"use client";

import React, { useState, useRef, useEffect } from "react";
import { Mic, MicOff } from "lucide-react";
import {
  initAudioContext,
  readTimeDomain,
  calcRMS,
  downsampleAndConvert,
  AudioStreamPlayer,
} from "@/utils/audio";

export default function VoiceMic() {
  const [isActive, setIsActive] = useState(false);
  const [volume, setVolume] = useState(0);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [agentSpeaking, setAgentSpeaking] = useState(false);

  type PipelineMetrics = {
    vad: number;
    stt: number;
    llm: number;
    tts: number;
    e2e: number;
  };

  type TranscriptTurn = {
    id: string;
    text: string;
    speaker: "user" | "ai";
    isComplete: boolean; // Track if message is finalized
  };

  const [turns, setTurns] = useState<TranscriptTurn[]>([]);
  const [currentMetrics, setCurrentMetrics] = useState<PipelineMetrics | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [latencyLogs, setLatencyLogs] = useState<string[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const audioRef = useRef<{ context: AudioContext; analyser: AnalyserNode } | null>(null);
  const playerRef = useRef<AudioStreamPlayer | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const rafRef = useRef<number | null>(null);
  const workletRef = useRef<AudioWorkletNode | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const bufferRef = useRef<Uint8Array | null>(null);
  const smoothRef = useRef(0);
  const maxRmsRef = useRef(0.02);
  const NOISE_FLOOR = 0.01;

  // Auto-scroll to bottom when turns change
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [turns]);

  const addLog = (msg: string) => {
    const timestamp = new Date().toLocaleTimeString();
    setLogs((prev) => [`[${timestamp}] ${msg}`, ...prev].slice(0, 15));
  };

  const addLatencyLog = (msg: string) => {
    const timestamp = new Date().toLocaleTimeString();
    setLatencyLogs((prev) => [`[${timestamp}] ${msg}`, ...prev].slice(0, 20));
  };

  /* ---------- Audio Pre-Init ---------- */
  useEffect(() => {
    let cancelled = false;
    const preInit = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ 
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true
          } 
        });
        if (cancelled) return;
        const { context, analyser } = initAudioContext(stream);
        await context.audioWorklet.addModule("/worklets/recorder-processor.js");
        await context.suspend();
        audioRef.current = { context, analyser };
        streamRef.current = stream;
        addLog("Audio pre-initialized");
      } catch (err) {
        console.error("Mic pre-init failed", err);
        addLog("⚠️ Mic pre-init failed");
      }
    };
    preInit();
    return () => { 
      cancelled = true; 
    };
  }, []);

  const updateLoop = () => {
    if (!audioRef.current || !bufferRef.current) return;
    const { analyser } = audioRef.current;
    readTimeDomain(analyser, bufferRef.current);
    const rms = calcRMS(bufferRef.current);
    const cleanRms = Math.max(0, rms - NOISE_FLOOR);
    
    if (cleanRms > maxRmsRef.current) {
      maxRmsRef.current = cleanRms;
    } else {
      maxRmsRef.current *= 0.96;
    }
    
    const currentMax = Math.max(maxRmsRef.current, 0.02);
    const percent = Math.min(cleanRms / currentMax, 1) * 100;
    smoothRef.current = smoothRef.current * 0.7 + percent * 0.3;
    setVolume(smoothRef.current);
    setIsSpeaking(smoothRef.current > 15);
    rafRef.current = requestAnimationFrame(updateLoop);
  };

  const startMic = async () => {
    try {
      addLog("🔌 Connecting to server...");
      const ws = new WebSocket("wss://real-time-voice-agent.onrender.com/ws/audio");
      // const ws = new WebSocket("ws://localhost:8000/ws/audio");
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;

      ws.onopen = () => {
        addLog("✅ Connected to server");
      };

      ws.onerror = (error) => {
        addLog("❌ WebSocket error");
        console.error("WebSocket error:", error);
      };

      ws.onclose = () => {
        addLog("🔌 Disconnected from server");
      };

      ws.onmessage = (event) => {
        if (typeof event.data === "string") {
          const msg = JSON.parse(event.data);

          if (msg.type === "interrupt" || msg.type === "stop_audio") {
            addLog("⚡ Barge-in detected");
            playerRef.current?.stop();
            setAgentSpeaking(false);
            return;
          }

          if (msg.type === "pipeline_metrics" && msg.metrics) {
            const m = msg.metrics;
            const sanitizedMetrics = {
              vad: Number(m.vad) || 0,
              stt: Number(m.stt) || 0,
              llm: Number(m.llm) || 0,
              tts: Number(m.tts) || 0,
              e2e: Number(m.e2e) || 0,
            };
            setCurrentMetrics(sanitizedMetrics);
            addLatencyLog(
              `VAD:${sanitizedMetrics.vad}ms | STT:${sanitizedMetrics.stt}ms | LLM:${sanitizedMetrics.llm}ms | TTS:${sanitizedMetrics.tts}ms | E2E:${sanitizedMetrics.e2e}ms`
            );
          }

          // Handle AI partial responses
          if (msg.type === "partial_agent_response") {
            addLog("🤖 AI responding...");
            setAgentSpeaking(true);
            
            setTurns((prev) => {
              const last = prev[prev.length - 1];
              
              // If last message is AI and not complete, update it
              if (last?.speaker === "ai" && !last.isComplete) {
                const updated = [...prev];
                updated[updated.length - 1] = { 
                  ...last, 
                  text: msg.ai_partial 
                };
                return updated;
              }
              
              // Otherwise create new AI message
              return [
                ...prev, 
                { 
                  id: `ai-${Date.now()}-${Math.random()}`, 
                  text: msg.ai_partial, 
                  speaker: "ai",
                  isComplete: false
                }
              ];
            });
          }

          // Handle complete AI response
          if (msg.type === "agent_response_complete") {
            addLog("✅ AI response complete");
            setAgentSpeaking(false);
            
            setTurns((prev) => {
              const last = prev[prev.length - 1];
              if (last?.speaker === "ai") {
                const updated = [...prev];
                updated[updated.length - 1] = { 
                  ...last, 
                  isComplete: true 
                };
                return updated;
              }
              return prev;
            });
          }

          // Handle user captions/transcriptions
          if (msg.type === "caption" || msg.type === "user_transcription") {
            const userText = msg.text || msg.transcription || "";
            addLog(`👤 User: ${userText.substring(0, 30)}...`);
            
            setTurns((prev) => {
              const last = prev[prev.length - 1];
              
              // If last message is user and not complete, update it
              if (last?.speaker === "user" && !last.isComplete) {
                const updated = [...prev];
                updated[updated.length - 1] = { 
                  ...last, 
                  text: userText 
                };
                return updated;
              }
              
              // Otherwise create new user message
              return [
                ...prev, 
                { 
                  id: `user-${Date.now()}-${Math.random()}`, 
                  text: userText, 
                  speaker: "user",
                  isComplete: false
                }
              ];
            });
          }

          // Handle user transcription complete
          if (msg.type === "user_transcription_complete") {
            setTurns((prev) => {
              const last = prev[prev.length - 1];
              if (last?.speaker === "user") {
                const updated = [...prev];
                updated[updated.length - 1] = { 
                  ...last, 
                  isComplete: true 
                };
                return updated;
              }
              return prev;
            });
          }
        } else {
          setAgentSpeaking(true);
          playerRef.current?.playRawChunk(event.data);
        }
      };

      // Audio setup
      let stream = streamRef.current;
      let context: AudioContext;
      let analyser: AnalyserNode;

      if (!audioRef.current || !stream) {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: { 
            echoCancellation: true, 
            noiseSuppression: true,
            autoGainControl: true
          },
        });
        streamRef.current = stream;
        const init = initAudioContext(stream);
        context = init.context;
        analyser = init.analyser;
        await context.audioWorklet.addModule("/worklets/recorder-processor.js");
      } else {
        ({ context, analyser } = audioRef.current);
        await context.resume();
      }

      audioRef.current = { context, analyser };
      playerRef.current = new AudioStreamPlayer(context);
      bufferRef.current = new Uint8Array(analyser.fftSize);

      const worklet = new AudioWorkletNode(context, "recorder-processor");
      workletRef.current = worklet;
      const source = context.createMediaStreamSource(stream);
      source.connect(worklet);

      worklet.port.onmessage = (e) => {
        const pcm = downsampleAndConvert(e.data, context.sampleRate);
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(pcm);
        }
      };

      setIsActive(true);
      addLog("🎙️ Microphone active");
      updateLoop();
    } catch (err) {
      addLog("❌ Error starting mic");
      console.error(err);
    }
  };

  const stopMic = () => {
    addLog("🔴 Session closed");
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    playerRef.current?.stop();
    playerRef.current = null;
    workletRef.current?.disconnect();
    workletRef.current = null;
    wsRef.current?.close();
    wsRef.current = null;
    setIsActive(false);
    setVolume(0);
    setIsSpeaking(false);
    setAgentSpeaking(false);
  };

  return (
    <div className="flex h-screen w-full bg-black text-white font-mono overflow-hidden">
      {/* --- Left Sidebar --- */}
      <aside className="w-72 border-r border-zinc-900 flex flex-col p-6 bg-[#050505] shrink-0">
        <h2 className="text-xs uppercase tracking-widest text-zinc-500 mb-4">Pipeline Logs</h2>
        <div className="space-y-3 text-[11px] mb-6">
          <div className="flex justify-between pb-2 border-b border-zinc-900">
            <span className="text-zinc-500">Status</span>
            <span className={isActive ? "text-green-500" : "text-zinc-700"}>
              {isActive ? "● Active" : "○ Offline"}
            </span>
          </div>
          <div className="flex justify-between pb-2 border-b border-zinc-900">
            <span className="text-zinc-500">Agent</span>
            <span className={agentSpeaking ? "text-blue-400" : "text-zinc-700"}>
              {agentSpeaking ? "● Speaking" : "○ Idle"}
            </span>
          </div>
          <div className="flex justify-between pb-2 border-b border-zinc-900">
            <span className="text-zinc-500">User</span>
            <span className={isSpeaking ? "text-purple-400" : "text-zinc-700"}>
              {isSpeaking ? "● Speaking" : "○ Quiet"}
            </span>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto space-y-2 pr-2 scrollbar-hide">
          {logs.map((log, i) => (
            <div 
              key={i} 
              className="text-[10px] text-zinc-500 border-l-2 border-zinc-800 pl-3 py-1 hover:border-zinc-600 transition-colors"
            >
              {log}
            </div>
          ))}
        </div>
      </aside>

      {/* --- Main Chat Area --- */}
      <main className="flex-1 flex flex-col min-w-0 bg-black relative">
        <div 
          ref={scrollRef}
          className="flex-1 overflow-y-auto p-8 space-y-6 scroll-smooth scrollbar-hide"
        >
          {turns.length === 0 ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center space-y-3">
                <h3 className="text-xl text-zinc-400">Ready to start</h3>
                <p className="text-sm text-zinc-600">Click the microphone to begin</p>
              </div>
            </div>
          ) : (
            turns.map((turn) => (
              <div
                key={turn.id}
                className={`flex w-full ${turn.speaker === "ai" ? "justify-start" : "justify-end"}`}
              >
                <div className="flex flex-col gap-1 max-w-[75%]">
                  {/* Speaker Label */}
                  <div className={`text-[10px] uppercase tracking-wider px-2 ${
                    turn.speaker === "ai" ? "text-blue-400" : "text-white"
                  }`}>
                    {turn.speaker === "ai" ? "Assistant" : "You"}
                  </div>
                  
                  {/* Message Bubble */}
                  <div
                    className={`p-4 rounded-2xl text-sm leading-relaxed shadow-lg transition-all ${
                      turn.speaker === "ai"
                        ? "bg-zinc-900 text-zinc-200 rounded-tl-none"
                        : "bg-white text-black rounded-tr-none"
                    } ${!turn.isComplete ? "opacity-70 animate-pulse" : ""}`}
                  >
                    {turn.text || (
                      <span className="text-zinc-500 italic">
                        {turn.speaker === "ai" ? "Thinking..." : "Listening..."}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))
          )}
          <div className="h-4 w-full" />
        </div>

        {/* Control Panel */}
        <div className="p-8 border-t border-zinc-900 bg-[#050505] shrink-0">
          <div className="flex flex-col items-center gap-6">
            {/* Mic Button */}
            <button
              onClick={isActive ? stopMic : startMic}
              className={`w-20 h-20 rounded-full flex items-center justify-center transition-all shadow-2xl hover:scale-105 ${
                isActive 
                  ? "bg-gradient-to-br from-red-500 to-red-600 scale-110" 
                  : "bg-gradient-to-br from-white to-zinc-200 hover:from-zinc-100"
              }`}
            >
              {isActive ? (
                <MicOff className="text-white" size={28} />
              ) : (
                <Mic className="text-black" size={28} />
              )}
            </button>

            {/* Volume Indicator */}
            <div className="w-full max-w-md flex items-center gap-4">
              <div className="flex-1 h-3 bg-zinc-900 rounded-full overflow-hidden shadow-inner">
                <div
                  className={`h-full transition-all duration-100 rounded-full ${
                    isSpeaking 
                      ? 'bg-gradient-to-r from-purple-500 to-blue-500 shadow-lg shadow-purple-500/50' 
                      : 'bg-zinc-700'
                  }`}
                  style={{ width: `${Math.min(volume, 100)}%` }}
                />
              </div>
              <span className="text-xs text-zinc-500 font-bold min-w-[45px] text-right tabular-nums">
                {isActive ? `${Math.round(volume)}%` : "0%"}
              </span>
            </div>

            {/* Status Text */}
            <div className="text-xs text-zinc-600">
              {!isActive && "Click to start"}
              {isActive && !isSpeaking && !agentSpeaking && "Listening..."}
              {isActive && isSpeaking && "You're speaking"}
              {isActive && agentSpeaking && "Assistant is responding"}
            </div>
          </div>
        </div>
      </main>

      {/* --- Right Sidebar (Latency) --- */}
      <aside className="w-80 border-l border-zinc-900 bg-[#050505] p-6 flex flex-col shrink-0">
        <h2 className="text-xs uppercase text-zinc-500 mb-6 tracking-widest">Latency Breakdown</h2>
        {currentMetrics ? (
          <div className="space-y-3 mb-6">
            <MetricRow label="VAD" value={currentMetrics.vad} />
            <MetricRow label="STT" value={currentMetrics.stt} />
            <MetricRow label="LLM" value={currentMetrics.llm} />
            <MetricRow label="TTS" value={currentMetrics.tts} />
            <div className="pt-3 mt-3 border-t border-zinc-800">
              <MetricRow label="Total E2E" value={currentMetrics.e2e} highlight />
            </div>
          </div>
        ) : (
          <div className="text-sm text-zinc-600 mb-6 italic p-4 bg-zinc-900/20 rounded border border-zinc-800">
            Waiting for voice input...
          </div>
        )}
        <h3 className="text-[10px] uppercase text-zinc-600 mb-3 tracking-wider">Recent Metrics</h3>
        <div className="flex-1 overflow-y-auto space-y-2 pr-2 scrollbar-hide">
          {latencyLogs.map((log, i) => (
            <div 
              key={i} 
              className="text-[9px] text-zinc-500 bg-zinc-900/30 p-2 rounded border-l-2 border-zinc-800 font-mono"
            >
              {log}
            </div>
          ))}
        </div>
      </aside>
    </div>
  );
}

function MetricRow({ 
  label, 
  value, 
  highlight 
}: { 
  label: string; 
  value: number; 
  highlight?: boolean 
}) {
  // Color coding based on latency
  const getColor = () => {
    if (highlight) return value < 2000 ? "text-green-400" : "text-yellow-400";
    if (value < 100) return "text-green-400";
    if (value < 500) return "text-yellow-400";
    return "text-red-400";
  };

  return (
    <div 
      className={`flex justify-between items-center p-3 rounded transition-all ${
        highlight 
          ? 'bg-gradient-to-r from-green-500/10 to-blue-500/10 border border-green-500/20' 
          : 'bg-zinc-900/30 hover:bg-zinc-900/50'
      }`}
    >
      <span className="text-[10px] text-zinc-500 uppercase tracking-wide">{label}</span>
      <span className={`text-sm font-mono font-bold ${getColor()}`}>
        {value}ms
      </span>
    </div>
  );
}