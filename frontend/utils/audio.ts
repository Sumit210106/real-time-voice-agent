
export function initAudioContext(stream: MediaStream) {
  const context = new (
    window.AudioContext || (window as any).webkitAudioContext
  )({ latencyHint: "interactive" });

  const source = context.createMediaStreamSource(stream);

  const gain = context.createGain();
  gain.gain.value = 1.0;

  const analyser = context.createAnalyser();
  analyser.fftSize = 1024; 
  source.connect(gain);
  gain.connect(analyser);

  return { context, analyser };
}
export function readTimeDomain(analyser: AnalyserNode, buffer: Uint8Array) {
  analyser.getByteTimeDomainData(buffer);
}
export function calcRMS(buffer: Uint8Array) {
  let sum = 0;
  for (let i = 0; i < buffer.length; i++) {
    const v = (buffer[i] - 128) / 128;
    sum += v * v;
  }
  return Math.sqrt(sum / (buffer.length || 1));
}

export function floatTo16BitPCM(input: Float32Array): ArrayBuffer {
  const buffer = new ArrayBuffer(input.length * 2);
  const view = new DataView(buffer);
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]));
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
  }
  return buffer;
}