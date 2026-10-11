# 红十多智能体 AI 玩家架构设计

## 1. 动机

当前 AI 玩家（规则型 / 搜索型 / ML型）都是单一决策函数：输入游戏状态，输出一个出牌选择。出牌风格无法调节——同一层级的 AI 打法趋同，缺乏个性。

参考 **TradingAgents** 多智能体协作架构，本文档设计一套可组合的内部 Agent 团队系统，赋予每个 AI 玩家独特的出牌人格。

## 2. 核心设计理念

### 2.1 人格 = 规则选择 + Agent 组合 + 辩论配置

不同出牌风格由三个维度共同决定：

```
人格 = 策略规则集（选哪些规则 + 权重） + Agent 组合（哪些倡导者在场） + 辩论深度（几轮）
```

```
激进型 = {intercept:1.2, friendly_fire:0.5, identity_protect:0, ...}
       + [BullishResearcher] + debate_rounds=0
保守型 = {identity_protect:1.5, safe_play:1.3, score_rush:0.3, ...}
       + [BearishResearcher] + debate_rounds=0
均衡型 = {intercept:0.8, friendly_fire:1.0, identity_protect:1.0, ...}
       + [BullishResearcher + BearishResearcher] + debate_rounds=2
```

其中**策略规则是独立的最小单元**——每条规则一个文件，只做一件事。加新策略 = 加一个规则文件 + 在人格配置里引用，不改任何已有代码。

### 2.2 三层解耦

```
人格配置（选规则、调权重）  →  倡导者（规则执行器）  →  策略规则（独立评分单元）
     ↓                              ↓                        ↓
 加新人格不改代码             不关心有哪些规则            一条规则只做一件事
 改战斗风格只调权重           只负责汇总和辩论            一个文件一条规则
```

比权宜之计（策略硬编码在倡导者里）好在一个关键点上：**加新策略规则是闭包操作——只加文件、不改文件**。规则之间互不知晓，通过倡导者汇总时自然竞争。人格之间共享同一条规则，只调权重表达偏好。

### 2.3 共享状态而非聊天传递

参考 TradingAgents 的 `AgentState` 设计，内部 Agent 之间**不通过对话传递信息**，而是各自向共享结构写入分析结果，下游 Agent 按需读取特定字段。这避免了上下文膨胀和信息衰减。

### 2.4 兼容现有架构

多层 Agent 系统作为 `Player.choose_action()` 的内部实现，对外接口不变。现有的三种 AI 玩家都可以逐步改造。

### 2.5 双路径设计

| 路径 | 分析师 | 倡导者 | 决策层 | 状态 |
|------|--------|--------|--------|------|
| **路径 A — 规则驱动** | 规则函数（统计计数、启发式） | 启发式评分函数 | 现有 AI Tier + 融合公式 | 默认实现 |
| **路径 B — LLM 驱动** | LLM 分析报告 | LLM 辩论 | LLM 裁决 | 预留接口 |

两条路径通过 `BaseAgent.mode: AgentMode` 字段切换，签名一致（`analyze(state) -> dict`），规则函数和 LLM 调用可互换。

## 3. 系统架构

### 3.1 整体层次

```
Hand._play_trick()
  │
  └─ player.choose_action(state, legal_moves)   ← 对外接口不变
       │
       └─ MultiAgentBrain.decide(state, legal_moves)  ← 新增内部层
            │
            ├─ Phase 1: 分析师采集信息 → SharedAnalysis（前4个并行 + Risk串行）
            │     ├─ HandAnalyst.analyze()        手牌结构分析
            │     ├─ PositionAnalyst.analyze()    座位·顺序分析
            │     ├─ TeamAnalyst.analyze()        身份·队友分析
            │     ├─ OpponentAnalyst.analyze()    对手牌况·风格分析
            │     └─ RiskAnalyst.analyze()        风险·暴露评估
            │
            ├─ Phase 1.5: 战略原则层 — 全局目标判断 ★
            │     └─ StrategyDirector.assess(analysis)
            │          ├─ 评估全局局势（分差、关人窗口、危险程度）
            │          ├─ 产出一组 规则权重修正系数 → StrategicContext
            │          └─ 下游战术规则的权重被动态调整
            │
            ├─ Phase 2: 倡导者执行战术规则 → ResearcherOpinion
            │     └─ Researcher.evaluate(analysis, legal_moves, context)
            │          │
            │          ├─ 战术规则层（独立、可插拔，权重被战略原则动态修正）
            │          │   ├─ InterceptRule      对手快出完 → 炸
            │          │   ├─ FriendlyFireRule   领先是队友 → 不炸
            │          │   ├─ IdentityProtectRule 身份未明 → 藏红十
            │          │   ├─ SafePlayRule       分牌无人压 → 谨慎
            │          │   ├─ LastActRule         末位+队友领先 → PASS
            │          │   ├─ HelpTeammateRule    队友被压 → 解围
            │          │   ├─ ScoreRushRule       机会难得 → 抢分
            │          │   └─ ...                加新规则只加文件
            │          │
            │          ├─ BullishResearcher  → 加载 offensive 类规则
            │          ├─ BearishResearcher  → 加载 defensive 类规则
            │          └─ WildcardResearcher → 随机扰动
            │
            ├─ Phase 3: 辩论 (可选，取决于人格配置)
            │     └─ Researcher.debate() × N rounds
            │
            ├─ Phase 4: 决策经理终裁
            │     └─ LeadAgent.choose()
            │          ├─ 现有 AI Tier 提供基线评分
            │          └─ 融合公式叠加倡导者意见
            │
            └─ Phase 5: 审核
                  └─ Validator.validate(move, legal_moves)  ← 安全兜底
```

### 3.2 SharedAnalysis — 共享分析状态

```python
@dataclass
class SharedAnalysis:
    """内部 Agent 之间共享的结构化分析结果，每个 Agent 写入自己负责的字段"""

    # HandAnalyst 写入
    my_bombs: list[Move]                        # 我手中可出的炸弹
    my_combos_by_type: dict[CardType, list[Move]]  # 按牌型分组的合法出牌
    dangerous_cards: list[Card]                 # 危险牌（大王、红十等高价值牌难出手）
    hand_strength: float                        # 手牌整体质量 [0-1]
    estimated_tricks_to_finish: int             # 估算出完还需几手

    # PositionAnalyst 写入
    my_position_in_trick: int                   # 本轮第几个出牌
    players_after_me: list[int]                 # 我之后还有谁
    is_last_to_act: bool                        # 是否最后行动
    trick_leader_team: Optional[Team]           # 本轮领牌方队伍

    # TeamAnalyst 写入
    likely_teammates: list[float]               # P(队友) × 6
    likely_opponents: list[float]               # P(对手) × 6
    red_ten_status: str                         # "all_hidden" | "partial" | "all_revealed"
    ally_finish_advantage: int                  # 完成进度优势 [-6, 6]
    teammate_needs_help: list[int]              # 哪些队友可能需要解围

    # OpponentAnalyst 写入
    scoring_cards_remaining: dict[Team, int]    # 红方/非红方剩余分牌价值
    bombs_visible: list[Move]                   # 已出现的炸弹
    high_cards_unplayed: list[Rank]             # 未出现的大牌（2、王等）
    estimated_opp_hand_strength: list[float]    # 每位对手手牌强度估计 [0-1]
    opponent_style_guess: list[str]             # 每位对手风格推测 ["aggressive"|"conservative"|"unknown"]

    # RiskAnalyst 写入
    red_ten_exposure_risk: float                # 出红十牌型的暴露风险 [0-1]
    score_loss_risk: dict[CardType, int]        # 各牌型可能送出的分值
    situation_advantage: float                  # 当前局势对己方有利程度 [-1, 1]

    # StrategyDirector 写入（Phase 1.5 战略原则层）
    strategic_context: Optional[StrategicContext]  # 全局目标 + 规则权重修正系数


@dataclass
class StrategicContext:
    """由战略原则层写入，影响下游所有战术规则的权重"""
    primary_goal: str                    # "guan_ren" | "avoid_being_guaned" | "max_score" | "balanced"
    rule_weight_modifiers: dict[str, float]  # {"intercept": +0.4, "speed_first": -0.6, ...}
    goal_urgency: float                  # 目标紧迫度 [0, 1]，越高越应该冒险
    reasoning: str                       # 调试用："关人窗口打开：红方2人已出完，非红方0人"
```

