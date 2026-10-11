"""
InterceptRule — bomb opponents who are about to finish.

Activates when any likely opponent has ≤ 2 cards remaining.
"""
from __future__ import annotations
from moves import Move
from shared_analysis import SharedAnalysis
from rules_base import StrategyRule


class InterceptRule(StrategyRule):
    """Bomb opponents who are about to finish."""

    name = "intercept"
    description = "对手快出完时炸弹拦截"
    category = "offensive"
    default_weight = 0.8

    def score(self, move: Move, analysis: SharedAnalysis) -> float:
        if not move.is_bomb():
            return 0.0

        for pid in range(6):
            if analysis.opp_hand_counts[pid] <= 0:
                continue
            if analysis.likely_opponents[pid] >= 0.5:
                if analysis.opp_hand_counts[pid] <= 2:
                    return 1.0
        return 0.0
