// sound.js — Web Audio API 音效引擎 + 全局静音
class SoundManager {
  constructor() {
    this._muted = localStorage.getItem('redten-mute') === '1';
    this._ctx = null;
  }

  get muted() { return this._muted; }

  toggle() {
    this._muted = !this._muted;
    localStorage.setItem('redten-mute', this._muted ? '1' : '0');
    if (this._muted && this._ctx) {
      this._ctx.close();
      this._ctx = null;
    }
    return this._muted;
  }

  _ac() {
    if (this._muted) return null;
    if (!this._ctx) this._ctx = new (window.AudioContext || window.webkitAudioContext)();
    if (this._ctx.state === 'suspended') this._ctx.resume();
    return this._ctx;
  }

  _tone(freq, type, dur, vol = 0.25, t0 = 0) {
    const c = this._ac();
    if (!c) return;
    const o = c.createOscillator(), g = c.createGain();
    o.connect(g); g.connect(c.destination);
    o.type = type; o.frequency.value = freq;
    const start = c.currentTime + t0;
    g.gain.setValueAtTime(vol, start);
    g.gain.exponentialRampToValueAtTime(0.001, start + dur);
    o.start(start); o.stop(start + dur + 0.02);
  }

  _noise(dur, vol = 0.12) {
    const c = this._ac();
    if (!c) return;
    const sr = c.sampleRate;
    const buf = c.createBuffer(1, sr * dur, sr);
    const d = buf.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = (Math.random()*2-1) * (1 - i/d.length);
    const src = c.createBufferSource(), g = c.createGain();
    src.buffer = buf; g.gain.value = vol;
    src.connect(g); g.connect(c.destination); src.start();
  }

  card()    { this._noise(0.04); }
  bomb()    { this._tone(55,'sine',0.6,0.5); this._tone(110,'sine',0.4,0.2,0.04); }
  yourTurn(){ this._tone(520,'sine',0.12,0.2); this._tone(660,'sine',0.12,0.2,0.13); }
  trickEnd(){ this._tone(880,'sine',0.18,0.15); }
  handEnd() { this._tone(440,'sine',0.15,0.2); this._tone(554,'sine',0.15,0.2,0.16);
              this._tone(659,'sine',0.25,0.2,0.32); }
}

export const sound = new SoundManager();