### 3.3 分析师 Agent

每个分析师是一个轻量函数，从 `GameState` 提取特定维度的信息：

| Agent | 职责 | 输入 | 输出字段 |
|-------|------|------|----------|
| **HandAnalyst** | 手牌结构分析：炸弹、可出牌型、危险牌、手牌质量 | `GameState.hands[me]`, `legal_moves` | `my_bombs`, `my_combos_by_type`, `dangerous_cards`, `hand_strength`, `estimated_tricks_to_finish` |
| **PositionAnalyst** | 评估座位位置、出牌顺序 | `GameState.turn_order`, `GameState.current_trick` | `my_position_in_trick`, `players_after_me`, `is_last_to_act`, `trick_leader_team` |
| **TeamAnalyst** | 推断队伍关系、出牌信号 | `IdentityTracker`, `PlayerStatus` | `likely_teammates`, `likely_opponents`, `red_ten_status`, `ally_finish_advantage`, `teammate_needs_help` |
| **OpponentAnalyst** | 对手牌分布、风格推测、剩余牌追踪 | `GameState.played_cards`, `GameState.hands` | `scoring_cards_remaining`, `bombs_visible`, `high_cards_unplayed`, `estimated_opp_hand_strength`, `opponent_style_guess` |
| **RiskAnalyst** | 出牌风险评估：身份暴露、送分、局势优劣 | `SharedAnalysis`（读取前4个分析结果）, `IdentityTracker` | `red_ten_exposure_risk`, `score_loss_risk`, `situation_advantage` |

分析师之间无依赖（除 RiskAnalyst 需要读取前 4 个结果），4 个可并行执行，RiskAnalyst 串行其后。

### 3.4 策略层

策略层分为两级：

- **战略原则**（Phase 1.5）：回答「这一局要什么」——评估全局局势，动态修正战术规则的权重。不直接给 move 打分。
- **战术规则**（Phase 2）：回答「这一手出什么」——逐 move 打分。权重由战略原则层动态调整。

```
战略原则（Phase 1.5）                  战术规则（Phase 2）
─────────────────────                 ──────────────────
"这局要把对手关了"  ───→ 权重修正 ───→  InterceptRule 权重 ↑
                                      ScoreRushRule 权重 ↑
                                      SpeedFirstRule 权重 ↓

"对手快把我们关了"  ───→ 权重修正 ───→  SpeedFirstRule 权重 ↑
                                      InterceptRule 权重 ↓
                                      SafePlayRule 权重 ↑
```

#### 3.4.1 战略原则 — 全局目标控制器

战略原则不直接选牌，而是做**元控制**：根据全局局势，产出一组战术规则权重修正系数。一个基本原则可以同时影响多条战术规则，同一个局面可以有多条战略原则同时激活（权重修正叠加）。

##### 基类

```python
class StrategicPrinciple(ABC):
    """战略原则的抽象基类——判断全局局势，修正战术规则权重"""

    name: str                    # "guan_ren"、"survive"
    description: str             # 调试用
    category: str                # "goal" | "danger_response" | "phase_transition"

    @abstractmethod
    def assess(self, analysis: SharedAnalysis) -> Optional[StrategicContext]:
        """评估当前全局局势。返回 None 表示这条原则当前未激活。"""
```

##### 原则类型

| 类型 | 含义 | 激活时机 | 示例 |
|------|------|---------|------|
| `goal` | 目标型 | 当关人/大分差等战略窗口打开时激活 | 关人原则、最大化得分 |
| `danger_response` | 危险响应型 | 当局势出现危险时紧急激活 | 防止被关、落后追赶 |
| `phase_transition` | 阶段转换型 | 牌局进入不同阶段（开局/中局/残局）时激活 | 残局策略切换 |

##### 具体原则示例

```python
# src/agents/principles/guan_ren.py
class GuanRenPrinciple(StrategicPrinciple):
    """关人原则：目标是不让任何一个对手出完牌——关人能拿满分"""
    name = "guan_ren"
    category = "goal"

    def assess(self, analysis):
        opp_finished = analysis.opp_finished_count
        our_finished = analysis.red_finished_count

        if opp_finished == 0 and our_finished >= 1:
            # 关人窗口打开：我方已有人出完，对手一个都没出完
            return StrategicContext(
                primary_goal = "guan_ren",
                goal_urgency = min(1.0, (6 - analysis.opp_min_remaining) / 6),
                rule_weight_modifiers = {
                    "score_rush":       +0.5,   # 抢分——关人能拿对方所有剩余分
                    "intercept":        +0.4,   # 拦截对手——不让对手出完
                    "speed_first":      -0.6,   # 自己先出完不是目标
                    "safe_play":        -0.4,   # 关人需要承受一定风险
                    "friendly_fire":    +0.3,   # 更不能误伤队友
                    "delay_bomb":       -0.5,   # 有炸弹就用，别留
                },
                reasoning = "关人窗口打开：红方已有人出完，非红方无人出完"
            )
        return None  # 未激活


# src/agents/principles/avoid_being_guaned.py
class AvoidBeingGuanedPrinciple(StrategicPrinciple):
    """生存原则：不让对手把己方关了"""
    name = "avoid_being_guaned"
    category = "danger_response"

    def assess(self, analysis):
        our_finished = analysis.red_finished_count
        opp_finished = analysis.opp_finished_count

        if our_finished == 0 and opp_finished >= 1:
            # 危险：对手有人出完了，我方一个都没有
            return StrategicContext(
                primary_goal = "avoid_being_guaned",
                goal_urgency = min(1.0, (6 - analysis.our_min_remaining) / 6),
                rule_weight_modifiers = {
                    "speed_first":      +0.8,   # 必须尽快出完一个人，破关
                    "safe_play":        +0.6,   # 别冒险送分给对手
                    "intercept":        -0.3,   # 保留炸弹——炸弹用于破关
                    "score_rush":       -0.2,   # 不争分，先保命
                    "identity_protect": +0.3,   # 别暴露身份引来集火
                    "delay_bomb":       +0.2,   # 炸弹留到必须用时
                },
                reasoning = "生存模式：对手已有人出完，我方必须尽快出完一人破关"
            )
        return None
```

##### 多条原则叠加

同一个局面可能同时触发多条战略原则。权重修正系数线性叠加，Clamp 到 [0, 3.0]：

```
局面：我方 1 人出完，对手 0 人出完，分差 -50（落后）

GuanRenPrinciple 激活：
  score_rush: +0.5, intercept: +0.4, speed_first: -0.6

ComebackPrinciple 也激活（落后追赶）：
  score_rush: +0.3, safe_play: -0.3

叠加后：
  score_rush: 1.0 + 0.5 + 0.3 = 1.8
  intercept:  0.8 + 0.4      = 1.2
  speed_first: 1.0 - 0.6     = 0.4
  safe_play:  0.7 - 0.3      = 0.4
```

#### 3.4.2 战术规则 — 独立、可插拔的出牌打分单元

战术规则是整个系统**最底层的决策知识**。每条规则是一个独立类，只做一件事：给候选出牌打分。

#### 设计原则

1. **一条规则一个文件**：加新策略不改已有代码，只加文件
2. **统一签名**：`score(move, analysis) -> float`，[-1, 1] 区间
3. **分类归属**：每条规则声明自己的类别，倡导者按类别加载
4. **权重可配**：人格配置可以覆写任何规则的默认权重，设为 0 即关闭
5. **无相互依赖**：规则之间互不知晓，通过倡导者汇总时自然竞争

