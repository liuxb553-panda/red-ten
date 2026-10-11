# 红十前端重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 4 个单体 HTML 文件重构为 Vite 多页应用 + vanilla JS 模块化 + CSS 设计令牌体系，同时升级牌桌质感、添加炸弹爆炸动画、简化语音系统。

**Architecture:** Vite 多页入口 → HTML 骨架通过 `<script type="module">` 引入 page 模块 → page 模块组合 lib 模块 → 所有 CSS 通过 `@import` 链从 `tokens.css` 派生。纯 vanilla JS，不引入框架。

**Tech Stack:** Vite, vanilla JS (ES modules), CSS custom properties, Web Speech API, Web Audio API

---

### Task 1: Vite 骨架搭建

**Files:**
- Create: `web/vite.config.js`
- Create: `web/package.json`
- Modify: `web/index.html` (改为 Vite 入口)
- Modify: `web/play.html` (改为 Vite 入口)
- Modify: `web/replay.html` (改为 Vite 入口)
- Modify: `web/training.html` (改为 Vite 入口)

- [ ] **Step 1: 创建 package.json**

```json
{
  "name": "red-ten-web",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "devDependencies": {
    "vite": "^6.0.0"
  }
}
```

- [ ] **Step 2: 安装依赖**

```bash
cd web && npm install
```

- [ ] **Step 3: 创建 vite.config.js**

```js
import { defineConfig } from 'vite';
import { resolve } from 'path';
import { fileURLToPath } from 'url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));

export default defineConfig({
  root: __dirname,
  build: {
    outDir: 'dist',
    rollupOptions: {
      input: {
        index: resolve(__dirname, 'index.html'),
        play: resolve(__dirname, 'play.html'),
        replay: resolve(__dirname, 'replay.html'),
        training: resolve(__dirname, 'training.html'),
      },
    },
  },
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
});
```

- [ ] **Step 4: 改造 index.html 为 Vite 入口**

删除原有 `<style>` 和 `<script>` 内容，替换为：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>红十 Red Ten Poker</title>
<link rel="stylesheet" href="/src/styles/reset.css">
<link rel="stylesheet" href="/src/styles/tokens.css">
<link rel="stylesheet" href="/src/styles/index.css">
<link rel="stylesheet" href="/src/styles/animations.css">
</head>
<body>
<div id="splash">
  <div class="splash-title">红 十</div>
  <div class="splash-sub">Red Ten Poker</div>
  <div class="splash-cards">
    <div class="mini-card r10">10♥</div>
    <div class="mini-card red">A♥</div>
    <div class="mini-card blk">K♠</div>
    <div class="mini-card jok">JOK</div>
    <div class="mini-card blk">7♣</div>
    <div class="mini-card red">10♦</div>
  </div>
  <div class="splash-hint">按空格键跳过动画</div>
</div>
<div id="select">
  <div class="menu-btn play"    id="btn-play">⚔ 实战对局</div>
  <div class="menu-label">选择阵营，真人+AI 混战，一局定胜负</div>
  <div class="menu-btn train"   id="btn-train">🤖 AI 训练</div>
  <div class="menu-label">观战 AI 对决 或 启动自动训练</div>
  <div class="menu-btn replay"  id="btn-replay">⏪ 回看</div>
  <div class="menu-label">浏览训练记录，回放历史对局</div>
</div>
<script type="module" src="/src/pages/home.js"></script>
</body>
</html>
```

- [ ] **Step 5: 创建 src/pages/home.js**

从原 index.html 的 `<script>` 块（行 121-142）提取：

```js
let animDone = false;

function showSelect() {
  if (animDone) return;
  animDone = true;
  document.getElementById('splash').style.display = 'none';
  document.getElementById('select').style.display = 'flex';
}

document.addEventListener('keydown', e => {
  if (e.code === 'Space' && !animDone) { e.preventDefault(); showSelect(); }
});

setTimeout(showSelect, 2200);

document.getElementById('btn-play')?.addEventListener('click', () => {
  window.location.href = '/play';
});
document.getElementById('btn-train')?.addEventListener('click', () => {
  window.location.href = '/training';
});
document.getElementById('btn-replay')?.addEventListener('click', () => {
  window.location.href = '/replay';
});
```

- [ ] **Step 7: 创建 src/styles/index.css**

将原有 index.html 中 `<style>` 块的 CSS 全部移入此文件，把所有硬编码颜色值替换为 `tokens.css` 变量引用。

- [ ] **Step 8: 验证 index.html 可加载**

```bash
# 终端 1: 启动 Python 后端（不同端口）
python src/web_server.py --port 8000

