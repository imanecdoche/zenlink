// Media player: H.264 access units (AVCC) through WebCodecs onto a
// low-latency canvas, and 48 kHz stereo PCM through WebAudio.
"use strict";

const MSG_VIDEO = 2;
const MSG_AUDIO = 3;

class CastPlayer {
  constructor(canvas, onStats) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d", { alpha: false, desynchronized: true });
    this.onStats = onStats;
    this.decoder = null;
    this.config = null;
    this.waitingForKey = true;
    this.pending = new Map(); // decoder timestamp -> host receive time (ms)
    this.ts = 0;
    this.audio = null;
    this.gain = null;
    this.nextAudio = 0;
    this.volume = 1;
    this.muted = false;
    this.window = { frames: 0, latency: 0, samples: 0, start: performance.now(), audioPackets: 0 };
  }

  configure(cfg) {
    const description = Uint8Array.from(atob(cfg.description), (c) => c.charCodeAt(0));
    this.config = {
      codec: cfg.codec,
      description,
      optimizeForLatency: true,
      hardwareAcceleration: "prefer-hardware",
    };
    this.size = { width: cfg.width, height: cfg.height };
    this._resetDecoder();
  }

  _resetDecoder() {
    if (this.decoder) {
      try { this.decoder.close(); } catch (_) {}
    }
    this.pending.clear();
    this.waitingForKey = true;
    if (!this.config) return;
    this.decoder = new VideoDecoder({
      output: (frame) => this._paint(frame),
      error: () => {
        // Corrupt or out-of-order data: rebuild and resume at the next keyframe.
        this.decoder = null;
        setTimeout(() => this._resetDecoder(), 0);
      },
    });
    this.decoder.configure(this.config);
  }

  handle(buffer) {
    const view = new DataView(buffer);
    const type = view.getUint8(0);
    const received = view.getFloat64(10, true);
    const payload = new Uint8Array(buffer, 18);
    if (type === MSG_VIDEO) this._video(view.getUint8(1) === 1, payload, received);
    else if (type === MSG_AUDIO) this._audio(payload);
  }

  _video(isKey, data, received) {
    if (!this.decoder || this.decoder.state !== "configured") return;
    if (this.waitingForKey) {
      if (!isKey) return;
      this.waitingForKey = false;
    }
    // Never let frames pile up inside the decoder: drop to the next keyframe.
    if (this.decoder.decodeQueueSize > 3 && !isKey) {
      this.waitingForKey = true;
      return;
    }
    this.ts += 16667;
    this.pending.set(this.ts, received);
    this.decoder.decode(new EncodedVideoChunk({ type: isKey ? "key" : "delta", timestamp: this.ts, data }));
  }

  _paint(frame) {
    const w = frame.displayWidth;
    const h = frame.displayHeight;
    if (this.canvas.width !== w || this.canvas.height !== h) {
      this.canvas.width = w;
      this.canvas.height = h;
      this.size = { width: w, height: h };
    }
    this.ctx.drawImage(frame, 0, 0, w, h);
    const received = this.pending.get(frame.timestamp);
    this.pending.delete(frame.timestamp);
    frame.close();
    if (this.pending.size > 120) this.pending.clear();

    const win = this.window;
    win.frames += 1;
    if (received) {
      win.latency += Date.now() - received;
      win.samples += 1;
    }
    const now = performance.now();
    if (now - win.start >= 1000) {
      this.onStats({
        width: this.size.width,
        height: this.size.height,
        fps: Math.round((win.frames * 1000) / (now - win.start)),
        latency: win.samples ? Math.round(win.latency / win.samples) : null,
        audio: win.audioPackets > 0,
      });
      this.window = { frames: 0, latency: 0, samples: 0, start: now, audioPackets: 0 };
    }
  }

  _ensureAudio() {
    if (this.audio) return;
    this.audio = new AudioContext({ sampleRate: 48000, latencyHint: "interactive" });
    this.gain = this.audio.createGain();
    this.gain.gain.value = this.muted ? 0 : this.volume;
    this.gain.connect(this.audio.destination);
    this.nextAudio = 0;
  }

  _audio(bytes) {
    this.window.audioPackets += 1;
    this._ensureAudio();
    const ctx = this.audio;
    if (ctx.state === "suspended") ctx.resume().catch(() => {});
    const samples = new Int16Array(bytes.buffer, bytes.byteOffset, bytes.byteLength >> 1);
    const frames = samples.length >> 1;
    if (!frames) return;
    const buf = ctx.createBuffer(2, frames, 48000);
    const left = buf.getChannelData(0);
    const right = buf.getChannelData(1);
    for (let i = 0, j = 0; i < frames; i++, j += 2) {
      left[i] = samples[j] / 32768;
      right[i] = samples[j + 1] / 32768;
    }
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(this.gain);
    // Keep a small cushion; if we fall behind or drift ahead, snap back.
    const now = ctx.currentTime;
    if (this.nextAudio < now + 0.01 || this.nextAudio > now + 0.15) this.nextAudio = now + 0.04;
    src.start(this.nextAudio);
    this.nextAudio += buf.duration;
  }

  setVolume(value) {
    this.volume = value;
    if (this.gain && !this.muted) this.gain.gain.setTargetAtTime(value, this.audio.currentTime, 0.02);
  }

  setMuted(muted) {
    this.muted = muted;
    if (this.gain) this.gain.gain.setTargetAtTime(muted ? 0 : this.volume, this.audio.currentTime, 0.02);
  }

  reset() {
    if (this.decoder) {
      try { this.decoder.close(); } catch (_) {}
    }
    this.decoder = null;
    this.config = null;
    this.pending.clear();
    if (this.audio) {
      this.audio.close().catch(() => {});
      this.audio = null;
    }
  }
}

window.CastPlayer = CastPlayer;