#### 基类

```python
class StrategyRule(ABC):
    """策略规则的抽象基类——每一条规则只做一件事"""
    name: str           # "intercept"、"friendly_fire"
    description: str    # 调试用，如 "对手快出完时，炸弹必须出手"
    category: str       # "offensive" | "defensive" | "teamwork" | "timing"
    default_weight: float  # 默认权重 [0, 2]，被人格配置覆写

    @abstractmethod
    def score(self, move: Move, analysis: SharedAnalysis) -> float:
        """给一个候选出牌打分 [-1, 1]。正分 = 倾向选它，负分 = 倾向避它，0 = 不表态"""
```

#### 规则分类体系

| 类别 | 含义 | 由哪个倡导者默认加载 | 示例 |
|------|------|---------------------|------|
| `offensive` | 进攻类——抢分、压制、炸弹 | BullishResearcher | InterceptRule, ScoreRushRule |
| `defensive` | 防御类——自保、藏身份、避送分 | BearishResearcher | IdentityProtectRule, SafePlayRule |
| `teamwork` | 配合类——援护、喂牌、解围 | BearishResearcher（配合型人格时双方都加载） | FriendlyFireRule, HelpTeammateRule |
| `timing` | 时机类——早出/晚出/留牌 | 双方都加载 | DelayBombRule, LastActRule |

#### 具体规则示例

```python
# src/agents/rules/intercept.py
class InterceptRule(StrategyRule):
    """对手快出完时，炸弹必须出手"""
    name = "intercept"
    category = "offensive"
    default_weight = 0.8

    def score(self, move, analysis):
        if not move.is_bomb():
            return 0
        urgent = any(cnt <= 2 for cnt in analysis.opp_hand_counts)
        return 1.0 if urgent else 0


# src/agents/rules/friendly_fire.py
class FriendlyFireRule(StrategyRule):
    """当前最佳出牌人是队友 → 不出炸弹压制"""
    name = "friendly_fire"
    category = "teamwork"
    default_weight = 1.0

    def score(self, move, analysis):
        if not move.is_bomb():
            return 0
        if analysis.trick_leader_team == analysis.my_team:
            return -1.0  # 强烈反对
        return 0


# src/agents/rules/identity_protect.py
class IdentityProtectRule(StrategyRule):
    """队友未亮明前，避免出含红十的牌型暴露身份"""
    name = "identity_protect"
    category = "defensive"
    default_weight = 1.0

    def score(self, move, analysis):
        if analysis.red_ten_status == "all_hidden":
            if any(c.is_red_ten() for c in move.cards):
                return -0.8
        return 0


# src/agents/rules/safe_play.py
class SafePlayRule(StrategyRule):
    """出分牌时评估对手是否能压过——有未出炸弹时降权"""
    name = "safe_play"
    category = "defensive"
    default_weight = 0.7

    def score(self, move, analysis):
        score_value = sum(c.score_value() for c in move.cards)
        if score_value > 0 and analysis.bombs_visible_remaining > 0:
            return -0.3 * (score_value / 10)  # 分越高越危险
        return 0


# src/agents/rules/last_act.py
class LastActRule(StrategyRule):
    """末位策略：最后行动且当前最佳是队友 → PASS"""
    name = "last_act"
    category = "timing"
    default_weight = 1.0

    def score(self, move, analysis):
        if not analysis.is_last_to_act:
            return 0
        if analysis.trick_leader_team == analysis.my_team:
            return 1.0 if move.is_pass() else -0.5
        return 0
```

#### 加新规则 = 加一个文件 + 更新配置

```
新增前:
  src/agents/rules/
    ├── intercept.py
    ├── friendly_fire.py
    ├── identity_protect.py
    ├── safe_play.py
    ├── last_act.py
    └── ...

新增后:
  src/agents/rules/
    ├── intercept.py
    ├── friendly_fire.py
    ├── identity_protect.py
    ├── safe_play.py
    ├── last_act.py
    ├── bait_and_switch.py   ← 新增，不改任何已有文件
    └── ...
```

然后在人格配置里加一行：

```python
# src/personalities/hybrid.py
HYBRID_CONFIG = PersonalityConfig(
    name = "诡变型",
    rules = {
        # 已有规则
        "intercept": 0.9,
        "friendly_fire": 0.7,
        # 新规则——一行启用
        "bait_and_switch": 1.2,  # 诡变型核心策略
    },
)
```

不改规则代码、不改倡导者代码、不改分析师代码。

### 3.5 倡导者 Agent — 规则执行器 + 辩论者

倡导者不再直接包含策略逻辑，而是成为**规则执行器和汇总器**。其职责是：
1. 从注册表加载人格配置指定的规则及覆写权重
2. 对每个 `legal_move` 执行所有规则的打分
3. 汇总结果，生成一个方向性的 `ResearcherOpinion`

```python
class BullishResearcher:
    """激进派倡导者"""

    def __init__(self, config: PersonalityConfig, registry: RuleRegistry):
        # 从注册表拿人格配置启用的、offensive 类规则（默认）
        # 也可以按人格配置精确指定哪些规则归属到 Bullish
        self.rules = registry.get_enabled(
            config.rules,
            categories=["offensive"],  # Bullish 默认加载进攻类
            include=["intercept", "score_rush", "speed_first"],  # 也加载指定规则
        )

    def evaluate(self, analysis: SharedAnalysis,
                 legal_moves: list[Move]) -> ResearcherOpinion:
        scores: dict[Move, float] = defaultdict(float)
        for move in legal_moves:
            for rule in self.rules:
                w = rule.effective_weight
                if w == 0:
                    continue
                scores[move] += rule.score(move, analysis) * w
        best_type = self._best_category(scores)
        return ResearcherOpinion(
            researcher_name="Bullish",
            preferred_category=best_type,
            must_avoid=self._must_avoid(scores),
            reasoning=self._explain(scores),
            confidence=self._confidence(scores),
        )
```

倡导者不直接出牌，而是针对候选出牌方向发表意见。每个倡导者生成一个 **ResearcherOpinion**：

```python
@dataclass
class ResearcherOpinion:
    researcher_name: str                        # "Bullish" / "Bearish" / "Wildcard"
    preferred_category: CardType                # 倾向的出牌类型
    preferred_rank_range: tuple[int, int]       # 倾向的 rank 范围
    must_avoid: list[CardType]                  # 必须避免的类型
    reasoning: str                              # 可读的论证（调试/回放用）
    confidence: float                           # [0, 1]
```

决策经理读取所有意见后，在 `legal_moves` 中筛选最符合倡导方向的出牌。

#### 倡导者类型

| 倡导者 | 策略方向 | 适用场景 |
|--------|----------|----------|
| **BullishResearcher** | 倾向出高分牌、炸弹，尽早清空手牌，喜欢争取得分 | 激进型、自私型 |
| **BearishResearcher** | 保留大牌、避免出红十暴露身份、宁可过牌也不冒险 | 保守型、配合型 |
| **WildcardResearcher** | 随机偏离最优出牌，偶尔出奇不意的牌型 | 诡诈型 |

#### 辩论流程（均衡型人格示例）

```
Round 1: Bullish 发表意见 → Bearish 反驳
Round 2: Bearish 发表修正意见 → Bullish 回应
LeadAgent: 阅读双方最终意见，在 legal_moves 中裁决
```

辩论轮数 `debate_rounds` 控制深度：
- `0` 轮 = 并行提交意见，不辩论，LeadAgent 直接综合
- `1` 轮 = 各自发表，不反驳
- `2` 轮 = 发表 + 一轮反驳
- `3` 轮 = 充分辩论

### 3.6 决策经理 (LeadAgent)

沿用 TradingAgents 命名，LeadAgent 负责将倡导者的抽象意见映射到具体的 `legal_moves`：

