"""
SafePlayRule — be cautious with scoring cards when bombs are still unplayed.
"""
from __future__ import annotations
from moves import Move
from shared_analysis import SharedAnalysis
from rules_base import StrategyRule


class SafePlayRule(StrategyRule):
    """Avoid playing high-value scoring cards when bombs remain unseen."""

    name = "safe_play"
    description = "有未出炸弹时出分牌需谨慎"
    category = "defensive"
    default_weight = 0.7

    def score(self, move: Move, analysis: SharedAnalysis) -> float:
        if move.is_pass():
            return 0.0
        if analysis.bombs_visible_remaining <= 0:
            return 0.0

        score_value = sum(c.score_value() for c in move.cards)
        if score_value > 0:
            return -0.3 * (score_value / 10.0)
        return 0.0
