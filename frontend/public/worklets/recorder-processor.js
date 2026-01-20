class RecorderProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel || channel.length === 0) return true;

    this.port.postMessage(channel);
    return true;
  }
}

registerProcessor("recorder-processor", RecorderProcessor);