# 终端 2: 启动 Vite dev server
cd web && npx vite --port 5173
```

打开 `http://localhost:5173` 确认 splash 动画和菜单正常显示，确认无 404 错误。Vite 自动将 `/api` 和 `/ws` 请求代理到 `localhost:8000`。

- [ ] **Step 9: Commit**

```bash
git add web/package.json web/package-lock.json web/vite.config.js \
        web/index.html web/src/styles/index.css web/src/styles/reset.css \
        web/src/styles/tokens.css web/src/styles/animations.css \
        web/src/pages/home.js
git commit -m "feat: Vite skeleton with index.html entry"
```

---

### Task 2: CSS 令牌 + 重置文件

**Files:**
- Create: `web/src/styles/tokens.css`
- Create: `web/src/styles/reset.css`
- Create: `web/src/styles/animations.css` (空骨架)
- Create: `web/src/styles/texture.css` (空骨架)

- [ ] **Step 1: 创建 reset.css**

```css
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; overflow: hidden; background: var(--color-felt-base);
  font-family: var(--font-body); color: var(--color-text-primary); }
button { font-family: inherit; cursor: pointer; }
input, select { font-family: inherit; }
a { color: inherit; text-decoration: none; }
```

- [ ] **Step 2: 创建 tokens.css**

```css
:root {
  /* 底色系统 */
  --color-felt-deep:    #081208;
  --color-felt-base:    #0c1a10;
  --color-felt-raise:   #113d1a;
  --color-felt-overlay: #165a23;

  /* 阵营色 */
  --color-red-team:     #dc4848;
  --color-red-glow:     #ff6b6b;
  --color-blue-team:    #589bdc;
  --color-blue-glow:    #7cb8f5;

  /* 强调色 */
  --color-gold:         #ffe42d;
  --color-gold-dim:     #b8a020;
  --color-redten:       #ffd200;

  /* 文字 */
  --color-text-primary: #e1e4d7;
  --color-text-dim:     #8a9a80;
  --color-text-inverse: #0c1a10;

  /* 牌面特殊色 */
  --color-card-bg:      #f5f0e8;
  --color-joker-purple: #7337c3;
  --color-joker-light:  #cd96eb;
  --color-suit-red:     #c0392b;
  --color-suit-black:   #1a1a1a;

  /* 间距系统 4px 基 */
  --space-xs:  4px;
  --space-sm:  8px;
  --space-md:  16px;
  --space-lg:  24px;
  --space-xl:  40px;
  --space-2xl: 64px;

  /* 阴影层级 */
  --shadow-card:       0 2px 6px rgba(0,0,0,0.5);
  --shadow-card-hover: 0 4px 14px rgba(0,0,0,0.6);
  --shadow-panel:      0 0 20px rgba(0,0,0,0.4);
  --shadow-overlay:    0 0 40px rgba(0,0,0,0.7);
  --shadow-gold:       0 0 8px rgba(255,228,45,0.4);

  /* 圆角 */
  --radius-card:  4px;
  --radius-btn:   6px;
  --radius-panel: 8px;

  /* 动效时长 */
  --dur-fast:     150ms;
  --dur-normal:   300ms;
  --dur-slow:     500ms;
  --dur-dramatic: 800ms;

  /* 字体 */
  --font-body:    "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif;
  --font-display: "STKaiti", "KaiTi", "Noto Serif SC", serif;
  --font-mono:    "SF Mono", "Cascadia Code", monospace;
}

@media (prefers-reduced-motion: reduce) {
  :root {
    --dur-fast:     0ms;
    --dur-normal:   0ms;
    --dur-slow:     0ms;
    --dur-dramatic: 0ms;
  }
}
```

- [ ] **Step 3: 创建 animations.css 骨架**

```css
/* All @keyframes — will be populated in subsequent tasks */
```

- [ ] **Step 4: 创建 texture.css 骨架**

```css
/* Table texture — will be populated in subsequent tasks */
```

- [ ] **Step 5: 验证 tokens 正确加载**

在浏览器 DevTools 中检查 `:root` 是否包含所有 CSS 变量。

- [ ] **Step 6: Commit**

```bash
git add web/src/styles/tokens.css web/src/styles/reset.css \
        web/src/styles/animations.css web/src/styles/texture.css
git commit -m "feat: CSS tokens, reset, empty animation & texture files"
```

---

### Task 3: 抽取 card.js + card.css

