"""
SpeedFirstRule — prioritize clearing hand quickly when many cards remain.
"""
from __future__ import annotations
from moves import Move
from shared_analysis import SharedAnalysis
from rules_base import StrategyRule


class SpeedFirstRule(StrategyRule):
    """Prefer clearing many cards quickly when hand is still large."""

    name = "speed_first"
    description = "手牌多时优先出大牌型快速清空"
    category = "offensive"
    default_weight = 0.7

    def score(self, move: Move, analysis: SharedAnalysis) -> float:
        if analysis.estimated_tricks_to_finish < 4:
            return 0.0

        if move.is_bomb():
            return 0.4   # Clears many cards at once
        if move.is_pass():
            return -0.3  # Delaying progress

        cards_out = len(move.cards)
        tricks = max(1, analysis.estimated_tricks_to_finish)
        efficiency = cards_out / tricks
        return 0.3 * min(1.0, efficiency)
