# Changelog — Red Ten Poker (红十)

---

## 2026-05-02

### 1. 单元测试基础设施

**文件**: `tests/test_legal_moves.py`, `tests/TEST_LOG.md`

建立单元测试套件，每次发现 bug 后添加针对性测试。当前包含 6 个测试用例：
- 领牌时所有合法牌型均可出（单张/对子/三条/炸弹）
- 3副牌重复卡牌的 rank 匹配
- 对子去重
- 序列化完整往返测试

详见 [TEST_LOG.md](../tests/TEST_LOG.md)。

---

### 2. 红十在普通对子/三条中按普通10计分

**文件**: `src/moves.py`

**问题**: ♥10 在对子/三条中使用了 `single_rank()` 返回的高位值(16)，导致对10错误地压制对2。

**修复**: `_add_same_rank_combos`、`_add_triple_combos`、`_add_triple_pair_combos`、`_bomb_key` 四个函数改用 `_SINGLE_RANK_MAP[int(combo[0].rank)]` 获取实际 rank 值。

---

### 3. `your_turn` 消息双嵌套修复

**文件**: `src/room_manager.py`

**问题**: `your_turn` WebSocket 消息中 `"cards": ser_move(m)` 将卡片数组嵌套在 dict 内，导致客户端 `m.cards` 拿到 dict 而非数组，Play 按钮始终灰色。

**修复**: 改为 `"cards": [ser_card(c) for c in m.cards]` 直接发送卡片数组。

---

### 4. 3副牌重复卡片导致 frozenset 去重碰撞

**文件**: `src/moves.py`, `web/play.html`

**问题**: 3副牌产生3张完全相同的 Q♠，`frozenset({Q♠₁, Q♠₂, Q♠₃})` 塌缩为 `frozenset({Q♠₁})`，三条的去重 key 与单张相同，三条被丢弃。

**修复**:
- 服务端去重 key 改为 `(m.type, len(m.cards), frozenset(m.cards))`
- 客户端 `findMatchingMove()` 改为按 rank label 排序匹配，忽略花色

---

### 5. 牌局前等待界面

**文件**: `web/play.html`

**功能**: 点击 "Start Game" 后不直接开始牌局，而是进入牌桌界面并在中央显示等待覆盖层：
- 展示所有玩家信息（头像图标、名称、得分）
- "开始新牌局" 按钮 → 发送 `start_game` 开始游戏
- "退出牌局" 按钮 → 返回房间界面

---

### 6. 每局结束后等待界面

**文件**: `src/room_manager.py`, `src/session.py`, `src/web_server.py`, `web/play.html`

**功能**: 每局结束后不再自动进入下一局，而是在牌桌中央显示结果覆盖层：
- 标题：Hand N Result
- 红队/非红队得分对比
- 每位玩家得分，并在得分后标注 大贡 / 末贡
- 玩家列表左对齐显示

**服务端改动**:
- `GameRoom` 新增 `_continue_event` (threading.Event)，提供 `signal_continue()` 和 `_wait_for_continue(timeout=120)`
- `GameSession` 新增 `continue_cb` 回调参数，替代 `time.sleep()` 在每局间等待
- WebSocket 新增 `continue_hand` 消息类型，调用 `room.signal_continue()`

**按钮行为**:
- "开始新牌局" → 发送 `continue_hand`，服务端继续下一局
- "退出牌局" → 发送 `continue_hand`（避免阻塞游戏线程），返回房间界面

**覆盖层复用**: 牌局前等待和每局结束共用 `#pre-game-overlay` div，通过 `showingHandEnd` 状态变量区分上下文。

---

### 7. 出牌区显示重设计

**文件**: `web/play.html`

**问题**: 牌桌中央6个出牌槽位分别显示每位玩家的出牌，多轮出牌后卡片重叠、显示混乱。

**修改**:
- 移除6槽位设计，改为单一中央显示区 `#gtrick-cards` + `#gtrick-name`
- 仅显示最后一手非过牌的出牌（即当前最佳牌型）
- 牌下方显示玩家名称
- 新出牌替代旧出牌，同时更新玩家名

**出牌动画**: 玩家出牌时，卡片从玩家座位区飞入中央显示区（CSS transition + `requestAnimationFrame`）

**过牌提示**: 玩家过牌时，在其座位旁显示 "Pass" 徽章，自动渐隐消失