```python
class LeadAgent:
    def choose(
        self,
        state: GameState,
        legal_moves: list[Move],
        analysis: SharedAnalysis,
        context: Optional[StrategicContext],   # 战略原则层的输出
        opinions: list[ResearcherOpinion],
    ) -> Move:
        # 1. 根据意见（已含战略修正后的战术规则权重）计算每个候选 move 的得分
        # 2. 现有 AI（规则/搜索/ML）提供基线评分
        # 3. 综合基线 + 意见权重 → 最终选择
        # 4. 可选：context.goal_urgency 调整 w_base 和 w_opinion 的配比
```

**关键设计**：LeadAgent 可以使用现有的三种 AI 引擎作为基线：
- **规则型基线**：`RuleBasedPlayer.choose_action()` 的结果作为默认选择
- **搜索型基线**：`SearchPlayer.evaluate()` 的评分作为基线分数
- **ML型基线**：`MLPlayer` 的神经网络输出作为基线分数

倡导者的意见作为**偏差项**叠加到基线分数上，调整不同人格的倾向。

### 3.7 审核者 (Validator)

```python
class Validator:
    def validate(self, move: Move, legal_moves: list[Move]) -> Move:
        """检查出牌合法性，拦截明显错误。路径 A 主要防 bug，路径 B 防 LLM 越权"""
        if move not in legal_moves:
            # 回退到合法出牌中评分最高的
            return self._fallback(legal_moves)
        return move
```

### 3.8 得分融合公式

```
final_score(move) = w_base × baseline_score(move)
                  + w_opinion × sum(researcher_i.score(move) × researcher_i.confidence)
                  + w_random × ε                    (仅 Wildcard 人格, ε ~ U(0, 1))
```

| 参数 | 激进型 | 保守型 | 均衡型 | 诡诈型 | 配合型 | 自私型 |
|------|--------|--------|--------|--------|--------|--------|
| `w_base` | 0.30 | 0.30 | 0.40 | 0.20 | 0.35 | 0.25 |
| `w_opinion` | 0.70 (Bullish) | 0.70 (Bearish) | 0.60 (Bullish+Bearish) | 0.60 | 0.50 | 0.55 |
| `w_random` | 0 | 0 | 0 | 0.20 | 0 | 0 |
| `w_team` | — | — | — | — | 0.15 | — |
| `debate_rounds` | 0 | 0 | 2 | 1 | 2 | 0 |

## 4. 人格系统

### 4.1 六种人格

| 人格 | Agent 组合 | 行为描述 |
|------|-----------|----------|
| **激进型** Aggressive | 5 分析师 + Bullish 独裁 + Validator | 不惜代价抢大贡，出炸弹不犹豫，对手领牌时喜欢压制。无保守掣肘。 |
| **保守型** Conservative | 5 分析师 + Bearish 独裁 + Validator | 谨慎出牌，保留大牌，宁可过牌也不冒险。避免出红十暴露身份。 |
| **均衡型** Balanced | 5 分析师 + Bullish/Bearish 辩论 + Validator | 正反方充分辩论后裁决。大多数局面的稳健选择。 |
| **诡诈型** Tricky | 5 分析师 + Bullish + Wildcard + Validator | 随机偏离最优解，偶尔出奇牌（假炸弹、保留好牌出差的），对手难读。 |
| **配合型** Cooperative | 5 分析师 + Bullish/Bearish + TeamAnalyst 高权重 + Validator | 优先喂队友、解围同伴、助攻队友先出完。团队利益优先。 |
| **自私型** Selfish | 5 分析师 + Bullish + RiskAnalyst 低权重 + Validator | 个人得分优先，风险承受高，愿意为高分牌冒险。团队协作弱。 |

### 4.2 人格配置

```python
@dataclass
class PersonalityConfig:
    name: str
    active_analysts: list[str]                  # 活跃分析师列表
    active_researchers: list[str]               # 活跃倡导者列表
    debate_rounds: int                          # 辩论轮数
    w_base: float                               # 基线权重
    w_opinion: float                            # 意见权重
    w_team: float                               # 团队协同权重
    w_random: float                             # 随机噪声权重
    researcher_weights: dict[str, float]        # 各倡导者意见权重分配
    analyst_weights: dict[str, float]           # 各分析师权重（影响 SharedAnalysis 加权读取）

    # 策略规则选择 + 权重覆写
    # key = 规则名（"intercept"、"friendly_fire" 等）
    # value = 覆写后的权重，None = 用规则默认权重，0 = 关闭该规则
    rules: dict[str, Optional[float]]
```

#### 激进型 vs 保守型的规则配置对比

```python
# src/personalities/aggressive.py
AGGRESSIVE_CONFIG = PersonalityConfig(
    name = "激进型",
    rules = {
        # 进攻类强化
        "intercept":        1.2,   # 更紧急才拦截 → 反而正向了激进型的炸牌偏好
        "score_rush":       1.3,   # 争分强化
        "speed_first":      1.5,   # 清空手牌优先
        # 防御类弱化或关闭
        "friendly_fire":    0.5,   # 友军识别弱化（不太在乎炸队友）
        "safe_play":        0.3,   # 安全出牌弱化
        "identity_protect": 0,     # 不保护身份——不怕暴露
        "delay_bomb":       0,     # 不延迟炸弹——有就炸
        # 时机类
        "last_act":         None,  # 末位策略用默认权重
    },
    debate_rounds = 0,              # 不辩论，Bullish 独裁
)

# src/personalities/conservative.py
CONSERVATIVE_CONFIG = PersonalityConfig(
    name = "保守型",
    rules = {
        # 防御类强化
        "identity_protect": 1.5,   # 身份保护强化
        "safe_play":        1.3,   # 安全出牌强化
        "friendly_fire":    1.2,   # 友军识别强化
        "delay_bomb":       1.0,   # 保留炸弹
        # 进攻类弱化
        "intercept":        0.6,   # 拦截弱化（需要更紧急才出手）
        "score_rush":       0.3,
        "speed_first":      0.2,
        # 时机类
        "last_act":         None,  # 末位策略用默认权重
    },
    debate_rounds = 0,              # 不辩论，Bearish 独裁
)
```

## 5. 文件结构

```
src/
├── agents/
│   ├── __init__.py
│   ├── base_agent.py          # BaseAgent 抽象基类 + AgentMode 枚举
│   ├── brain.py               # MultiAgentBrain — 对外的 choose_action() 入口
│   ├── shared_analysis.py     # SharedAnalysis 数据结构
│   ├── analysts/
│   │   ├── __init__.py
│   │   ├── hand.py            # HandAnalyst 手牌分析师
│   │   ├── position.py        # PositionAnalyst 位置分析师
│   │   ├── team.py            # TeamAnalyst 队伍分析师
│   │   ├── opponent.py        # OpponentAnalyst 对手分析师
│   │   └── risk.py            # RiskAnalyst 风险分析师
│   ├── rules/                 # ★ 战术规则层（独立、可插拔）
│   │   ├── __init__.py
│   │   ├── base.py            # StrategyRule 抽象基类 + RuleRegistry 注册表
│   │   ├── intercept.py       # 拦截规则
│   │   ├── friendly_fire.py   # 友军识别
│   │   ├── identity_protect.py # 身份保护
│   │   ├── safe_play.py       # 安全出牌
│   │   ├── last_act.py        # 末位策略
│   │   ├── help_teammate.py   # 解围规则
│   │   ├── score_rush.py      # 争分规则
│   │   ├── speed_first.py     # 清空优先
│   │   └── delay_bomb.py      # 保留炸弹
│   ├── principles/            # ★ 战略原则层（全局目标控制）
│   │   ├── __init__.py
│   │   ├── base.py            # StrategicPrinciple 基类 + StrategyDirector
│   │   ├── guan_ren.py        # 关人原则
│   │   ├── avoid_being_guaned.py  # 生存原则
│   │   └── ...                # 未来扩展
│   ├── researchers/
│   │   ├── __init__.py
│   │   ├── base.py            # ResearcherOpinion, ReseracherBase
│   │   ├── bullish.py         # BullishResearcher — 加载 offensive 类规则
│   │   ├── bearish.py         # BearishResearcher — 加载 defensive 类规则
│   │   └── wildcard.py        # WildcardResearcher — 随机扰动
│   ├── lead_agent.py          # LeadAgent 决策经理
│   └── validator.py           # Validator 审核者
├── personalities/
│   ├── __init__.py
│   ├── base.py                # PersonalityConfig 人格配置基类
│   ├── aggressive.py          # 激进型人格
│   ├── conservative.py        # 保守型人格
│   ├── balanced.py            # 均衡型人格
│   ├── tricky.py              # 诡诈型人格
│   ├── cooperative.py         # 配合型人格
│   └── selfish.py             # 自私型人格
├── decision_logger.py         # 决策日志记录（~/.redten/decisions/）
└── session.py                 # make_players() 新增 multi_agent tier
```

