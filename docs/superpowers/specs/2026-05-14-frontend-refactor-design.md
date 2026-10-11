# 红十前端重构设计

**日期:** 2026-05-14
**分支:** ai-training
**范围:** web/ 目录全部 4 个页面
**目标:** 可维护性 + 视觉升级，两者并重

---

## 1. 技术选型

- **Vite** 多页应用，vanilla JS 模块化（ES modules）
- 不引入 React/Vue 等框架
- CSS 通过 Vite `@import` 链组织
- 音频：删除 136 个 MP3 文件，改用 Web Speech API (SpeechSynthesis)
- 产物为标准静态 HTML/CSS/JS，为将来 Tauri/Electron 桌面化预留路径

---

## 2. 文件架

```
web/
├── vite.config.js              # 多页入口：index, play, replay, training
├── index.html                  # 入口页（骨架，~2KB）
├── play.html                   # 游戏主体（骨架，~5KB）
├── replay.html                 # 回放
├── training.html               # 训练看板
├── src/
│   ├── styles/
│   │   ├── tokens.css          # CSS 变量：颜色、间距、阴影、圆角、动效时长、字体
│   │   ├── reset.css           # CSS reset + body 全局基础
│   │   ├── card.css            # 牌面渲染（唯一一份）
│   │   ├── table.css           # 牌桌座位布局 + trick zone
│   │   ├── components.css      # 按钮、弹窗、badge、overlay 等 UI 元件
│   │   ├── animations.css      # 所有 @keyframes + transition 集中管理
│   │   └── texture.css         # 牌桌质感（噪点、渐变叠加、阴影层次）
│   ├── lib/
│   │   ├── card.js             # cardHtml() 唯一实现
│   │   ├── seat.js             # 座位定位计算
│   │   ├── sound.js            # 音效管理（静音开关 + 重叠防护）
│   │   ├── speech.js           # Web Speech API TTS（标准男女声）
│   │   ├── ws.js               # WebSocket 客户端封装
│   │   ├── api.js              # REST fetch 封装
│   │   └── state.js            # 全局状态管理（替代散布的全局变量）
│   ├── pages/
│   │   ├── home.js             # index.html 入口逻辑
│   │   ├── play.js             # play.html 主入口
│   │   ├── lobby.js            # 大厅：房间列表 + 创建/加入
│   │   ├── room.js             # 等待室：座位网格 + 开始
│   │   ├── game.js             # 游戏中：回合管理 + 出牌 + 结算
│   │   ├── config.js           # 战斗配置面板
│   │   ├── replay.js           # 回放逻辑
│   │   └── training.js         # 训练看板逻辑
│   └── audio/                  # 删除：不再需要 136 个 MP3
```

---

## 3. 设计令牌 tokens.css

统一所有颜色、间距、阴影、圆角、动效时长、字体：

```css
:root {
  /* 底色系统 */
  --color-felt-deep:    #081208;   /* 最深：牌桌边缘阴影 */
  --color-felt-base:    #0c1a10;   /* 主底：牌桌呢绒色 */
  --color-felt-raise:   #113d1a;   /* 浮起：卡片/面板背景 */
  --color-felt-overlay: #165a23;   /* 叠加：hover / active 态 */

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
```

**设计决策：**
- `--font-display` 楷体用于标题/得分数字，`--font-body` 黑体用于 UI 文字，形成「墨韵」对比
- 间距 4px 基与牌面尺寸 (36×52) 天然适配
- 所有颜色通过变量引用，改一处全局生效

---

## 4. 质感层 texture.css

牌桌从纯色平面升级为有「呢绒布面」触感：

- **径向光晕：** `radial-gradient` 从中心亮到四角暗，引导视线聚焦 trick zone
- **SVG 噪点叠加：** 内联 SVG data URI (~200 bytes) 模拟呢绒纤维，零额外请求
- **面板浮起：** 135° 对角线渐变 + `box-shadow` + 微弱白边，营造凸起感
- **牌背纹理：** `repeating-linear-gradient` 45° 条纹模拟牌背，不依赖图片
- **桌沿暗角：** `inset box-shadow` 模拟牌桌边缘的木质边框阴影

所有质感纯 CSS 实现，零外部资源。

---

## 5. 动效系统 animations.css

### 5.1 现有动效收拢

- `fly-to-trick` — 飞牌：手牌区 → trick zone (cubic-bezier 缓动)
- `screen-shake` — 屏幕震动（8% 偏移量，300ms）
- `pass-badge-pop` — pass 标记弹出
- `bubble-pop` — AI 语音气泡弹出
- `log-slide-in` — 事件日志右滑入

### 5.2 新增动效

