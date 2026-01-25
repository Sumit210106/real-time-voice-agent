"use client";
import React, { useState, useRef, useEffect } from "react";
import { Mic, MicOff } from "lucide-react";
import { initAudioContext, readTimeDomain, calcRMS } from "@/utils/audio";

export default function VoiceMic() {
  const [isActive, setIsActive] = useState(false);
  const [volume, setVolume] = useState(0);
  const [isSpeaking, setIsSpeaking] = useState(false);

  type TranscriptTurn = {
    id: number;
    text: string;
    speaker: "user";
    startedAt: number;
    endedAt: number;
  };

  const [turns, setTurns] = useState<TranscriptTurn[]>([]);
  const speechStartTimeRef = useRef<number | null>(null);
  const turnId = useRef(0);

  const wsRef = useRef<WebSocket | null>(null);
  const audioRef = useRef<{ context: AudioContext; analyser: AnalyserNode } | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const rafRef = useRef<number | null>(null);
  const workletRef = useRef<AudioWorkletNode | null>(null);

  const bufferRef = useRef<Uint8Array | null>(null);
  const smoothRef = useRef(0);
  const maxRmsRef = useRef(0.02);

  const accumulatorRef = useRef<number[]>([]);
  const CHUNK_SIZE = 1024;

  const SPEAK_THRESHOLD = 15;
  const NOISE_FLOOR = 0.01;
  const DECAY = 0.96;

  /* ---------- Loudness Loop ---------- */

  const updateLoop = () => {
    if (!audioRef.current || !bufferRef.current) return;

    if (audioRef.current.context.state === "suspended") {
      audioRef.current.context.resume();
    }

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
    const speakingNow = smoothRef.current > SPEAK_THRESHOLD;
    setVolume(smoothRef.current);
    setIsSpeaking(speakingNow); // Only controls the UI "Activity" text

    rafRef.current = requestAnimationFrame(updateLoop);
  };

  /* ---------- Worklet Samples ---------- */

  function onWorkletMessage(event: MessageEvent) {
    const samples = event.data as Float32Array;
    accumulatorRef.current.push(...samples);

    while (accumulatorRef.current.length >= CHUNK_SIZE) {
      const chunk = accumulatorRef.current.slice(0, CHUNK_SIZE);
      accumulatorRef.current = accumulatorRef.current.slice(CHUNK_SIZE);

      if (wsRef.current?.readyState === WebSocket.OPEN) {
        const float32 = new Float32Array(chunk);
        wsRef.current.send(float32.buffer);
      }

      console.log("Chunk sent:", chunk.length);
    }
  }

  /* ---------- Start Mic ---------- */

  const startMic = async () => {
    try {
      const ws = new WebSocket("ws://localhost:8000/ws/audio");
      wsRef.current = ws;
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);

          // 1. Backend tells us user started talking
          if (msg.type === "vad" && msg.event === "speech_start") {
            speechStartTimeRef.current = Date.now();
          }

          // 2. Backend sends final transcript
          if (msg.type === "transcript") {
            const now = Date.now();
            const startTime = speechStartTimeRef.current || now;
            
            setTurns(prev => [
              ...prev,
              {
                id: turnId.current++,
                text: msg.text,
                speaker: "user",
                startedAt: startTime,
                endedAt: now,
              }
            ]);
            
            // Reset for next utterance
            speechStartTimeRef.current = null;
          }
        } catch (err) {
          console.error("WS Message Error:", err);
        }
      };

      ws.onopen = () => console.log("Audio WS connected");
      ws.onclose = () => console.log("Audio WS closed");

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
      });

      streamRef.current = stream;

      // Force 16kHz for STT efficiency and lower network bandwidth
      const context = new AudioContext({ sampleRate: 16000 });
      await context.resume();

      const analyser = context.createAnalyser();
      analyser.fftSize = 2048;
      audioRef.current = { context, analyser };
      bufferRef.current = new Uint8Array(analyser.fftSize);

      await context.audioWorklet.addModule("/worklets/recorder-processor.js");

      const source = context.createMediaStreamSource(stream);
      const worklet = new AudioWorkletNode(context, "recorder-processor");
      workletRef.current = worklet;

      // Connect source to Analyser (UI) and Worklet (Backend)
      // DO NOT connect to context.destination to prevent speaker-to-mic feedback loop
      source.connect(analyser);
      source.connect(worklet);
      
      worklet.port.onmessage = onWorkletMessage;

      setIsActive(true);
      updateLoop();
    } catch (err) {
      console.error("Mic error:", err);
    }
  };

  /* ---------- Stop Mic ---------- */

  const stopMic = () => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);

    workletRef.current?.disconnect();
    workletRef.current = null;
    accumulatorRef.current = [];

    wsRef.current?.close();
    wsRef.current = null;

    streamRef.current?.getTracks().forEach(t => t.stop());
    audioRef.current?.context.close();

    setIsActive(false);
    setVolume(0);
    setIsSpeaking(false);
  };

  useEffect(() => () => stopMic(), []);

  /* ---------- UI ---------- */

  return (
    <div className="flex flex-col items-center justify-center p-8 space-y-8 bg-black border border-zinc-800 rounded-xl w-full max-w-sm mx-auto shadow-2xl">
      <button
        onClick={isActive ? stopMic : startMic}
        className={`p-6 rounded-full border transition-colors ${
          isActive ? "bg-white text-black border-white" : "bg-black text-white border-zinc-500"
        }`}
      >
        {isActive ? <MicOff size={28} /> : <Mic size={28} />}
      </button>

      <div className="w-full space-y-4">
        <div className="flex justify-between text-[10px] font-mono uppercase">
          <span className="text-zinc-500">Signal</span>
          <span className={isSpeaking ? "text-white" : "text-zinc-500"}>
            {isSpeaking ? "Activity" : "Silence"}
          </span>
        </div>

        <div className="h-1 bg-zinc-900 overflow-hidden">
          <div className="h-full bg-white transition-all duration-75" style={{ width: `${volume}%` }} />
        </div>
      </div>
      <div className="w-full max-h-48 overflow-y-auto border-t border-zinc-800 pt-4 space-y-3">
        {turns.map(turn => (
          <div key={turn.id} className="bg-zinc-900 rounded p-3">
            <div className="text-[10px] text-zinc-500 mb-1 font-mono uppercase">
              User · {((turn.endedAt - turn.startedAt) / 1000).toFixed(1)}s
            </div>
            <div className="text-sm text-zinc-200 font-mono">
              {turn.text}
            </div>
          </div>
        ))}
      </div>

      <p className="text-[10px] font-mono text-zinc-600 uppercase">
        {isActive ? "Streaming Audio → Backend" : "Input Device Ready"}
      </p>
    </div>
  );
}
