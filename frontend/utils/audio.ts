/**
 * utils/audio.ts
 */

const TARGET_SAMPLE_RATE = 16000;

export function initAudioContext(stream: MediaStream) {
  const AudioContextAPI = (window as any).AudioContext || (window as any).webkitAudioContext;
  const context = new AudioContextAPI({ sampleRate: TARGET_SAMPLE_RATE });

  const analyser = context.createAnalyser();
  analyser.fftSize = 2048;

  return { context, analyser };
}

// Added this back to resolve your import error
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

export function downsampleAndConvert(
  input: Float32Array,
  originalSampleRate: number
): ArrayBuffer {
  const ratio = originalSampleRate / TARGET_SAMPLE_RATE;
  const newLength = Math.round(input.length / ratio);
  const resultBuffer = new ArrayBuffer(newLength * 2);
  const view = new DataView(resultBuffer);

  for (let i = 0; i < newLength; i++) {
    const index = Math.round(i * ratio);
    const sample = Math.max(-1, Math.min(1, input[index]));
    view.setInt16(i * 2, sample < 0 ? sample * 0x8000 : sample * 0x7FFF, true);
  }

  return resultBuffer;
}

export class AudioStreamPlayer {
  private context: AudioContext;
  private nextStartTime: number = 0;

  constructor(context: AudioContext) {
    this.context = context;
  }

  async playRawChunk(arrayBuffer: ArrayBuffer) {
    if (this.context.state === 'suspended') await this.context.resume();

    const int16 = new Int16Array(arrayBuffer);
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) {
      float32[i] = int16[i] / 32768.0;
    }

    const audioBuffer = this.context.createBuffer(1, float32.length, TARGET_SAMPLE_RATE);
    audioBuffer.getChannelData(0).set(float32);

    const source = this.context.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(this.context.destination);

    const currentTime = this.context.currentTime;
    if (this.nextStartTime < currentTime) {
      this.nextStartTime = currentTime + 0.05;
    }

    source.start(this.nextStartTime);
    this.nextStartTime += audioBuffer.duration;
  }
}