**Files:**
- Create: `web/src/lib/card.js`
- Create: `web/src/styles/card.css`
- Modify: `web/play.html` (移除内联 card CSS 和 cardHtml 函数)

- [ ] **Step 1: 创建 card.css — 从 play.html 提取全部牌面样式**

```css
.card { display: inline-block; width: 36px; height: 52px; border-radius: var(--radius-card);
  background: var(--color-card-bg); border: 1px solid #888; position: relative;
  flex-shrink: 0; margin-left: -18px; font-size: 11px; vertical-align: bottom;
  overflow: hidden; cursor: default; }
.card:first-child { margin-left: 0; }
.card .cr { position: absolute; top: 2px; left: 3px; font-weight: bold;
  line-height: 1; color: var(--color-suit-black); }
.card .cs { position: absolute; top: 13px; left: 3px; line-height: 1; color: var(--color-suit-black); }
.card.red-suit .cr, .card.red-suit .cs { color: var(--color-suit-red); }
.card.red-ten  { background: var(--color-redten); }
.card.red-ten .cr, .card.red-ten .cs { color: #8c2d00; }
.card.red-ten .cstar { position: absolute; bottom: 2px; right: 2px;
  font-size: 9px; color: #8c2d00; }
.card.big-joker   { background: var(--color-joker-purple); }
.card.small-joker { background: var(--color-joker-light); }
.card.big-joker .cj, .card.small-joker .cj { position: absolute; top: 50%;
  left: 50%; transform: translate(-50%, -50%); font-size: 9px; color: #fff;
  text-align: center; line-height: 1.3; white-space: nowrap; }
.card.back { background: var(--color-felt-raise); border-color: #3a7a44; cursor: default; }
.card.selectable { cursor: pointer; transition: transform var(--dur-fast); }
.card.selectable:hover { transform: translateY(-6px); }
.card.selected { transform: translateY(-10px); outline: 2px solid var(--color-gold); }
.card.scoring { box-shadow: 0 0 5px 2px rgba(255,220,60,0.55); }
```

- [ ] **Step 2: 创建 card.js — cardHtml 函数的唯一实现**

```js
// card.js — 牌面 HTML 渲染，全项目唯一实现
export function cardHtml(c, opts = {}) {
  let cls = 'card';
  if (c.rt) cls += ' red-ten';
  else if (c.bj) cls += ' big-joker';
  else if (c.sj) cls += ' small-joker';
  else if (c.red) cls += ' red-suit';
  if (c.sv > 0) cls += ' scoring';
  if (opts.selectable) cls += ' selectable';
  if (opts.selected) cls += ' selected';
  const di = opts.idx !== undefined ? ` data-idx="${opts.idx}"` : '';
  if (c.bj || c.sj)
    return `<div class="${cls}"${di}><span class="cj">${c.rl}</span></div>`;
  const star = c.rt ? '<span class="cstar">★</span>' : '';
  return `<div class="${cls}"${di}><span class="cr">${c.rl}</span><span class="cs">${c.ss}</span>${star}</div>`;
}

export function backCardHtml() {
  return `<div class="card back"></div>`;
}

export const RANK_SORT = {"3":3,"4":4,"5":5,"6":6,"7":7,"8":8,"9":9,"10":10,
                           "J":11,"Q":12,"K":13,"A":14,"2":15,"小王":16,"大王":17};
export const SUIT_SORT = {"CLUBS":0,"DIAMONDS":1,"HEARTS":2,"SPADES":3,"JOKER":4};

export function sortedHand(hand) {
  return hand
    .map((c, i) => ({c, i}))
    .sort((a, b) => {
      const rd = (RANK_SORT[a.c.rl] ?? 0) - (RANK_SORT[b.c.rl] ?? 0);
      if (rd !== 0) return rd;
      return (SUIT_SORT[a.c.ss] ?? 0) - (SUIT_SORT[b.c.ss] ?? 0);
    });
}
```

- [ ] **Step 3: 改造 play.html — 引入 card 模块**

在 play.html 中：
1. 将 `<link rel="stylesheet" href="/src/styles/card.css">` 加入 `<head>`
2. 删除 `<style>` 中的 `.card` 相关 CSS（行 18-40）
3. 在 `<script type="module">` 顶部添加 `import { cardHtml, backCardHtml, RANK_SORT, SUIT_SORT, sortedHand } from '/src/lib/card.js';`
4. 删除原有的 `function cardHtml`, `function backCardHtml`, `RANK_SORT`, `SUIT_SORT`, `function sortedHand` 定义
5. 删除全局 `let selectedCardIdxs = new Set();`（后续移到 state.js）

