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

  type TranscriptTurn = {
    id: number;
    text: string;
    speaker: "user" | "ai";
    stt_latency?: number;
    llm_latency?: number;
    total_latency?: number;
  };

  const [turns, setTurns] = useState<TranscriptTurn[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const audioRef = useRef<{ context: AudioContext; analyser: AnalyserNode } | null>(null);
  const playerRef = useRef<AudioStreamPlayer | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const rafRef = useRef<number | null>(null);
  const workletRef = useRef<AudioWorkletNode | null>(null);

  const bufferRef = useRef<Uint8Array | null>(null);
  const smoothRef = useRef(0);
  const maxRmsRef = useRef(0.02);

  const SPEAK_THRESHOLD = 15;
  const NOISE_FLOOR = 0.01;
  const DECAY = 0.96;

  /* ---------- Loudness Loop ---------- */
  const updateLoop = () => {
    if (!audioRef.current || !bufferRef.current) return;
    const { analyser } = audioRef.current;
    const buffer = bufferRef.current;

    readTimeDomain(analyser, buffer);
    const rms = calcRMS(buffer);
    const cleanRms = Math.max(0, rms - NOISE_FLOOR);

    if (cleanRms > maxRmsRef.current) maxRmsRef.current = cleanRms;
    else maxRmsRef.current *= DECAY;

    const currentMax = Math.max(maxRmsRef.current, 0.02);
    const percent = Math.min(cleanRms / currentMax, 1) * 100;

    smoothRef.current = smoothRef.current * 0.7 + percent * 0.3;
    setVolume(smoothRef.current);
    setIsSpeaking(smoothRef.current > SPEAK_THRESHOLD); 

    rafRef.current = requestAnimationFrame(updateLoop);
  };

  /* ---------- Start Mic ---------- */
  const startMic = async () => {
    try {
      const ws = new WebSocket("ws://localhost:8000/ws/audio");
      ws.binaryType = "arraybuffer"; // Industry standard for raw audio
      wsRef.current = ws;

      ws.onmessage = async (event) => {
        if (typeof event.data === "string") {
          try {
            const msg = JSON.parse(event.data);
            
            if (msg.type === "partial_agent_response") {
              setTurns((prev) => {
                const last = prev[prev.length - 1];
                if (last?.speaker === "ai") {
                  const updated = [...prev];
                  updated[updated.length - 1] = {
                    ...last,
                    text: msg.ai_partial,
                    stt_latency: msg.stt_latency,
                    llm_latency: msg.llm_latency,
                    total_latency: msg.total_latency
                  };
                  return updated;
                }
                return [...prev, { 
                  id: Date.now(), 
                  text: msg.ai_partial, 
                  speaker: "ai", 
                  stt_latency: msg.stt_latency,
                  llm_latency: msg.llm_latency,
                  total_latency: msg.total_latency
                }];
              });
            }
          } catch (err) { console.error("JSON Parse Error", err); }
        } else {
          // Play binary PCM chunk using our jitter-free player
          playerRef.current?.playRawChunk(event.data);
        }
      };

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
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
      source.connect(analyser);
      source.connect(worklet);
      
      worklet.port.onmessage = (e) => {
        // Use precision downsampling to 16kHz
        const pcm = downsampleAndConvert(e.data, context.sampleRate);
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(pcm);
        }
      };

      setIsActive(true);
      updateLoop();
    } catch (err) { console.error("Mic error:", err); }
  };

  /* ---------- Stop Mic ---------- */
  const stopMic = () => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    workletRef.current?.disconnect();
    wsRef.current?.close();
    streamRef.current?.getTracks().forEach(t => t.stop());
    
    // Check state before closing to avoid InvalidStateError
    if (audioRef.current?.context.state !== "closed") {
      audioRef.current?.context.close();
    }
    
    setIsActive(false);
    setVolume(0);
    setIsSpeaking(false);
  };

  useEffect(() => () => stopMic(), []);

  return (
    <div className="flex flex-col items-center justify-center p-8 space-y-8 bg-black border border-zinc-800 rounded-xl w-full max-w-sm mx-auto shadow-2xl">
      <button
        onClick={isActive ? stopMic : startMic}
        className={`p-6 rounded-full border transition-all duration-300 ${
          isActive ? "bg-white text-black border-white shadow-[0_0_15px_rgba(255,255,255,0.2)]" : "bg-black text-white border-zinc-500"
        }`}
      >
        {isActive ? <MicOff size={28} /> : <Mic size={28} />}
      </button>

      <div className="w-full space-y-4">
        <div className="flex justify-between text-[10px] font-mono uppercase">
          <span className="text-zinc-500">Signal</span>
          <span className={isSpeaking ? "text-white font-bold" : "text-zinc-500"}>
            {isSpeaking ? "Activity" : "Silence"}
          </span>
        </div>
        <div className="h-1 bg-zinc-900 overflow-hidden rounded-full">
          <div className="h-full bg-white transition-all duration-75" style={{ width: `${volume}%` }} />
        </div>
      </div>

      <div className="w-full max-h-64 overflow-y-auto border-t border-zinc-800 pt-4 flex flex-col gap-3 scroll-smooth scrollbar-hide">
        {turns.length === 0 && (
          <p className="text-[10px] text-zinc-600 text-center uppercase py-4">Waiting for input...</p>
        )}
        {turns.map((turn) => (
          <div
            key={turn.id}
            className={`max-w-[85%] p-3 rounded-2xl font-mono text-xs ${
              turn.speaker === "ai"
                ? "bg-zinc-900 text-zinc-200 self-start rounded-tl-none border border-zinc-800"
                : "bg-blue-600 text-white self-end rounded-tr-none"
            }`}
          >
            <div className="flex justify-between items-center mb-1 gap-2">
              <span className="text-[8px] uppercase tracking-widest opacity-50 font-bold">
                {turn.speaker === "ai" ? "Assistant" : "You"}
              </span>
              {turn.speaker === "ai" && turn.total_latency && (
                <span className="text-[7px] text-zinc-500">
                  {turn.total_latency.toFixed(2)}s
                </span>
              )}
            </div>
            {turn.text}
            {turn.speaker === "ai" && turn.stt_latency && (
              <div className="mt-2 pt-2 border-t border-zinc-800 flex gap-2 text-[7px] text-zinc-500 uppercase">
                <span>STT: {turn.stt_latency.toFixed(2)}s</span>
                <span>LLM: {turn.llm_latency?.toFixed(2)}s</span>
              </div>
            )}
          </div>
        ))}
      </div>

      <p className="text-[10px] font-mono text-zinc-600 uppercase tracking-widest">
        {isActive ? "🔴 Live Pipeline Active" : "Input Device Ready"}
      </p>
    </div>
  );
}