- `card-breathe` — 手牌悬停微浮动（±3px）
- `redten-pulse` — 红十牌金色脉动发光
- `score-bounce` — 得分变化数字弹跳变色

### 5.3 炸弹爆炸 bom-blast（新增）

三层叠加的 300ms 爆炸动画：

1. **爆心圆** — 金色圆形从牌中心炸开扩散至消失
2. **碎片粒子** — 8-12 个三角碎片从爆心沿 `--px`/`--py` CSS 变量随机飞散
3. **白屏闪光** — 全屏 100ms 白闪

三层层叠，配合 `screen-shake` 震动，形成完整爆炸反馈。`bom-blast` class 触发，300ms 自动结束。

### 5.4 无障碍

所有动效通过 `prefers-reduced-motion: reduce` 查询可关闭。

---

## 6. 音效与语音

### 6.1 音效管理 sound.js

- 静音开关，状态持久化到 `localStorage('redten-mute')`
- 游戏画面右上角小喇叭图标，点击切换
- Web Audio API 音效引擎封装
- 静音时立即 kill 所有正在播放的 oscillator

### 6.2 语音系统 speech.js

**删除：** `web/audio/chars/` 下全部 136 个 MP3 文件、play.html 中硬编码的 144 条台词数组、Google Gemini TTS 逻辑。

**替换为：** Web Speech API (SpeechSynthesis)，标准男女声说"过"。

```
speech.sayPass('female')  →  女声说"过"
speech.sayPass('male')    →  男声说"过"
```

- 每次出声前 `speechSynthesis.cancel()`，打断当前播放，**彻底解决重叠问题**
- 优先选取系统中文女声/男声，fallback 任意中文声音
- 音色与速度固定（rate 1.0, pitch: 女 1.1 / 男 0.9）

### 6.3 AI 玩家声音分配

6 个 AI 座位：
- P1、P3、P5 → 女声
- P2、P4、P6 → 男声

---

## 7. JS 模块职责

| 模块 | 职责 | 暴露 |
|------|------|------|
| `lib/api.js` | `fetch()` 封装，base URL 处理，错误统一 | `get()`, `post()` |
| `lib/ws.js` | WebSocket 连接/重连/消息分发 | `connect(url, handlers)` |
| `lib/card.js` | 牌面 HTML/CSS 渲染（唯一实现） | `cardHtml(card)`, `cardBackHtml()` |
| `lib/seat.js` | 6 座 CCW 定位计算 | `computeSeatPositions(mySeat)` |
| `lib/sound.js` | 音效引擎 + 静音管理 | `sound.play('bomb')`, `sound.toggle()` |
| `lib/speech.js` | Web Speech TTS | `speech.sayPass(gender)` |
| `lib/state.js` | 游戏全局状态 | `state.room`, `state.hand`, `state.update(msg)` |
| `pages/lobby.js` | 大厅逻辑 | `initLobby(container)` |
| `pages/room.js` | 等待室逻辑 | `initRoom(container)` |
| `pages/game.js` | 回合管理 + 出牌 + 结算 | `initGame(container)` |
| `pages/config.js` | 战斗配置面板 | `initConfig(container)` |
| `pages/replay.js` | 回放控制 | `initReplay(container)` |
| `pages/training.js` | 训练看板 | `initTraining(container)` |
| `pages/home.js` | 入口动画 + 菜单路由 | `initHome()` |
| `pages/play.js` | 组装 lobby/room/game/config 四个子屏 | `initPlay()` |

每个 page 模块暴露一个 `init*` 函数，接收要挂载的 DOM 容器。

---

## 8. 重构顺序（6 步）

1. **搭 Vite 骨架** — `vite.config.js`，4 个 HTML 入口，确认空壳能跑
2. **抽 `tokens.css` + `reset.css`** — 全局变量注入所有现有页面
3. **抽 `lib/`** — card.js, seat.js, sound.js, speech.js, ws.js, api.js
4. **拆 `pages/`** — 按 play.html 子屏拆 lobby/room/game/config
5. **重构 replay + training** — 复用 lib 模块
6. **质感 + 动效** — texture.css, animations.css, 炸弹动画

---

## 9. 不做的

- 不引入 React/Vue 等 UI 框架
- 不改后端 Python 代码（除非前端接口变化需要）
- 不改 Chart.js 用法（training 页面保留 CDN 引用）
- 不做 i18n 提取（保留中英混用现状）
- 不改变 WebSocket 协议

---

## 10. 测试策略

- 每步完成后手动验证 4 个页面可正常加载
- 播放一场完整对局验证 game flow
- 回放一局训练数据验证 replay
- 启动一次训练看板验证 training
- `mypy src/` + `pytest tests/` 确认后端无回归