- [ ] **Step 4: 验证**

启动 Vite dev server，进入游戏，确认牌面渲染正确（大小、颜色、红十星标、joker 样式均正常）。

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/card.js web/src/styles/card.css web/play.html
git commit -m "feat: extract card.js and card.css as shared module"
```

---

### Task 4: 抽取音效 + 语音模块

**Files:**
- Create: `web/src/lib/sound.js`
- Create: `web/src/lib/speech.js`
- Delete: `web/audio/chars/` (136 个 MP3)
- Modify: `web/play.html` (移除内联 Sound IIFE 和 TTS 逻辑)

- [ ] **Step 1: 创建 sound.js**

```js
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
```

- [ ] **Step 2: 创建 speech.js**

```js
// speech.js — Web Speech API TTS，标准男女声
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
```

- [ ] **Step 3: 改造 play.html — 替换 Sound 和 TTS**

在 play.html 的 `<script type="module">` 添加：
```js
import { sound } from '/src/lib/sound.js';
import { speech } from '/src/lib/speech.js';
```

删除原有的 `Sound` IIFE（行 422-454）、`_ttsVoices` 变量（行 1783-1788）、`TRIGGER_MOD`（行 1791-1798）、`_currentAudio`（行 1801）、`_stopAudio`（行 1803-1806）、`speakBubble`（行 1808-1818）、`_speakWebSpeech`（行 1820-1836）、`showAIBubble`（行 1840+）、`AI_CHARACTER_POOL`（行 1750+）、`seatCharacters`（行 1770+）。

将所有 `Sound.card()` → `sound.card()`，`Sound.bomb()` → `sound.bomb()`，依此类推。

将 `showAIBubble(seat, trigger, delay, interrupt)` 调用替换为：
```js
speech.sayPass(/* gender based on seat: P1/P3/P5→female, P2/P4/P6→male */);
```

- [ ] **Step 4: 添加静音按钮到游戏 UI**

在 `#gpanel` 或 `#ghand` 区域添加：
```html
<button id="mute-btn" title="静音">🔊</button>
```

在 play.js 中绑定：
```js
document.getElementById('mute-btn').addEventListener('click', () => {
  const muted = sound.toggle();
  speech._muted = muted;
  document.getElementById('mute-btn').textContent = muted ? '🔇' : '🔊';
});
```

- [ ] **Step 5: 删除 web/audio/chars/ 目录**

```bash
rm -rf web/audio/
```

- [ ] **Step 6: 验证**

启动 dev server，进入游戏，测试：
- 出牌音效正常
- 炸弹低沉音正常
- AI 玩家出牌时说"过"（女声/男声各半）
- 点击静音按钮 → 无声音 → 再次点击 → 声音恢复
- 刷新页面 → 静音状态保持

- [ ] **Step 7: Commit**

```bash
git rm -r web/audio/
git add web/src/lib/sound.js web/src/lib/speech.js web/play.html
git commit -m "feat: extracted sound/speech modules, removed MP3s, Web Speech TTS"
```

---

### Task 5: 抽取 WebSocket + API + 状态模块

**Files:**
- Create: `web/src/lib/ws.js`
- Create: `web/src/lib/api.js`
- Create: `web/src/lib/state.js`

- [ ] **Step 1: 创建 api.js**

```js
// api.js — REST fetch 封装
const BASE = '';

export async function get(url) {
  const res = await fetch(BASE + url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export async function post(url, body) {
  const res = await fetch(BASE + url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}
```

- [ ] **Step 2: 创建 ws.js**

```js
// ws.js — WebSocket 连接/重连/消息分发
export function connectWS({ url, onOpen, onMessage, onClose, reconnectMs = 2000 } = {}) {
  let ws;
  let closed = false;

  function connect() {
    if (closed) return;
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${location.host}${url}`);

    ws.onopen = () => { if (onOpen) onOpen(ws); };

    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (onMessage) onMessage(msg, ws);
    };

    ws.onclose = () => {
      if (!closed && reconnectMs > 0) setTimeout(connect, reconnectMs);
      if (onClose) onClose();
    };
  }

  connect();

  return {
    send(data) {
      if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(data));
    },
    close() {
      closed = true;
      if (ws) ws.close();
    },
    getSocket() { return ws; },
  };
}
```

- [ ] **Step 3: 创建 state.js**

```js
// state.js — 游戏全局状态
export const state = {
  room: null,
  seat: -1,
  seats: [],
  events: [],
  myHand: [],
  legalMoves: [],
  selectedCards: new Set(),
  scores: [],
  phase: 'lobby',  // lobby | room | play | over
};

