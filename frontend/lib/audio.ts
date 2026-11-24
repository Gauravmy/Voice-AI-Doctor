/**
 * Browser audio I/O for a call.
 *
 *   MicCapture  - getUserMedia -> AudioWorklet -> 16 kHz PCM16 chunks (sent to backend)
 *   PcmPlayer   - PCM16 chunks from backend (24 kHz) -> gapless scheduled playback,
 *                 with flush() for barge-in interruptions.
 */

export const OUTPUT_SAMPLE_RATE = 24000;

export class MicCapture {
  private stream?: MediaStream;
  private source?: MediaStreamAudioSourceNode;
  private node?: AudioWorkletNode;
  muted = false;

  constructor(
    private ctx: AudioContext,
    private onChunk: (pcm: ArrayBuffer) => void,
    private onLevel: (level: number) => void,
  ) {}

  async start(): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    await this.ctx.audioWorklet.addModule("/worklets/mic-processor.js");
    this.source = this.ctx.createMediaStreamSource(this.stream);
    this.node = new AudioWorkletNode(this.ctx, "mic-processor");
    this.node.port.onmessage = (e: MessageEvent<{ pcm: ArrayBuffer; level: number }>) => {
      if (this.muted) {
        // Keep the stream flowing with silence so server-side VAD timing stays sane.
        this.onChunk(new ArrayBuffer(e.data.pcm.byteLength));
        this.onLevel(0);
        return;
      }
      this.onChunk(e.data.pcm);
      this.onLevel(e.data.level);
    };
    this.source.connect(this.node);
    // The worklet must be pulled by the graph; route it to a muted gain node.
    const sink = this.ctx.createGain();
    sink.gain.value = 0;
    this.node.connect(sink).connect(this.ctx.destination);
  }

  stop(): void {
    this.node?.port.close();
    this.node?.disconnect();
    this.source?.disconnect();
    this.stream?.getTracks().forEach((t) => t.stop());
  }
}

export class PcmPlayer {
  private nextStart = 0;
  private sources = new Set<AudioBufferSourceNode>();
  readonly analyser: AnalyserNode;

  constructor(private ctx: AudioContext) {
    this.analyser = ctx.createAnalyser();
    this.analyser.fftSize = 256;
    this.analyser.connect(ctx.destination);
  }

  play(pcm16: ArrayBuffer): void {
    const samples = new Int16Array(pcm16);
    if (samples.length === 0) return;
    const buffer = this.ctx.createBuffer(1, samples.length, OUTPUT_SAMPLE_RATE);
    const channel = buffer.getChannelData(0);
    for (let i = 0; i < samples.length; i++) channel[i] = samples[i] / 0x8000;

    const src = this.ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(this.analyser);
    const startAt = Math.max(this.ctx.currentTime + 0.02, this.nextStart);
    src.start(startAt);
    this.nextStart = startAt + buffer.duration;
    this.sources.add(src);
    src.onended = () => this.sources.delete(src);
  }

  /** Drop everything queued (the caller interrupted the agent). */
  flush(): void {
    this.sources.forEach((s) => {
      try {
        s.stop();
      } catch {
        /* already stopped */
      }
    });
    this.sources.clear();
    this.nextStart = 0;
  }

  level(): number {
    const data = new Uint8Array(this.analyser.frequencyBinCount);
    this.analyser.getByteTimeDomainData(data);
    let sum = 0;
    for (const v of data) sum += ((v - 128) / 128) ** 2;
    return Math.sqrt(sum / data.length);
  }
}
