"use client";

import React, { useState, useRef, useEffect } from "react";
import { Mic, MicOff } from "lucide-react";
import { 
  initAudioContext, 
  readTimeDomain, 
  calcRMS, 
  downsampleAndConvert, 
  AudioStreamPlayer 
} from "@/utils/audio";

export default function VoiceMic() {
  const [isActive, setIsActive] = useState(false);
  const [volume, setVolume] = useState(0);
  const [isSpeaking, setIsSpeaking] = useState(false);

  type PipelineMetrics = {
    vad: number;
    stt: number;
    llm: number;
    tts: number;
    search: string;
    e2e: number;
  };

  type TranscriptTurn = {
    id: number;
    text: string;
    speaker: "user" | "ai";
    metrics?: PipelineMetrics;
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

  const bufferRef = useRef<Uint8Array | null>(null);
  const smoothRef = useRef(0);
  const maxRmsRef = useRef(0.02);

  const addLog = (msg: string) => {
    setLogs(prev => [msg, ...prev].slice(0, 15));
  };

  const addLatencyLog = (msg: string) => {
    setLatencyLogs(prev => [msg, ...prev].slice(0, 20));
  };

  /* ---------- Loudness Loop ---------- */
  const updateLoop = () => {
    if (!audioRef.current || !bufferRef.current) return;
    const { analyser } = audioRef.current;
    const buffer = bufferRef.current;

    readTimeDomain(analyser, buffer);
    const rms = calcRMS(buffer);
    const cleanRms = Math.max(0, rms - NOISE_FLOOR);

    if (cleanRms > maxRmsRef.current) maxRmsRef.current = cleanRms;
    else maxRmsRef.current *= 0.96;

    const currentMax = Math.max(maxRmsRef.current, 0.02);
    const percent = Math.min(cleanRms / currentMax, 1) * 100;

    smoothRef.current = smoothRef.current * 0.7 + percent * 0.3;
    setVolume(smoothRef.current);
    setIsSpeaking(smoothRef.current > 15); 

    rafRef.current = requestAnimationFrame(updateLoop);
  };

  /* ---------- Start Mic ---------- */
  const startMic = async () => {
    try {
      addLog("Initializing connection...");
      const wsUrl = "ws://localhost:8000/ws/audio";
      const ws = new WebSocket(wsUrl);
      ws.binaryType = "arraybuffer"; 
      wsRef.current = ws;

      ws.onmessage = async (event) => {
        if (typeof event.data === "string") {
          const msg = JSON.parse(event.data);

          if (msg.type === "interrupt") {
            addLog("⚡ Barge-in detected");
            playerRef.current?.stop(); 
            return; 
          }

          if (msg.type === "pipeline_metrics" || msg.metrics) {
            const m = msg.metrics;
            if (m && m.e2e) {
              setCurrentMetrics(m);
              addLog(`Pipeline Finish: ${m.e2e}ms`);
              addLatencyLog(`VAD: ${m.vad}ms | STT: ${m.stt}ms | LLM: ${m.llm}ms | TTS: ${m.tts}ms | E2E: ${m.e2e}ms`);
            }
          }

          if (msg.type === "partial_agent_response" || msg.ai_partial) {
            const text = msg.ai_partial || msg.text;
            setTurns((prev) => {
              const last = prev[0];
              if (last?.speaker === "ai") {
                const updated = [...prev];
                updated[0] = { ...last, text, metrics: msg.metrics };
                return updated;
              }
              return [{ id: Date.now(), text, speaker: "ai", metrics: msg.metrics }, ...prev];
            });
          }

          if (msg.type === "caption") {
            setTurns(prev => {
                const last = prev[0];
                if (last?.speaker === "user") {
                    const updated = [...prev];
                    updated[0] = { ...last, text: msg.text };
                    return updated;
                }
                return [{ id: Date.now(), text: msg.text, speaker: "user" }, ...prev];
            });
          }
        } else {
          playerRef.current?.playRawChunk(event.data);
        }
      };

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
      streamRef.current = stream;

      const { context, analyser } = initAudioContext(stream);
      audioRef.current = { context, analyser };
      playerRef.current = new AudioStreamPlayer(context);
      bufferRef.current = new Uint8Array(analyser.fftSize);

      await context.audioWorklet.addModule("/worklets/recorder-processor.js");
      const worklet = new AudioWorkletNode(context, "recorder-processor");
      workletRef.current = worklet;

      const source = context.createMediaStreamSource(stream);
      source.connect(worklet);
      
      worklet.port.onmessage = (e) => {
        const pcm = downsampleAndConvert(e.data, context.sampleRate);
        if (wsRef.current?.readyState === WebSocket.OPEN) wsRef.current.send(pcm);
      };

      setIsActive(true);
      addLog("Mic Live // STT Streaming");
      updateLoop();
    } catch (err) { addLog("Error starting mic"); }
  };

  const stopMic = () => {
    addLog("Session closed.");
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    wsRef.current?.close();
    streamRef.current?.getTracks().forEach(t => t.stop());
    setIsActive(false);
  };

  const NOISE_FLOOR = 0.01;

  return (
    <div className="flex h-screen w-full bg-black text-white font-mono overflow-hidden">
      
      {/* --- Left Sidebar (Pipeline Logs) --- */}
      <aside className="w-72 border-r border-zinc-900 flex flex-col p-6 bg-[#050505]">
        <div className="mb-6">
          <h2 className="text-xs uppercase tracking-widest text-zinc-500 mb-4">Pipeline Logs</h2>
          <div className="space-y-3 text-[11px]">
            <div className="flex justify-between pb-2 border-b border-zinc-900">
              <span className="text-zinc-500">Status</span>
              <span className={isActive ? "text-green-500" : "text-zinc-700"}>
                {isActive ? "● Active" : "○ Offline"}
              </span>
            </div>
            <div className="flex justify-between pb-2 border-b border-zinc-900">
              <span className="text-zinc-500">Messages</span>
              <span className="text-zinc-300">{turns.length}</span>
            </div>
          </div>
        </div>

        <div className="flex-1 flex flex-col min-h-0">
          <div className="flex-1 overflow-y-auto space-y-2 pr-2 scrollbar-hide">
            {logs.map((log, i) => (
              <div key={i} className="text-[10px] text-zinc-500 border-l border-zinc-800 pl-3 py-1">
                {log}
              </div>
            ))}
          </div>
        </div>
      </aside>

      {/* --- Main Chat Area --- */}
      <main className="flex-1 flex flex-col min-w-0 bg-black">
        {/* Chat Feed (reversed - latest at top) */}
        <div className="flex-1 overflow-y-auto p-8 space-y-6 flex flex-col-reverse scrollbar-hide">
          {turns.map((turn) => (
            <div key={turn.id} className={`flex ${turn.speaker === "ai" ? "justify-start" : "justify-end"}`}>
              <div className={`max-w-[70%] p-4 rounded-lg text-sm leading-relaxed ${
                turn.speaker === "ai" 
                  ? "bg-zinc-900 text-zinc-200" 
                  : "bg-white text-black"
              }`}>
                {turn.text}
              </div>
            </div>
          ))}
        </div>

        {/* --- Bottom controls --- */}
        <div className="p-8 border-t border-zinc-900 bg-[#050505]">
          <div className="flex flex-col items-center gap-6">
            <button 
              onClick={isActive ? stopMic : startMic}
              className={`w-20 h-20 rounded-full flex items-center justify-center transition-all ${
                isActive 
                  ? "bg-white hover:bg-gray-200" 
                  : "bg-white hover:bg-gray-200"
              }`}
            >
              {isActive ? (
                <MicOff className="text-black" size={28} />
              ) : (
                <Mic className="text-black" size={28} />
              )}
            </button>
            
            <div className="w-full max-w-md flex items-center gap-4">
              <div className="flex-1 h-2 bg-zinc-900 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-blue-500 transition-all duration-75" 
                  style={{width: `${volume}%`}} 
                />
              </div>
              <span className="text-xs text-zinc-500 min-w-[40px] text-right">
                {isActive ? `${Math.round(volume)}%` : ''}
              </span>
            </div>
          </div>
        </div>
      </main>

      {/* --- Right Sidebar (Latency Metrics) --- */}
      <aside className="w-80 border-l border-zinc-900 bg-[#050505] p-6 flex flex-col">
        <h2 className="text-xs uppercase text-zinc-500 mb-6 tracking-widest">Latency Breakdown</h2>
        
        {currentMetrics ? (
          <div className="space-y-3 mb-6">
            <MetricRow label="VAD" value={currentMetrics.vad} />
            <MetricRow label="STT" value={currentMetrics.stt} />
            <MetricRow label="LLM" value={currentMetrics.llm} />
            <MetricRow label="TTS" value={currentMetrics.tts} />
            <div className="pt-3 mt-3 border-t border-zinc-900">
              <MetricRow label="E2E" value={currentMetrics.e2e} highlight />
            </div>
            {currentMetrics.search && currentMetrics.search !== "NONE" && (
              <div className="text-[10px] text-blue-400 pt-2">
                Search: {currentMetrics.search}
              </div>
            )}
          </div>
        ) : (
          <div className="text-sm text-zinc-600 mb-6 italic">
            waiting for metrics...
          </div>
        )}

        <div className="flex-1 flex flex-col min-h-0 mt-4">
          <h3 className="text-[10px] uppercase text-zinc-600 mb-3 tracking-wider">
            History
          </h3>
          <div className="flex-1 overflow-y-auto space-y-2 pr-2 scrollbar-hide">
            {latencyLogs.length === 0 ? (
              <div className="text-[10px] text-zinc-700 italic">no logs yet</div>
            ) : (
              latencyLogs.map((log, i) => (
                <div key={i} className="text-[9px] text-zinc-500 bg-zinc-900/30 p-2 rounded border-l-2 border-zinc-800">
                  {log}
                </div>
              ))
            )}
          </div>
        </div>
      </aside>
    </div>
  );
}

function MetricRow({ label, value, highlight }: { label: string, value: number, highlight?: boolean }) {
  return (
    <div className="flex justify-between items-center bg-zinc-900/30 p-3 rounded">
      <span className="text-[10px] text-zinc-500 uppercase">{label}</span>
      <span className={`text-sm font-mono ${highlight ? 'text-green-400 font-bold' : 'text-zinc-300'}`}>
        {value}ms
      </span>
    </div>
  );
}