export function resetState() {
  state.room = null;
  state.seat = -1;
  state.seats = [];
  state.events = [];
  state.myHand = [];
  state.legalMoves = [];
  state.selectedCards.clear();
  state.scores = [];
  state.phase = 'lobby';
}
```

- [ ] **Step 4: 改造 play.html — 替换全局变量和 WS 逻辑**

在 `<script type="module">` 添加：
```js
import { get, post } from '/src/lib/api.js';
import { connectWS } from '/src/lib/ws.js';
import { state, resetState } from '/src/lib/state.js';
```

用 `state.room`, `state.seat`, `state.seats` 等替换全局 `myRoom`, `mySeat`, `roomSeats`。用新 `connectWS()` 替换 `connectWS()` 和 `connectSpectatorWS()` 函数。用 `get()/post()` 替换各处 `fetch()` 调用。

- [ ] **Step 5: 验证**

启动 dev server，完整走一遍：大厅→创建房间→加入→发牌→出牌→结算。确认 WebSocket 通信和状态同步正常。

- [ ] **Step 6: Commit**

```bash
git add web/src/lib/ws.js web/src/lib/api.js web/src/lib/state.js web/play.html
git commit -m "feat: extract ws, api, state modules from play.html"
```

---

### Task 6: 拆分 play.html 为页面模块

**Files:**
- Create: `web/src/pages/play.js` (主入口)
- Create: `web/src/pages/lobby.js`
- Create: `web/src/pages/room.js`
- Create: `web/src/pages/game.js`
- Create: `web/src/pages/config.js`
- Create: `web/src/lib/seat.js`
- Create: `web/src/styles/table.css`
- Create: `web/src/styles/components.css`
- Modify: `web/play.html` (缩减为 HTML 骨架)

- [ ] **Step 1: 创建 seat.js — 座位定位计算**

```js
// seat.js — 6 座位 CCW 定位
const CCW_NUM   = [1, 6, 5, 4, 3, 2];
const CCW_ORDER = [0, 5, 4, 3, 2, 1];

export function pLabel(p) { return 'P' + CCW_NUM[p]; }

export function computeSeatPositions(mySeat) {
  // 以玩家座位为底边中点，CCW 排列 6 个座位
  // 返回百分比 {top, left} 数组
  const positions = [];
  const baseOrder = [...CCW_ORDER];
  // 旋转使得 mySeat 在底部中央
  const myIdx = baseOrder.indexOf(mySeat);
  const ordered = [...baseOrder.slice(myIdx), ...baseOrder.slice(0, myIdx)];

  const layout = [
    {top: '8%',  left: '50%'},  // 顶
    {top: '18%', left: '22%'},  // 左上
    {top: '50%', left: '8%'},   // 左
    {top: '82%', left: '22%'},  // 左下
    {top: '88%', left: '50%'},  // 底 (player)
    {top: '82%', left: '78%'},  // 右下
    {top: '50%', left: '92%'},  // 右
    {top: '18%', left: '78%'},  // 右上
  ];

  for (let i = 0; i < 6; i++) {
    positions[ordered[i]] = layout[i];
  }
  return positions;
}
```

- [ ] **Step 2: 创建 table.css — 牌桌布局**

从 play.html 提取 `#game-screen`, `#gmain`, `#gpanel`, `#ghand`, trick zone, seat 定位等 CSS。

- [ ] **Step 3: 创建 components.css — UI 元件**

从 play.html 提取 lobby、room、button、input、overlay 等非牌面/牌桌的通用样式。

- [ ] **Step 4: 创建 lobby.js**

从 play.html 提取大厅逻辑（房间列表刷新、创建房间、加入房间）的 JS 代码，封装为：

```js
import { get, post } from '/src/lib/api.js';
import { state } from '/src/lib/state.js';

export function initLobby(container) {
  // ... 大厅 DOM 构建 + 事件绑定
  // fetchRoomList() — GET /api/rooms
  // createRoom(tier) — POST /api/room/create
  // joinRoom(code) — POST /api/room/join/{code}
}
```

具体实现：从 play.html 原有代码中提取并重构，保持功能完全一致。

- [ ] **Step 5: 创建 room.js**

```js
import { connectWS } from '/src/lib/ws.js';
import { state } from '/src/lib/state.js';

export function initRoom(container) {
  // ... 等待室 DOM 构建 + 座位网格 + 开始按钮
  // 6 座位网格用 computeSeatPositions
  // 点击座位 → 切换 claim/release
  // 开始按钮 → WebSocket 发 start 消息
}
```