## 6. 实现阶段

### Phase 1: 基础设施（基础框架搭建，< 400 行）

- [ ] `SharedAnalysis` 数据结构（含全部分析字段）
- [ ] `ResearcherOpinion` 数据结构
- [ ] `StrategyRule` 抽象基类 + `RuleRegistry` 注册表
- [ ] `BaseAgent` 抽象基类 + `AgentMode` 枚举
- [ ] `PersonalityConfig` — 含规则选择、权重覆写、辩论配置
- [ ] `MultiAgentBrain` 骨架 — 串联 5 阶段的流水线

### Phase 2: 分析师实现（纯规则，无 AI 依赖）

- [ ] `HandAnalyst` — 自身手牌结构、炸弹、危险牌
- [ ] `PositionAnalyst` — 基于 `turn_order` 和 `current_trick` 分析位置
- [ ] `TeamAnalyst` — 包装现有 `IdentityTracker`
- [ ] `OpponentAnalyst` — 基于 `played_cards` 计算剩余牌分布和对手风格
- [ ] `RiskAnalyst` — 综合前 4 个分析结果评估风险

此阶段可验证共享分析是否正确填充。

### Phase 3: 战略原则实现（3 条原则，< 120 行）

- [ ] `StrategicPrinciple` 基类 + `StrategyDirector` — 执行活跃原则，合并权重修正
- [ ] `GuanRenPrinciple` — 关人窗口打开时：强化抢分/拦截，弱化自清空
- [ ] `AvoidBeingGuanedPrinciple` — 被关风险时：强化清空/安全，弱化争分
- [ ] 人格可以单独调整每条原则的响应强度

### Phase 4: 战术规则实现（P0 → P3 分批）

#### P0 — 消除最愚蠢的错误（4 条规则，< 80 行）

- [ ] `InterceptRule` — 对手快出完 → 炸弹拦截
- [ ] `FriendlyFireRule` — 领先是队友 → 不炸自己人
- [ ] `LastActRule` — 末位 + 队友领先 → PASS
- [ ] `SafePlayRule` — 有未出炸弹 → 大分牌谨慎

#### P1 — 身份与时机（3 条规则，< 60 行）

- [ ] `IdentityProtectRule` — 队友未亮 → 藏红十
- [ ] `HelpTeammateRule` — 队友被压 → 解围
- [ ] `DelayBombRule` — 手牌多时保留炸弹

#### P2 — 争分与速度（2 条规则，< 50 行）

- [ ] `ScoreRushRule` — 机会难得 → 抢分
- [ ] `SpeedFirstRule` — 手牌多 → 大牌优先清空

#### P3 — 高级策略（按需扩展）

- [ ] 假动作、诱导、跨局对手建模等

每条规则独立开发和单元测试。加新规则只加文件，不改已有代码。

### Phase 5: 倡导者实现（规则执行器）

- [ ] `ResearcherBase` — 读取 `SharedAnalysis` + `StrategicContext`（修正后的权重）+ 执行规则集，输出 `ResearcherOpinion`
- [ ] `BullishResearcher` — 加载 offensive 类规则，规则权重由战略原则动态修正
- [ ] `BearishResearcher` — 加载 defensive 类规则，规则权重由战略原则动态修正
- [ ] `WildcardResearcher` — 随机扰动
- [ ] 辩论流程实现（多轮反驳）

此阶段依赖 Phase 3（战略原则）和 Phase 4（战术规则）已就位。战略原则修正后的权重通过 `StrategicContext` 传入。

### Phase 6: 决策层（LeadAgent + Validator）

- [ ] `LeadAgent` — 实现得分融合公式
- [ ] 接入 `RuleBasedPlayer` 作为基线
- [ ] 接入 `SearchPlayer.evaluate()` 作为基线
- [ ] 接入 `MLPlayer` 神经网络作为基线
- [ ] `Validator` — 合法性兜底检查

### Phase 7: 人格化配置 + 集成

- [ ] 6 种人格配置文件（选择规则 + 调权重）
- [ ] `make_players(tier="personalities")` 集成到 `session.py`
- [ ] 6 个玩家可以各自独立配置人格
- [ ] `DecisionLogger` 决策日志系统

### Phase 8: LLM 增强（可选）

- [ ] 将分析师替换为 LLM 调用（Claude API），输出自然语言分析
- [ ] 将倡导者替换为 LLM 辩论
- [ ] Validator 的 LLM 路径需更严格的合法性检查

## 7. 与 TradingAgents 的对应关系

| TradingAgents | 红十多智能体 AI |
|---|---|
| Fundamentals Analyst | HandAnalyst |
| Sentiment Analyst | TeamAnalyst |
| Technical Analyst | OpponentAnalyst |
| — | PositionAnalyst（新增，红十特有） |
| News Analyst | RiskAnalyst |
| — | **StrategyDirector（新增，战略原则层）** — 评估全局局势，修正战术规则权重 |
| Bullish Researcher | BullishResearcher |
| Bearish Researcher | BearishResearcher |
| — | WildcardResearcher（新增，诡诈型） |
| Trader | LeadAgent |
| Risk Management + Portfolio Manager | **战略原则**执行风险管控 + Validator 审核 |
| Aggressive / Conservative / Neutral | 6 种人格（激进/保守/均衡/诡诈/配合/自私） |
| 两级 LLM（快/深） | 分析师（规则）+ 决策层（现有 AI Tier），LLM 路径 B 预留 |
| `AgentState` 共享状态 | `SharedAnalysis` + `StrategicContext` |
| `max_debate_rounds` | `debate_rounds` 人格参数 |
| 记忆 + BM25 检索 | Phase 8 可选：跨局对手建模 |

## 8. 非 LLM 实现路径

TradingAgents 依赖 LLM 生成分析报告和辩论内容。本架构设计为**规则优先**：

- 分析师用**规则函数**实现（统计计数、概率估算），不需要 LLM
- 倡导者用**启发式评分**实现（偏好函数 + 权重），不需要 LLM
- LeadAgent 用**现有 AI 引擎**（规则/搜索/ML）作为基线

**未来可选 LLM 增强**：将分析师和倡导者替换为 LLM 调用（例如 Claude API），可获得自然语言推理和更细腻的策略表达。架构已为此预留接口：分析师和倡导者都通过 `BaseAgent.mode` 字段在 `AgentMode.RULE_BASED` 和 `AgentMode.LLM_BASED` 之间切换。

## 9. 示例：激进型 vs 保守型在同一局面下的决策

