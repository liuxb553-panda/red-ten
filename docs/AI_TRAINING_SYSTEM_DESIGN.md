# AI 自对弈训练系统 + 页面架构重构

**日期**: 2026-05-09

---

## 1. 背景

项目已有 4 种 AI 玩家类型（RuleBased / Search / ML / MultiAgent），但存在以下问题：

- 训练管线是 CLI-only，用户无法直观启动训练、监控进度、回放训练对局
- 页面架构混乱，入口分散
- MLPlayer 具备学习能力但缺乏风格多样性，MultiAgentPlayer 有风格但 MLP 未针对其决策管线训练

## 2. 页面架构

```
/              → 开场动画 → 选择界面（实战 / 训练 / 回看）
/play          → 实战对局（当前 lobby → 房间 → 游戏）
/training      → 训练模式选择（观战 / 自动训练）
/replay        → 训练记录文件列表 → 加载回放
```

所有页面均为独立 HTML 文件，在 `web/` 目录下。

## 3. 功能模块

### 3.1 开场动画 + 选择界面

- 页面刷新时播放红十文字 CSS 动画（具体形式和效果待定，先用占位动画）
- 动画结束后显示三选一入口
- 动画期间可按空格跳过

### 3.2 实战对局 (`/play`)

保持现有功能不变。需包含：
- 空格暂停功能（非本人回合时生效，在手牌区和出牌区之间显示 "⏸ PAUSED"）

### 3.3 AI 训练界面 (`/training`)

风格与实战界面保持一致，包含两个子模式：

**真人观战模式**
- 复用 BattleConfig：6 座位 AI 配置 + 速度 + 局数
- 连接 `/ws/{code}/spectate`，全牌面可见
- 空格暂停功能

**AI 自动训练模式**
- 训练参数：100 手牌 × 每手 30 次重复 = 3000 局
- 训练流程：
  1. 生成 100 手随机牌（记录到 deals.json）
  2. 逐手训练：固定发牌，跑 30 次（ε=0.2，不同 random seed）
  3. 每局收集 (65维特征, 标签) → 合并为 samples.npz
  4. 全部完成后训练 MLP → 保存 model.pt
- 进度显示：WebSocket 推送（当前手牌 N/100，重复次数 M/30）
- 界面：进度条 + 计数器 + 状态文字
- 内嵌训练仪表板（移植 dashboard.html 的统计表）
- 训练前后各跑 benchmark vs RuleBased 对比

### 3.4 回放 (`/replay`)

- 服务端训练文件列表 → 选择 session → 选择手牌 → 选择重复次数 → 加载回放
- 空格暂停功能
- 复用现有回放器核心逻辑

## 4. 训练存储结构

```
data/training/
├── session_20260509_143000/
│   ├── meta.json              # {hands: 100, reps: 30, epsilon: 0.2, tiers: [...]}
│   ├── deals.json             # 100 手初始发牌
│   ├── benchmark_before.json  # 训练前 benchmark
│   ├── benchmark_after.json   # 训练后 benchmark
│   ├── samples.npz            # 训练样本 (X, y)
│   ├── model_before.pt        # 训练前模型
│   ├── model_after.pt         # 训练后模型
│   └── hands/
│       ├── hand_00001/
│       │   ├── rep_01.jsonl   # 完整事件日志
│       │   ├── rep_02.jsonl
│       │   └── ...
│       └── hand_00100/
│           └── ...
```

每局 JSONL 格式复用现有 `ser_event()`，兼容回放器。

## 5. 服务端改动

### 新文件

- `src/train_mlp_fixed.py` — 固定发牌训练引擎
  - `FixedDealTrainer` 类：生成手牌、固定发牌、多轮重放、数据收集、MLP 训练
  - WebSocket 推送进度

### 修改文件

- `src/hand.py` — `Hand.deal_preset(cards_per_player)` 方法
- `src/web_server.py` — 新增路由：
  - `GET /api/training/sessions` — 列出训练 session
  - `GET /api/training/session/{id}` — session meta + 手牌列表
  - `GET /api/training/session/{id}/hand/{hid}/rep/{rid}` — 返回 JSONL 事件
  - `WS /ws/training/{session_id}` — 训练进度推送
  - `GET /training` — 返回 training.html
  - `GET /replay` — 返回 replay.html
  - `POST /api/training/start` — 启动训练任务
- `web/index.html` — 改造为开场动画 + 选择界面
- `web/play.html` — Bug 修复 + 空格暂停

## 6. 暂停功能

- **观战/回放模式**：空格切换暂停，缓冲 WebSocket 消息，恢复后按序播放
- **真人对战模式**：仅非本人回合时生效，暂停时在手牌区和出牌区之间显示 "⏸ PAUSED"

## 7. 训练模式下的探索多样性

为保证同一手牌的 30 次重放产生不同对局路径：

- 强制设置 `epsilon=0.2`（20% 概率随机选牌）
- 纯启发式人格（激进/保守/均衡）临时注入 `w_random=0.1` 噪声
- MLP 采样数可临时降低到 3~5 以增加评分波动

## 8. 实现顺序

1. Bug 修复（play.html 状态清理）
2. `hand.py` — `deal_preset()` 方法
3. `src/train_mlp_fixed.py` — 固定发牌训练引擎
4. `web_server.py` — 新路由
5. `web/index.html` — 开场动画 + 选择界面
6. `web/training.html` — 训练界面
7. `web/replay.html` — 回放界面
8. 测试验证
9. CHANGELOG 更新
