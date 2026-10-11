"""
ScoreRushRule — prefer plays that capture scoring cards.
"""
from __future__ import annotations
from moves import Move
from shared_analysis import SharedAnalysis
from rules_base import StrategyRule


class ScoreRushRule(StrategyRule):
    """Prefer moves that capture scoring cards (5, 10, K)."""

    name = "score_rush"
    description = "有机会抢分时优先出高分牌型"
    category = "offensive"
    default_weight = 0.8

    def score(self, move: Move, analysis: SharedAnalysis) -> float:
        if move.is_pass():
            return -0.2  # Missing scoring opportunity

        score_value = sum(c.score_value() for c in move.cards)
        if score_value == 0:
            return 0.0

        return min(0.7, score_value / 50.0)
