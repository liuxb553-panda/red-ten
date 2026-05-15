// speech.js — Web Speech API TTS，标准男女声说"过"
class SpeechManager {
  constructor() {
    this._muted = localStorage.getItem('redten-mute') === '1';
    this._femaleVoice = null;
    this._maleVoice = null;
    this._ready = false;
    this._init();
  }

  async _init() {
    if (!window.speechSynthesis) return;
    const voices = await new Promise(resolve => {
      const list = speechSynthesis.getVoices();
      if (list.length) return resolve(list);
      speechSynthesis.onvoiceschanged = () => resolve(speechSynthesis.getVoices());
    });
    this._femaleVoice = voices.find(v => v.lang.startsWith('zh') && /female|nv/i.test(v.name))
                     || voices.find(v => v.lang.startsWith('zh'));
    this._maleVoice = voices.find(v => v.lang.startsWith('zh') && /male|nan/i.test(v.name))
                   || voices.find(v => v.lang.startsWith('zh'));
    this._ready = true;
  }

  say(text, gender = 'female') {
    if (this._muted || !window.speechSynthesis) return;
    speechSynthesis.cancel(); // 打断当前播放，防重叠
    const u = new SpeechSynthesisUtterance(text);
    u.voice = gender === 'male' ? this._maleVoice : this._femaleVoice;
    u.rate = 1.0;
    u.pitch = gender === 'male' ? 0.9 : 1.1;
    speechSynthesis.speak(u);
  }

  sayPass(gender) { this.say('过', gender); }
}

export const speech = new SpeechManager();
