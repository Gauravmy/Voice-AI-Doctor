/**
 * AudioWorklet that turns microphone audio into what the backend expects:
 * 16 kHz, mono, 16-bit little-endian PCM, in 20 ms chunks (320 samples).
 *
 * The AudioContext runs at the device rate (usually 48 kHz), so we downsample
 * here by averaging the input samples that fall into each output sample.
 */
class MicProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.targetRate = 16000;
    this.ratio = sampleRate / this.targetRate; // `sampleRate` is a worklet global
    this.frameSize = 320; // 20 ms @ 16 kHz
    this.buffer = new Int16Array(this.frameSize);
    this.offset = 0;
    this.acc = 0;
    this.accCount = 0;
    this.pos = 0;
    this.levelSum = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;

    for (let i = 0; i < channel.length; i++) {
      this.acc += channel[i];
      this.accCount++;
      this.pos += 1;
      if (this.pos >= this.ratio) {
        this.pos -= this.ratio;
        const sample = Math.max(-1, Math.min(1, this.acc / this.accCount));
        this.acc = 0;
        this.accCount = 0;
        this.levelSum += sample * sample;
        this.buffer[this.offset++] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
        if (this.offset === this.frameSize) {
          const level = Math.sqrt(this.levelSum / this.frameSize);
          this.port.postMessage({ pcm: this.buffer.buffer, level }, [this.buffer.buffer]);
          this.buffer = new Int16Array(this.frameSize);
          this.offset = 0;
          this.levelSum = 0;
        }
      }
    }
    return true;
  }
}

registerProcessor("mic-processor", MicProcessor);
