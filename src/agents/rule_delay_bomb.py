"""
DelayBombRule — save bombs for later when hand is still large and no threat is imminent.
"""
from __future__ import annotations
from moves import Move
from shared_analysis import SharedAnalysis
from rules_base import StrategyRule


class DelayBombRule(StrategyRule):
    """Save bombs when hand is still large and no opponent is about to finish."""

    name = "delay_bomb"
    description = "手牌多且无紧迫威胁时保留炸弹"
    category = "timing"
    default_weight = 0.6

    def score(self, move: Move, analysis: SharedAnalysis) -> float:
        # Only apply when hand is still large
        if analysis.estimated_tricks_to_finish < 4:
            return 0.0

        # Check if any opponent is close to finishing (≤ 2 cards)
        for pid in range(6):
            if analysis.opp_hand_counts[pid] <= 0:
                continue
            if analysis.likely_opponents[pid] >= 0.5:
                if analysis.opp_hand_counts[pid] <= 2:
                    return 0.0  # Urgent — don't delay

        if move.is_bomb():
            return -0.3  # Save it
        if move.is_pass():
            return 0.5   # Preserving options
        return 0.0