- [ ] **Step 6: 创建 game.js**

```js
import { cardHtml, sortedHand } from '/src/lib/card.js';
import { sound } from '/src/lib/sound.js';
import { speech } from '/src/lib/speech.js';
import { state } from '/src/lib/state.js';
import { computeSeatPositions, pLabel } from '/src/lib/seat.js';

export function initGame(container) {
  // ... 游戏主界面：牌桌座位渲染、手牌区、trick zone、事件日志
  // handleGameEvent(ev) — 根据消息类型派发
  // renderTrickZone() — 渲染当前回合出牌
  // 炸弹检测 → 触发 bom-blast 动画
  // AI bubble → speech.sayPass()
}
```

- [ ] **Step 7: 创建 config.js**

从 play.html 提取 Battle Config 面板逻辑。

- [ ] **Step 8: 创建 play.js — 组装入口**

```js
import { initLobby } from './lobby.js';
import { initRoom } from './room.js';
import { initGame } from './game.js';
import { initConfig } from './config.js';
import { state } from '/src/lib/state.js';

const screens = {
  lobby:  document.getElementById('lobby-screen'),
  room:   document.getElementById('room-screen'),
  game:   document.getElementById('game-screen'),
  config: document.getElementById('config-screen'),
};

function showScreen(name) {
  state.phase = name;
  for (const [k, el] of Object.entries(screens)) {
    if (el) el.classList.toggle('active', k === name);
  }
}

initLobby(screens.lobby);
initRoom(screens.room);
initGame(screens.game);
initConfig(screens.config);

// 初始显示 lobby
showScreen('lobby');

export { showScreen };
```

- [ ] **Step 9: 缩减 play.html 为骨架**

play.html 只保留 HTML 结构 + `<link>` + `<script type="module" src="/src/pages/play.js">`，删除所有 `<style>` 和 `<script>` 内联内容。

- [ ] **Step 10: 验证**

完整游戏流程：大厅列表 → 创建房间 → 加入 → 开始 → 出牌 → Pass → 炸弹 → 结算。确认所有功能正常、视觉无回归。

- [ ] **Step 11: Commit**

```bash
git add web/src/pages/play.js web/src/pages/lobby.js web/src/pages/room.js \
        web/src/pages/game.js web/src/pages/config.js web/src/lib/seat.js \
        web/src/styles/table.css web/src/styles/components.css web/play.html
git commit -m "feat: split play.html into page modules (lobby/room/game/config)"
```

---

### Task 7: 重构 replay + training 页面

**Files:**
- Modify: `web/replay.html` (改造为 Vite 入口)
- Modify: `web/training.html` (改造为 Vite 入口)
- Create: `web/src/pages/replay.js`
- Create: `web/src/pages/training.js`

- [ ] **Step 1: 改造 replay.html**

移除内联 `<style>` 和 `<script>`，改用：
```html
<link rel="stylesheet" href="/src/styles/reset.css">
<link rel="stylesheet" href="/src/styles/tokens.css">
<link rel="stylesheet" href="/src/styles/card.css">
<link rel="stylesheet" href="/src/styles/table.css">
<link rel="stylesheet" href="/src/styles/components.css">
<link rel="stylesheet" href="/src/styles/animations.css">
<script type="module" src="/src/pages/replay.js"></script>
```

保留 HTML 结构骨架。

- [ ] **Step 2: 创建 replay.js**

从原 replay.html 的 `<script>` 提取 JS 逻辑，用 `import { cardHtml } from '/src/lib/card.js'` 替换内联的 `cardHtml`。

- [ ] **Step 3: 改造 training.html**

同样替换 CSS/JS 引用为 Vite 模块路径。保留 Chart.js CDN 引用。

- [ ] **Step 4: 创建 training.js**

从原 training.html 提取 JS 逻辑，复用 `cardHtml`、`api.js`、`ws.js`。

- [ ] **Step 5: 验证**

- replay.html: 选择 session → hand → rep，播放回放（play/pause/step/speed 正常）
- training.html: 观战 tab 和训练 tab 正常

- [ ] **Step 6: Commit**

```bash
git add web/replay.html web/training.html web/src/pages/replay.js web/src/pages/training.js
git commit -m "feat: migrate replay and training pages to Vite modules"
```

---

### Task 8: 质感层 + 动效 + 炸弹动画