```
GameState: 我是 P0，共6张手牌（4张Q、单张A、单张3）。P3 领牌（出单张K）。
          我已确认是红方。P2 也是红方。当前最佳是 P3 的单张K。
          对手 P3 手牌只剩 4 张（OpponentAnalyst 追踪）。

Phase 1 — 分析 (5 分析师):
  HandAnalyst:     我有 4张Q炸弹。手牌质量 0.72。
  PositionAnalyst: 我在本轮第 2 个出牌，P1/P4/P5 在我之后
  TeamAnalyst:     P2 是队友 (P=1.0)，P3 是确认对手。当前领先者是 P3(对手)
  OpponentAnalyst: P3 手牌只剩 4 张。剩余分牌价值 45。
  RiskAnalyst:     暴露风险 0.1（我不出红十牌型），局势优势 0.3

Phase 2 — 规则打分 (每种合法出牌 × 每条规则):

  激进型人格（rules = {intercept:1.2, friendly_fire:0.5, safe_play:0.3, identity_protect:0, ...}）:

    对 BOMB_Q:
      InterceptRule(P3剩4张≤6→不触发)        →  0
      FriendlyFireRule(领先者P3是对手)        →  0
      IdentityProtectRule(已关闭, weight=0)   →  0
      SafePlayRule(有未出炸弹→分牌降权)       →  0  (炸弹本身不是分牌)
      ScoreRushRule(炸弹压制可抢分)           → +0.7 × 1.3 = +0.91
      SpeedFirstRule(出炸弹清4张加速)         → +0.6 × 1.5 = +0.90
      → Bullish 汇总: +1.81

    对 PASS:
      InterceptRule                          →  0
      ScoreRushRule(PASS不抢分)              → -0.5 × 1.3 = -0.65
      SpeedFirstRule(PASS不清手牌)           → -0.3 × 1.5 = -0.45
      → Bullish 汇总: -1.10

    → BullishOpinion: preferred=BOMB, confidence=0.62

  保守型人格（rules = {identity_protect:1.5, safe_play:1.3, friendly_fire:1.2, ...}）:

    同样局面，BearishResearcher 加载 defensive 类规则:

    对 BOMB_Q:
      FriendlyFireRule(领先者是对手)          →  0
      IdentityProtectRule(炸弹不含红十)       →  0
      DelayBombRule(手牌仅6张，快出完了)     → -0.3 × 1.0 = -0.30
      SafePlayRule(炸弹非分牌)                →  0
      InterceptRule(P3剩4张不触发)            →  0
      ScoreRushRule(权重仅0.3)                → +0.7 × 0.3 = +0.21
      → Bearish 汇总: -0.09

    对 PASS:
      IdentityProtectRule                    →  0
      SafePlayRule(PASS不送分)               → +0.4 × 1.3 = +0.52
      DelayBombRule(PASS保留炸弹)            → +0.5 × 1.0 = +0.50
      LastActRule(不是末位)                   →  0
      → Bearish 汇总: +1.02

    → BearishOpinion: preferred=PASS, confidence=0.45

Phase 3 — 决策 (LeadAgent):
  激进型:
    基线(SearchPlayer): PASS=0.9, BOMB_Q=0.4
    融合: BOMB_Q = 0.30×0.4 + 0.70×1.81 = 1.387
          PASS    = 0.30×0.9 + 0.70×(-1.10) = -0.50
    → 出 4张Q炸弹 ✓

  保守型:
    基线(SearchPlayer): PASS=0.9, BOMB_Q=0.4
    融合: BOMB_Q = 0.30×0.4 + 0.70×(-0.09) = 0.057
          PASS    = 0.30×0.9 + 0.70×1.02  = 0.984
    → PASS ✓

Phase 4 — 审核:
  两者均通过 Validator。

最终: 同一局面，激进型出炸弹，保守型 PASS —— 人格差异由规则选择 + 权重驱动。
```

**关键观察**：激进型和保守型的差异不是硬编码的 if-else，而是**同一套规则、不同的权重和子集**。加一条新规则（比如 `TeammateSignalRule`）后，两个人格的行为会自动分化——不需要改各自的人格代码。

## 10. 测试策略

1. **单元测试**：每个分析师独立输入 → 验证输出字段
2. **人格差异测试**：同一局面 × 6 种人格 → 验证出牌不同
3. **胜率对比**：各人格 vs 规则型基线，打 1000 局统计胜率
4. **回放审查**：记录 `ResearcherOpinion.reasoning`，在回放器里展示 AI 当时的"思考"
5. **决策日志验证**：检查 `~/.redten/decisions/` 日志完整性，用于训练数据积累

## 11. 决策日志系统

```python
@dataclass
class DecisionLog:
    timestamp: str
    room_code: str
    hand_number: int
    trick_number: int
    player: int
    personality: str
    game_state_snapshot: dict
    shared_analysis: SharedAnalysis
    researcher_opinions: list[ResearcherOpinion]
    baseline_scores: dict[int, float]          # move_idx → baseline_score
    fusion_scores: dict[int, float]            # move_idx → final_score
    chosen_move: Move
    was_validated: bool
```

日志写入 `~/.redten/decisions/{room_code}_{timestamp}.jsonl`，每行一条决策记录。用于：
- 离线分析不同人格的决策质量
- 训练 ML 模型（作为特征工程输入）
- 回放器展示 AI "思考过程"

## 12. 策略描述模板

战术规则和战略原则使用不同的模板——前者描述「怎么出一手牌」，后者描述「这一局要什么」。

### 12.1 战略原则描述模板

新增战略原则时按以下模板提交。

```markdown
### 原则名称（英文 slug）—— 一句话中文概括

**类型**： goal / danger_response / phase_transition（三选一）

**问题描述**：
AI 在什么全局局面下没有做出正确的战略判断？（1-3 句）

**激活条件**（用 SharedAnalysis 字段表达）：
- 条件 1：`SharedAnalysis.xxx` 满足什么
- 条件 2：`SharedAnalysis.yyy` 满足什么
- （如有多条，全部列出。AND / OR 关系明确标注）
- 示例：`opp_finished == 0 AND our_finished >= 1`（关人窗口打开）

**反激活条件**：
- 什么状态下这条原则应该退出？如果不写，默认为「激活条件不再满足时退出」

**战术规则权重修正**：

| 规则 | 修正量 | 理由 |
|------|--------|------|
| score_rush | +0.5 | 关人需要抢分 |
| speed_first | -0.6 | 个人出完不重要 |
| intercept | +0.4 | 必须阻止对手出完 |
| ... | ... | ... |

- 修正量范围 [-2.0, +2.0]，叠加后 Clamp 到 [0, 3.0]
- 只列会被修正的规则，不影响的不用列

**各人格响应强度**：

| 人格 | 强度 | 理由 |
|------|------|------|
| 激进型 | | |
| 保守型 | | |
| 均衡型 | | |
| 诡诈型 | | |
| 配合型 | | |
| 自私型 | | |

- 强度 = 人格对该原则的敏感度乘数：1.0 = 标准响应，<1.0 = 迟钝，>1.0 = 敏感
- 例如保守型对 GuanRenPrinciple 强度 0.6：关人窗口打开时保守型调整幅度比均衡型小

**正例**（触发原则的局面）：
- 描述一个具体的全局局面，说明原则应该激活

**反例**（不应触发的局面）：
- 描述一个相似但不应激活原则的局面，说明边界条件

**与现有原则/规则的关系**：
- 这条战略原则和哪些战术规则 / 其他战略原则有交互
- 如果有竞争，优先级如何
```

### 12.2 战术规则描述模板

新增战术规则时按以下模板提交。每个字段直接对应代码结构。

#### 模板

