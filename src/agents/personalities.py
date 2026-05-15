"""
Six personality configurations for the multi-agent AI system.

Each personality is defined by:
  - Which researchers are active (bullish / bearish / wildcard)
  - Debate depth
  - Fusion weights (w_base, w_opinion, w_random, w_team)
  - Rule weight overrides (intercept, friendly_fire, etc.)
  - Principle intensity multipliers (guan_ren, avoid_being_guaned)

Rule weights: None = use default, 0.0 = disable, float = override.
Principle intensities: 1.0 = standard, 0 = disabled.
"""
from brain import PersonalityConfig

# ── 激进型 Aggressive ──────────────────────────────────────────────────────

AGGRESSIVE = PersonalityConfig(
    name="激进型",
    active_researchers=["bullish"],
    debate_rounds=0,
    w_base=0.30,
    w_opinion=0.70,
    w_random=0.0,
    researcher_weights={"bullish": 1.0},
    principle_intensities={"guan_ren": 1.2, "avoid_being_guaned": 0.6},
    rules={
        "intercept":        1.2,
        "friendly_fire":    0.5,
        "last_act":         0.8,
        "safe_play":        0.3,
        "identity_protect": 0.0,
        "help_teammate":    0.6,
        "delay_bomb":       0.0,
        "score_rush":       1.3,
        "speed_first":      1.5,
    },
)

# ── 保守型 Conservative ────────────────────────────────────────────────────

CONSERVATIVE = PersonalityConfig(
    name="保守型",
    active_researchers=["bearish"],
    debate_rounds=0,
    w_base=0.30,
    w_opinion=0.70,
    w_random=0.0,
    researcher_weights={"bearish": 1.0},
    principle_intensities={"guan_ren": 0.6, "avoid_being_guaned": 1.3},
    rules={
        "intercept":        0.6,
        "friendly_fire":    1.2,
        "last_act":         1.0,
        "safe_play":        1.3,
        "identity_protect": 1.5,
        "help_teammate":    0.8,
        "delay_bomb":       1.0,
        "score_rush":       0.3,
        "speed_first":      0.2,
    },
)

# ── 均衡型 Balanced ─────────────────────────────────────────────────────────

BALANCED = PersonalityConfig(
    name="均衡型",
    active_researchers=["bullish", "bearish"],
    debate_rounds=2,
    w_base=0.40,
    w_opinion=0.60,
    w_random=0.0,
    researcher_weights={"bullish": 0.5, "bearish": 0.5},
    principle_intensities={"guan_ren": 1.0, "avoid_being_guaned": 1.0},
    rules={},  # All default weights
)

# ── 诡诈型 Tricky ──────────────────────────────────────────────────────────

TRICKY = PersonalityConfig(
    name="诡诈型",
    active_researchers=["bullish", "wildcard"],
    debate_rounds=1,
    w_base=0.20,
    w_opinion=0.60,
    w_random=0.20,
    researcher_weights={"bullish": 0.5, "wildcard": 0.5},
    principle_intensities={"guan_ren": 0.8, "avoid_being_guaned": 0.8},
    rules={
        "intercept":        0.8,
        "friendly_fire":    0.7,
        "last_act":         0.6,
        "safe_play":        0.5,
        "identity_protect": 0.6,
        "help_teammate":    0.5,
        "delay_bomb":       0.4,
        "score_rush":       0.7,
        "speed_first":      0.5,
    },
)

# ── 配合型 Cooperative ─────────────────────────────────────────────────────

COOPERATIVE = PersonalityConfig(
    name="配合型",
    active_researchers=["bullish", "bearish"],
    debate_rounds=2,
    w_base=0.35,
    w_opinion=0.50,
    w_team=0.15,
    researcher_weights={"bullish": 0.4, "bearish": 0.6},
    principle_intensities={"guan_ren": 1.0, "avoid_being_guaned": 1.0},
    rules={
        "intercept":        0.8,
        "friendly_fire":    1.3,
        "last_act":         1.0,
        "safe_play":        0.8,
        "identity_protect": 1.0,
        "help_teammate":    1.2,
        "delay_bomb":       0.6,
        "score_rush":       0.6,
        "speed_first":      0.5,
    },
)

# ── 自私型 Selfish ─────────────────────────────────────────────────────────

SELFISH = PersonalityConfig(
    name="自私型",
    active_researchers=["bullish"],
    debate_rounds=0,
    w_base=0.25,
    w_opinion=0.55,
    w_random=0.20,
    researcher_weights={"bullish": 1.0},
    principle_intensities={"guan_ren": 0.5, "avoid_being_guaned": 0.5},
    rules={
        "intercept":        1.0,
        "friendly_fire":    0.4,
        "last_act":         0.8,
        "safe_play":        0.2,
        "identity_protect": 0.3,
        "help_teammate":    0.3,
        "delay_bomb":       0.3,
        "score_rush":       1.2,
        "speed_first":      1.0,
    },
)