**Files:**
- Modify: `web/src/styles/texture.css` (写入质感)
- Modify: `web/src/styles/animations.css` (写入全部 @keyframes)
- Modify: `web/src/pages/game.js` (炸弹检测 → 触发动画)

- [ ] **Step 1: 填充 texture.css**

```css
/* 桌面呢绒噪点纹理 */
.game-table {
  background:
    radial-gradient(ellipse at 50% 40%, #113d1a 0%, #0c1a10 60%, #081208 100%),
    url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.04'/%3E%3C/svg%3E");
}

/* 面板浮起 */
.panel-raised {
  background: linear-gradient(
    135deg,
    var(--color-felt-raise) 0%,
    var(--color-felt-base) 100%
  );
  box-shadow: var(--shadow-panel);
  border: 1px solid rgba(255,255,255,0.06);
}

/* 牌背纹理 */
.card.back {
  background: repeating-linear-gradient(
    45deg,
    transparent,
    transparent 2px,
    rgba(255,255,255,0.03) 2px,
    rgba(255,255,255,0.03) 4px
  ), var(--color-felt-raise);
  border: 1px solid rgba(255,228,45,0.12);
}

/* 桌沿暗角 */
.table-edge {
  box-shadow: inset 0 0 60px rgba(0,0,0,0.5);
}
```

- [ ] **Step 2: 在游戏容器上应用质感**

在 play.html、replay.html、training.html 的 `#gmain` / `#main` / `#spectate-main` 元素上添加 `class="game-table table-edge"`。

- [ ] **Step 3: 填充 animations.css — 收拢现有动效**

```css
/* ── 飞牌 ── */
@keyframes fly-to-trick {
  0%   { transform: translate(var(--from-x), var(--from-y)) scale(0.8); opacity: 0.5; }
  60%  { transform: translate(calc(var(--to-x)*0.6), calc(var(--to-y)*0.6)) scale(1.05); opacity: 1; }
  100% { transform: translate(var(--to-x), var(--to-y)) scale(1); opacity: 1; }
}

/* ── 屏幕震动 ── */
@keyframes screen-shake {
  0%, 100% { transform: translate(0, 0); }
  10% { transform: translate(-4px, 2px); }
  30% { transform: translate(3px, -3px); }
  50% { transform: translate(-2px, 4px); }
  70% { transform: translate(4px, -1px); }
  90% { transform: translate(-1px, 2px); }
}

/* ── Pass 标记 ── */
@keyframes pass-badge-pop {
  0%   { transform: scale(0); opacity: 0; }
  60%  { transform: scale(1.15); opacity: 1; }
  100% { transform: scale(1); opacity: 0.6; }
}

/* ── AI 气泡 ── */
@keyframes bubble-pop {
  0%   { transform: translateY(8px) scale(0.9); opacity: 0; }
  100% { transform: translateY(0) scale(1); opacity: 1; }
}

/* ── 日志滑入 ── */
@keyframes log-slide-in {
  0%   { transform: translateX(20px); opacity: 0; }
  100% { transform: translateX(0); opacity: 1; }
}

/* ── 牌面呼吸 ── */
@keyframes card-breathe {
  0%, 100% { transform: translateY(0); }
  50%      { transform: translateY(-3px); }
}

/* ── 红十脉动 ── */
@keyframes redten-pulse {
  0%, 100% { box-shadow: 0 0 6px rgba(255,228,45,0.4); }
  50%      { box-shadow: 0 0 16px rgba(255,228,45,0.8); }
}

/* ── 得分弹跳 ── */
@keyframes score-bounce {
  0%   { transform: scale(1); }
  40%  { transform: scale(1.3); color: var(--color-gold); }
  100% { transform: scale(1); }
}
```

- [ ] **Step 4: 填充 animations.css — 炸弹爆炸动画**

```css
/* ── 炸弹爆炸 ── */
@keyframes bomb-explode {
  0%   { transform: scale(0); opacity: 1; }
  40%  { transform: scale(1.8); opacity: 0.9; }
  100% { transform: scale(3); opacity: 0; }
}

@keyframes bomb-particle {
  0%   { transform: translate(0, 0) scale(1); opacity: 1; }
  100% { transform: translate(var(--px), var(--py)) scale(0); opacity: 0; }
}

@keyframes bomb-flash {
  0%   { background: rgba(255,255,255,0.6); }
  100% { background: transparent; }
}

.bomb-overlay {
  position: absolute; inset: 0; pointer-events: none; z-index: 50;
  animation: bomb-flash var(--dur-fast) ease-out forwards;
}

.bomb-blast {
  position: absolute; top: 50%; left: 50%; width: 60px; height: 60px;
  margin-left: -30px; margin-top: -30px;
  border-radius: 50%;
  background: radial-gradient(circle, var(--color-gold), rgba(255,100,0,0.6), transparent);
  animation: bomb-explode var(--dur-slow) ease-out forwards;
}

.bomb-particle {
  position: absolute; top: 50%; left: 50%; width: 10px; height: 10px;
  background: var(--color-gold);
  clip-path: polygon(50% 0%, 0% 100%, 100% 100%);
  animation: bomb-particle var(--dur-slow) ease-out forwards;
}
```