**清理**:
- 移除 `TRICK_OFF` 常量
- 移除 `.gtrick-slot` CSS
- 简化 `buildGTrickZone()` 和 `positionGTrickZone()`

---

### 8. 红十在4+张普通炸弹中按普通10计分

**文件**: `src/moves.py`

**问题**: 玩家有4张10（含♥10），获得出牌权后无法出4张10的炸弹，只能出3张10（去掉红十）。

**修复**:
- `_is_valid_bomb()`: 移除 `or c.is_red_ten()` 检查，允许红十参与普通炸弹
- `_add_bomb_combos()`: 移除 `and not c.is_red_ten()` 过滤，红十正常计入rank分组

`_bomb_key()` 的rank计算早已正确处理此情况（注释注明 "red-ten plays as 10 in normal bomb context"）。

**测试**: `test_red_ten_in_normal_bomb` — 验证4张10（含♥10）可组成炸弹，rank值为普通10(8)

---

### 9. AI出牌延迟

**文件**: `src/room_manager.py`

**功能**: AI玩家出牌前随机延迟1-3秒，模拟真实玩家思考时间。
在 `SeatController.choose_action()` 的AI路径中增加 `time.sleep(random.uniform(1.0, 3.0))`。

---

### 10. 红十红心计数显示

**文件**: `src/state.py`, `src/hand.py`, `src/gui_renderer.py`, `src/serializers.py`, `web/play.html`

**功能**: 玩家每打出一张红桃10，头像旁显示一个♥标记。打出多张红桃10时显示对应数量的♥（最多3个），保留 "Red" 文字。

**服务端改动**:
- `PlayerStatus.identity_revealed` 从 `bool` 改为 `red_ten_count: int`，新增 `@property identity_revealed` 兼容旧代码
- `revealed_red_ten_count()` 改为对 `red_ten_count` 求和
- `_apply_play()` 每张红桃10都递增计数并调用 `log_identity_reveal()`
- `GameSnapshot` 新增 `red_ten_counts` 字段
- 快照序列化新增 `"rtc"` 键

**客户端**: 根据 `snap.rtc[p]` 渲染 `♥.repeat(n) + ' Red'`

---

### 11. 末贡判定时机修正

**文件**: `web/play.html`

**问题**: 游戏进行中，`finish_order` 中最后一位已完成的玩家被错误标记为"末贡"。末贡应在牌局结束时由服务端 `HandResult.mo_gong` 判定。

**修复**: `renderGame()` 中去除 `pos === snap.fo.length-1 ? ' 末贡'` 分支，游戏进行中仅显示"大贡"和序号，末贡标签仅在牌局结束覆盖层显示。

---

### 12. 末贡未出牌展示

**文件**: `src/state.py`, `src/hand.py`, `src/serializers.py`, `web/play.html`

**功能**: 牌局结束后、显示结果前，在牌桌中央展示末贡玩家手中未打出的牌。分牌（5/10/K）有金色光晕标记，鼠标悬停时扑克牌上提。

**服务端改动**:
- `HandResult` 新增 `mo_gong_hands: dict` 字段，记录每位末贡玩家剩余手牌
- `_compute_result()` 在三个返回路径中均捕获 `mg_hands`
- `ser_result()` 新增 `"mg_hands"` 键

**客户端**: 新增 `#mogong-display` 区域，`showMoGongDisplay()` 函数按玩家分组展示牌面，包含"继续"按钮进入结果界面。

---

### 13. 牌局结束条件与末贡分牌转移

**文件**: `src/hand.py`

**问题 1**: 每局双方总分不等于300（例如红方150 + 非红方110 = 260），计分缺失。

**问题 2**: 一方所有玩家出完牌后，另一方剩余玩家继续对战直到全部出完，牌局才结束。正确规则是：任何一方所有玩家出完牌则牌局结束。

**修复**:
- `_is_hand_over()`: `>= 5` 改为 `>= 6`（安全兜底，主要结束条件由 `_check_terminal()` 控制）
- `_check_terminal()`: 当一方全员完成且对方有部分完成时，返回 `TerminalKind.NORMAL`（不再返回 None）
- `_compute_result()`: 在 NORMAL 路径中，扫描未完成玩家手中剩余的分牌（5/10/K），将其分值转移给对方队伍