```markdown
### 规则名称（英文 slug）—— 一句话中文概括

**分类**： offensive / defensive / teamwork / timing（四选一）

**问题描述**：
AI 目前在什么局面下犯了什么错误？（1-3 句）

**触发条件**（用 SharedAnalysis 字段表达）：
- 条件 1：`SharedAnalysis.xxx` 满足什么
- 条件 2：`SharedAnalysis.yyy` 满足什么
- （如有多条，全部列出。AND / OR 关系明确标注）

**打分逻辑**：

| 候选出牌类型 | 条件组合 | 打分 | 解释 |
|-------------|---------|------|------|
| 炸弹 | 触发条件满足 | +1.0 | 强烈倾向 |
| PASS | 触发条件满足 | -0.5 | 不建议 |
| 其他 | — | 0 | 不表态 |

- 打分范围 [-1.0, 1.0]：正分 = 倾向出，负分 = 倾向避，0 = 不表态
- 可以给不同类型的牌打不同分（如对炸弹打 +0.8，对单张打 -0.3）

**默认权重**： `0.0 ~ 2.0`（ 1.0 = 标准，>1.0 = 这条规则影响力大，<1.0 = 参考性的 ）

**各人格建议权重**：

| 人格 | 权重 | 理由 |
|------|------|------|
| 激进型 | | |
| 保守型 | | |
| 均衡型 | | |
| 诡诈型 | | |
| 配合型 | | |
| 自私型 | | |

**正例**（触发规则的局面）：
- 描述一个具体局面，说明规则应该触发并影响出牌

**反例**（不应触发的局面）：
- 描述一个相似但不应触发规则的局面，说明边界条件

**与现有规则的关系**：
- 互补 / 竞争 / 无关联
- 如果是竞争关系，哪个优先级应更高
```

### 填写示例

以下用一条已讨论的规则演示如何填写模板：

---

### teammate_signal_rule —— 队友暗号识别：出队友容易接的牌型

**分类**： teamwork

**问题描述**：
当前 AI 不会根据队友的出牌信号调整自己的出牌策略。队友出了对子向我示意，我却出了一张刁钻的单牌，队友接不住，浪费了配合机会。

**触发条件**（用 SharedAnalysis 字段表达）：
- 条件 1：`SharedAnalysis.teammate_needs_help` 包含当前被压制的队友（AND）
- 条件 2：`SharedAnalysis.likely_teammates[p] > 0.5`，至少有一个确认或高概率队友（AND）
- 条件 3：`SharedAnalysis.is_last_to_act == False`，我不是末位（末位逻辑由 LastActRule 处理）

**打分逻辑**：

| 候选出牌类型 | 条件组合 | 打分 | 解释 |
|-------------|---------|------|------|
| 与队友最近出牌同类型（对子跟对子、单张跟单张） | 全部触发条件满足 | +0.6 | 出队友能接的牌型 |
| PASS | 非末位 + 队友被压 | -0.4 | 不出牌帮队友 |
| 炸弹 | 对手压制了队友 | +0.8 | 直接解围比喂牌更好 |
| 与队友出牌类型不同的低牌 | 触发条件满足 | -0.3 | 刁钻出牌不利于配合 |

**默认权重**： `1.0`

**各人格建议权重**：

| 人格 | 权重 | 理由 |
|------|------|------|
| 激进型 | 0.3 | 不重视配合，优先自己的进攻节奏 |
| 保守型 | 0.8 | 团队稳定优先 |
| 均衡型 | 1.0 | 标准权重 |
| 诡诈型 | 0.5 → 1.2（随机波动） | 有时配合有时故意反向，不可预测 |
| 配合型 | 1.5 | 核心策略，队友信号高度敏感 |
| 自私型 | 0.1 | 几乎不关心队友信号 |

**正例**（触发规则的局面）：
P2（队友）领牌出对子 88，P3（对手）出对子 QQ 压制。我是 P4，手里有对子 JJ 也有单张 A。规则应为对子 JJ 打正分，单张 A 打负分。出对子 JJ 帮队友反压。

**反例**（不应触发的局面）：
我是末位，P2（队友）的对子被 P3 压制。LastActRule 已处理末位逻辑（P3 是对手不能 PASS），本条规则不覆盖此场景。或者 `likely_teammates[p2] < 0.3`，我不确定 P2 是不是队友，不应触发配合。

**与现有规则的关系**：
- 与 `FriendlyFireRule` 互补——FriendlyFire 管「不对队友开枪」，我管「帮队友打对手」
- 与 `LastActRule` 有场景分叉——末位情景由 LastActRule 裁决，本规则退让
- 与 `SpeedFirstRule` 有潜在竞争——配合可能会牺牲清牌速度。配合型人格这两种规则权重大致相当，由具体得分竞争

---

### 使用说明

1. **提新策略时**：复制模板的 markdown 部分，逐项填写。
2. **不需要填写的项**：写「无」或留空，不用编造。
3. **打分不确定时**：给区间即可（如 "+0.5 ~ +0.8"），我帮你细化。
4. **模板本身不要求完美**——触发条件可以用自然语言描述，我来翻译成 `SharedAnalysis` 字段。

## 13. 策略清单

### 13.1 战略原则

战略原则不指导具体出牌，而是根据全局局势动态修正下游战术规则的权重。

| # | 名称 | slug | 类型 | 状态 | 核心逻辑 |
|---|------|------|------|------|---------|
| S1 | **关人原则** | `guan_ren` | `goal` | ✅ 完整设计 | 我方已有人出完 + 对手无人出完 → 强化拦截/抢分，弱化自清空 |
| S2 | **生存原则** | `avoid_being_guaned` | `danger_response` | ✅ 完整设计 | 对手已有人出完 + 我方无人出完 → 强化清空/安全，弱化争分 |
| S3 | **落后追赶** | `comeback` | `danger_response` | 🔲 概念 | 分差较大且落后 → 强化抢分，弱化安全（敢于冒险） |
| S4 | **最大化得分** | `max_score` | `goal` | 🔲 概念 | 分差接近、牌局末期 → 出分牌优先，不为清空牺牲分值 |
| S5 | **残局策略** | `endgame` | `phase_transition` | 🔲 概念 | 全局剩余总牌数低于阈值 → 切换节奏（具体行为待定） |

**状态说明**：✅ = 有完整代码设计和权重修正表，可直接实现。🔲 = 仅概念提及，待细化。

#### 战略原则 → 战术规则权重修正速查

| 原则 | score_rush | intercept | speed_first | safe_play | friendly_fire | identity_protect | delay_bomb |
|------|-----------|-----------|-------------|-----------|---------------|-----------------|------------|
| S1 关人 | **+0.5** | **+0.4** | −0.6 | −0.4 | +0.3 | — | −0.5 |
| S2 生存 | −0.2 | **+0.4** | **+0.8** | **+0.6** | — | +0.3 | **−0.4** |
| S3 追赶 | +0.3 | — | — | −0.3 | — | — | — |
| S4 最大分 | +0.4 | — | −0.3 | −0.2 | — | — | — |
| S5 残局 | 待定 | 待定 | 待定 | 待定 | 待定 | 待定 | 待定 |

### 13.2 战术规则

战术规则给每个候选出牌打分，由倡导者加载执行。权重可被人格配置覆写，也可被战略原则动态修正。

#### P0 — 消除最愚蠢的错误

| # | 名称 | slug | 分类 | 状态 | 核心逻辑 |
|---|------|------|------|------|---------|
| T1 | **拦截规则** | `intercept` | offensive | ✅ 完整设计 | 有对手手牌 ≤ 2 张 → 炸弹 +1.0 |
| T2 | **友军识别** | `friendly_fire` | teamwork | ✅ 完整设计 | 当前最佳出牌人是队友 → 炸弹 −1.0 |
| T3 | **末位策略** | `last_act` | timing | ✅ 完整设计 | 我是末位 + 当前最佳是队友 → PASS +1.0，出牌 −0.5 |
| T4 | **安全出牌** | `safe_play` | defensive | ✅ 完整设计 | 有未出炸弹 + 我出高分牌 → 按分值比例扣分 |

#### P1 — 身份与时机

