"""
Shared data structures for the multi-agent AI pipeline.

SharedAnalysis is the central state object populated by the 5 analysts in Phase 1,
read by researchers in Phase 2, and used by LeadAgent in Phase 4.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from cards import Card, Rank
from moves import Move, CardType
from state import Team


@dataclass
class SharedAnalysis:
    """Shared analysis state written by the 5 analyst agents.

    Each section is populated by a specific analyst. Fields have safe defaults
    so the pipeline can run with partial or no analysis (stub mode).
    """

    # ── HandAnalyst ──
    my_bombs: list[Move] = field(default_factory=list)
    my_combos_by_type: dict[CardType, list[Move]] = field(default_factory=dict)
    dangerous_cards: list[Card] = field(default_factory=list)
    hand_strength: float = 0.0                     # [0, 1]
    estimated_tricks_to_finish: int = 99

    # ── PositionAnalyst ──
    my_position_in_trick: int = 0
    players_after_me: list[int] = field(default_factory=list)
    is_last_to_act: bool = False
    trick_leader_team: Optional[Team] = None

    # ── TeamAnalyst ──
    likely_teammates: list[float] = field(default_factory=lambda: [0.0] * 6)
    likely_opponents: list[float] = field(default_factory=lambda: [0.0] * 6)
    red_ten_status: str = "all_hidden"             # "all_hidden" | "partial" | "all_revealed"
    ally_finish_advantage: int = 0                  # [-6, 6]
    teammate_needs_help: list[int] = field(default_factory=list)
    my_team: Optional[Team] = None

    # ── OpponentAnalyst ──
    scoring_cards_remaining: dict[Team, int] = field(default_factory=dict)
    bombs_visible: list[Move] = field(default_factory=list)
    high_cards_unplayed: list[Rank] = field(default_factory=list)
    estimated_opp_hand_strength: list[float] = field(default_factory=lambda: [0.0] * 6)
    opponent_style_guess: list[str] = field(default_factory=lambda: ["unknown"] * 6)
    opp_hand_counts: list[int] = field(default_factory=lambda: [27] * 6)

    # ── RiskAnalyst ──
    red_ten_exposure_risk: float = 0.0             # [0, 1]
    score_loss_risk: dict[CardType, int] = field(default_factory=dict)
    situation_advantage: float = 0.0               # [-1, 1]
    bombs_visible_remaining: int = 0

    # ── Convenience (derived by TeamAnalyst / OpponentAnalyst) ──
    opp_finished_count: int = 0
    red_finished_count: int = 0
    our_min_remaining: int = 27
    opp_min_remaining: int = 27

    # ── StrategyDirector output (Phase 1.5) ──
    strategic_context: Optional[StrategicContext] = None


@dataclass
class StrategicContext:
    """Written by StrategyDirector in Phase 1.5.

    Represents the global strategic situation and modifies downstream tactical
    rule weights. Multiple strategic principles can be active simultaneously;
    their weight modifiers are merged additively and clamped.
    """
    primary_goal: str = "balanced"                 # "guan_ren" | "avoid_being_guaned" | "max_score" | "balanced"
    rule_weight_modifiers: dict[str, float] = field(default_factory=dict)
    goal_urgency: float = 0.0                      # [0, 1]
    reasoning: str = ""


@dataclass
class ResearcherOpinion:
    """Output produced by each researcher in Phase 2.

    A researcher evaluates all legal moves through its assigned tactical rules
    and produces a directional opinion — not a specific move selection.
    """
    researcher_name: str = ""                      # "Bullish" | "Bearish" | "Wildcard"
    preferred_category: CardType = CardType.PASS
    preferred_rank_range: tuple[int, int] = (0, 0)
    must_avoid: list[CardType] = field(default_factory=list)
    reasoning: str = ""
    confidence: float = 0.0                        # [0, 1]
    move_scores: dict = field(default_factory=dict)  # {Move: float} per-move scores