- [ ] **Step 5: 在 game.js 中实现炸弹触发**

当检测到游戏事件为 bomb 类型时，动态创建 DOM 元素：

```js
export function triggerBombAnimation(container) {
  // 创建爆心圆
  const blast = document.createElement('div');
  blast.className = 'bomb-blast';
  container.appendChild(blast);

  // 创建 8 个碎片粒子
  for (let i = 0; i < 8; i++) {
    const p = document.createElement('div');
    p.className = 'bomb-particle';
    const angle = (Math.PI * 2 * i) / 8;
    const dist = 40 + Math.random() * 30;
    p.style.setProperty('--px', `${Math.cos(angle) * dist}px`);
    p.style.setProperty('--py', `${Math.sin(angle) * dist}px`);
    container.appendChild(p);
  }

  // 创建白屏闪光层
  const flash = document.createElement('div');
  flash.className = 'bomb-overlay';
  container.appendChild(flash);

  // 300ms 后自动清理
  setTimeout(() => {
    blast.remove();
    flash.remove();
    container.querySelectorAll('.bomb-particle').forEach(el => el.remove());
  }, 500);
}
```

此外保留现有的 `document.body.classList.add('shake')` 震动触发。

- [ ] **Step 6: 验证**

进入一局有炸弹的对局，确认炸弹出牌时：
- 震动效果正常
- 金色爆心圆动画
- 碎片飞散
- 白屏闪光
- 300ms 后自动清理

- [ ] **Step 7: Commit**

```bash
git add web/src/styles/texture.css web/src/styles/animations.css web/src/pages/game.js \
        web/play.html web/replay.html web/training.html
git commit -m "feat: table texture, consolidated animations, bomb explosion effect"
```

---

### Task 9: 后端清理 + 全量验证

**Files:**
- Modify: `src/web_server.py` (移除 audio 静态挂载)
- Modify: `src/agents/personalities.py` (清理 TTS 相关属性)

- [ ] **Step 1: 后端清理**

在 `web_server.py` 中删除或注释 `app.mount("/audio", StaticFiles(directory="web/audio"), name="audio")`。

在 `personalities.py` 中将 `character.slug`, `voice_lines`, `lang`, `pitch`, `rate` 等 TTS 属性标记为 deprecated，或直接移除。保留后端 personality 的名称、描述、策略属性。

- [ ] **Step 2: 全量验证清单**

```bash
# 1. 启动服务器
python src/web_server.py &

# 2. 前端 dev server
cd web && npx vite --port 5173 &

# 3. 逐页验证
# - http://localhost:5173 → splash → 菜单
# - /play → 大厅 → 创建房间 → 加入 → 对战 → 结算
# - /replay → 选择 session → 播放回放
# - /training → 观战 + 训练两个 tab

# 4. 后端测试
python -m pytest tests/ -v --tb=short
mypy src/
```

- [ ] **Step 3: 构建验证**

```bash
cd web && npx vite build
ls web/dist/   # 确认 index.html play.html replay.html training.html assets/ 产出
```

- [ ] **Step 4: Commit**

```bash
git add src/web_server.py src/agents/personalities.py
git commit -m "chore: cleanup backend TTS/audio references after frontend refactor"
```

---

### 重构顺序总结

```
Task 1: Vite 骨架          ← 先搭框架
Task 2: tokens + reset     ← 变量体系就位
Task 3: card.js + card.css ← 共享渲染模块
Task 4: sound + speech     ← 音效语音（独立，不依赖其他模块）
Task 5: ws + api + state   ← 连接和状态（被 pages 依赖）
Task 6: pages 拆分         ← 核心重构（依赖上面所有 lib）
Task 7: replay + training  ← 复用 lib
Task 8: 质感 + 动效        ← 视觉升级（最后，不影响功能）
Task 9: 后端清理 + 验证    ← 收尾
```
