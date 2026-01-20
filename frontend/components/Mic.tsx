"use client";
import React, { useState, useRef, useEffect } from "react";
import { Mic, MicOff } from "lucide-react";
import { initAudioContext, readTimeDomain, calcRMS } from "@/utils/audio";

export default function VoiceMic() {
  const [isActive, setIsActive] = useState(false);
  const [volume, setVolume] = useState(0);
  const [isSpeaking, setIsSpeaking] = useState(false);

  const audioRef = useRef<{ context: AudioContext; analyser: AnalyserNode } | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const rafRef = useRef<number | null>(null);
  const smoothRef = useRef(0);
  const maxRmsRef = useRef(0.02);
  const bufferRef = useRef<Uint8Array | null>(null);

  const workletRef = useRef<AudioWorkletNode | null>(null);
  const accumulatorRef = useRef<number[]>([]);
  const CHUNK_SIZE = 1024;

  const SPEAK_THRESHOLD = 15;
  const NOISE_FLOOR = 0.01;
  const DECAY = 0.96;

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

    if (cleanRms > maxRmsRef.current) {
      maxRmsRef.current = cleanRms;
    } else {
      maxRmsRef.current *= DECAY;
    }

    const currentMax = Math.max(maxRmsRef.current, 0.02);
    const normalized = Math.min(Math.max(cleanRms / currentMax, 0), 1);
    const percent = normalized * 100;

    smoothRef.current = smoothRef.current * 0.7 + percent * 0.3;

    setVolume(smoothRef.current);
    setIsSpeaking(smoothRef.current > SPEAK_THRESHOLD);

    rafRef.current = requestAnimationFrame(updateLoop);
  };

  function onWorkletMessage(event: MessageEvent) {
    const samples = event.data as Float32Array;
    handleSamples(samples);
  }

  function handleSamples(samples: Float32Array) {
    accumulatorRef.current.push(...samples);

    while (accumulatorRef.current.length >= CHUNK_SIZE) {
      const chunk = accumulatorRef.current.slice(0, CHUNK_SIZE);
      accumulatorRef.current = accumulatorRef.current.slice(CHUNK_SIZE);
      console.log("Chunk created:", chunk.length);
    }
  }

  const startMic = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
        },
      });

      streamRef.current = stream;

      const { context, analyser } = initAudioContext(stream);
      audioRef.current = { context, analyser };
      bufferRef.current = new Uint8Array(analyser.fftSize);

      await context.audioWorklet.addModule("/worklets/recorder-processor.js");

      const source = context.createMediaStreamSource(stream);
      const worklet = new AudioWorkletNode(context, "recorder-processor");
      workletRef.current = worklet;

      source.connect(worklet);
      worklet.connect(context.destination);
      worklet.port.onmessage = onWorkletMessage;

      setIsActive(true);
      updateLoop();
    } catch (err) {
      console.error("Mic error:", err);
    }
  };

  const stopMic = () => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);

    workletRef.current?.disconnect();
    workletRef.current = null;
    accumulatorRef.current = [];

    streamRef.current?.getTracks().forEach((t) => t.stop());
    if (audioRef.current?.context.state !== "closed") {
      audioRef.current?.context.close();
    }

    setIsActive(false);
    setVolume(0);
    setIsSpeaking(false);
  };

  useEffect(() => {
    return () => stopMic();
  }, []);

  return (
    <div className="flex flex-col items-center justify-center p-8 space-y-8 bg-black border border-zinc-800 rounded-xl w-full max-w-sm mx-auto shadow-2xl">
      <button
        onClick={isActive ? stopMic : startMic}
        className={`p-6 rounded-full transition-colors border ${
          isActive
            ? "bg-white text-black border-white"
            : "bg-black text-white border-zinc-500 hover:border-zinc-400"
        }`}
      >
        {isActive ? <MicOff size={28} /> : <Mic size={28} />}
      </button>

      <div className="w-full space-y-4">
        <div className="flex justify-between items-center text-[10px] font-mono uppercase">
          <span className="text-zinc-500 tracking-widest">Signal</span>
          <span className={isSpeaking ? "text-white" : "text-zinc-500"}>
            {isSpeaking ? "Activity" : "Silence"}
          </span>
        </div>

        <div className="h-1 w-full bg-zinc-900 overflow-hidden">
          <div
            className="h-full bg-white transition-all duration-75"
            style={{ width: `${volume}%` }}
          />
        </div>
      </div>

      <p className="text-[10px] font-mono text-zinc-600 uppercase tracking-widest">
        {isActive ? "Audio capturer" : "Input Device Ready"}
      </p>
    </div>
  );
}