| # | 名称 | slug | 分类 | 状态 | 核心逻辑 |
|---|------|------|------|------|---------|
| T5 | **身份保护** | `identity_protect` | defensive | ✅ 完整设计 | 红十身份未明 + 出牌含红十 → −0.8 |
| T6 | **解围规则** | `help_teammate` | teamwork | 🔲 描述 | 队友被对手压制 → 能压过对手的牌型 +0.6 |
| T7 | **保留炸弹** | `delay_bomb` | timing | 🔲 描述 | 手牌 ≥ 12 张 + 非必须拦截 → 炸弹 −0.3，PASS +0.5 |

#### P2 — 争分与速度

| # | 名称 | slug | 分类 | 状态 | 核心逻辑 |
|---|------|------|------|------|---------|
| T8 | **争分规则** | `score_rush` | offensive | 🔲 描述 | 有机会抢到高分 → 高分牌型 +0.7 |
| T9 | **清空优先** | `speed_first` | offensive | 🔲 描述 | 手牌多 → 大牌优先 +0.6，PASS −0.3 |

#### P3+ — 概念阶段

| # | 名称 | slug | 分类 | 状态 | 核心逻辑 |
|---|------|------|------|------|---------|
| T10 | **假动作** | `bait_and_switch` | offensive | 🔲 概念 | 故意出弱牌诱导对手放松警惕，留大牌后续压制 |
| T11 | **跨局建模** | `opponent_model` | teamwork | 🔲 概念 | 跨局记录对手风格，预测其下一步行为 |

#### 模板示例

| # | 名称 | slug | 分类 | 状态 | 核心逻辑 |
|---|------|------|------|------|---------|
| — | **队友暗号识别** | `teammate_signal` | teamwork | 📋 示例 | 队友出了对子 → 跟同类型 +0.6，刁钻出牌 −0.3 |

#### 战术规则 → 人格默认权重速查

| 规则 | 默认 | 激进 | 保守 | 均衡 | 诡诈 | 配合 | 自私 |
|------|------|------|------|------|------|------|------|
| T1 拦截 | 0.8 | **1.2** | 0.6 | 0.8 | 0.8 | 0.8 | 1.0 |
| T2 友军识别 | 1.0 | 0.5 | **1.2** | 1.0 | 0.7 | **1.3** | 0.4 |
| T3 末位策略 | 1.0 | 0.8 | 1.0 | 1.0 | 0.6 | 1.0 | 0.8 |
| T4 安全出牌 | 0.7 | 0.3 | **1.3** | 0.7 | 0.5 | 0.8 | 0.2 |
| T5 身份保护 | 1.0 | 0 | **1.5** | 1.0 | 0.6 | 1.0 | 0.3 |
| T6 解围规则 | 0.8 | 0.6 | 0.8 | 0.8 | 0.5 | **1.2** | 0.3 |
| T7 保留炸弹 | 0.6 | 0 | 1.0 | 0.6 | 0.4 | 0.6 | 0.3 |
| T8 争分规则 | 0.8 | **1.3** | 0.3 | 0.8 | 0.7 | 0.6 | **1.2** |
| T9 清空优先 | 0.7 | **1.5** | 0.2 | 0.7 | 0.5 | 0.5 | 1.0 |

**状态说明**：
- ✅ 完整设计 = 含基类、`score()` 实现、默认权重，可直接写代码
- 🔲 描述 = 有文字描述和核心逻辑，待细化打分函数
- 🔲 概念 = 仅有方向和意图，需要进一步讨论触发条件和打分逻辑
- 📋 示例 = 为演示模板而写的示例规则，不纳入实现计划

**已实现 / 待实现统计**：
- 战略原则：2 ✅ / 3 🔲
- 战术规则：4 ✅ / 4 🔲 / 2 🔲概念 / 1 📋

## 14. MLP 值网络 — 多智能体自学习

### 14.1 问题

MultiAgentPlayer 和 MLPlayer 是两条平行线：

```
MultiAgentPlayer                          MLPlayer
───────────────                          ────────
Phase 1-3: 分析 + 战略 + 研究员          sample_world() 随机分配
Phase 4: LeadAgent                        simulate_trick() 模拟
  final = w_base × 启发式baseline        extract_features() → MLP → score
        + w_opinion × 研究员打分          选 argmax
        + w_random × 噪声
```

LeadAgent 的 `_baseline_score()` 是一个硬编码的启发式（BOMB=0.85, SINGLE=0.10, PASS=0.05），不随训练提高。而 MLPlayer 已经有一套成熟的自对弈训练管线（`train_selfplay.py`），能通过 10 轮自对弈从 47% 提升到 ~65% 胜率。

### 14.2 方案：MLP 嵌入 LeadAgent

用 MLP 值网络替换启发式 baseline。MLP 负责"这个局面有多好"（客观评估），研究员规则负责"按我的风格该不该打"（主观偏好）。

```
MLP 值网络（共享，持续训练）
    ↓ 提供客观局面评分
┌───────────────────────────────────────────┐
│  LeadAgent 融合                           │
│  final = w_base × MLP + w_opinion × 规则  │
│           ↑                    ↑          │
│      越训越强              保持个性差异    │
└───────────────────────────────────────────┘
```

**融合公式**（不变）：

```
final = w_base × baseline + w_opinion × Σ(researcher_score × confidence) + w_random × ε
```

当 MLP 可用时 `baseline = mlp_value_network(state_after_move)`；不可用时回退到启发式。

MLP 评分通过 min-max 归一化映射到 [0, 1]，与启发式 baseline 尺度对齐。

### 14.3 架构改动

```
MultiAgentBrain.__init__():
  + model_path: str | None = None     # 可选 MLP 模型路径
  + epsilon: float = 0.0              # ε-greedy 探索率
  + 如果 model_path 有效，加载 RedTenMLP

MultiAgentBrain._fuse_decision():
  + 创建 LeadAgent 时传入 model + p_red + player_id
  + 如 ε-greedy 触发，直接随机选 move（跳过管线）

LeadAgent.__init__():
  + model: RedTenMLP | None = None
  + n_mlp_samples: int = 12
  + p_red: list[float] | None = None
  + player_id: int = 0

LeadAgent.choose():
  + 如 model 存在: _mlp_baseline_scores(state, legal_moves)
  + 如 model 为空: _heuristic_baseline(move, analysis)  ← 旧逻辑不变

LeadAgent._mlp_baseline_scores():
  + 复用 MLPlayer 的 sample_world + simulate_trick + extract_features + MLP
  + min-max 归一化到 [0, 1]
  + 被 prune_candidates 剪掉的 move 得分 = 0

MultiAgentPlayer.__init__():
  + model_path: str | None = None
  + epsilon: float = 0.0
```

### 14.4 训练 6 种人格

```
Round 1:
  激进型(ε=0.4) vs 保守型+均衡型+... → 收集 (特征, 结果)
  保守型(ε=0.4) vs 激进型+均衡型+... → 收集 (特征, 结果)
  ...6种人格各自打500局...
  → 合并所有数据 → 训练共享 MLP → model_r1.pt

Round 2:
  用 model_r1.pt, ε=0.37 → 各自打500局 → 训练 → model_r2.pt
  ...

Round 10:
  ε衰减到0.1, MLP 已学会红十基础价值判断
  6种人格共用同一 MLP，但研究员权重不同 → 出牌风格分化
```

关键点：
- **MLP 共享** — 6 种人格的训练数据喂给同一个网络，学会红十通用价值判断
- **个性来自规则权重** — 激进型的 `speed_first=1.5`、保守型的 `identity_protect=1.5` 不变，在 MLP 基础上叠加
- **互相训练** — 每种人格与其他人格对战，MLP 学到应对不同风格的经验

### 14.5 新增 session tier

```
multi-agent-mlp         → 6× MultiAgentPlayer + MLP baseline
multi-agent-mlp-vs-rule → 3× MultiAgentPlayer(MLP) vs 3× RuleBasedPlayer
```

### 14.6 向后兼容

- 不传 `model_path` 时行为完全不变（回退到启发式 baseline）
- 已有 6 种人格配置不变
- 已有 benchmark tier 不受影响
