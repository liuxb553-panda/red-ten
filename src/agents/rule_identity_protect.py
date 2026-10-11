"""
IdentityProtectRule — avoid revealing red ten identity through play choices.
"""
from __future__ import annotations
from moves import Move
from shared_analysis import SharedAnalysis
from rules_base import StrategyRule


class IdentityProtectRule(StrategyRule):
    """Avoid playing cards that contain red tens when identity is hidden."""

    name = "identity_protect"
    description = "红十未明时避免出含红十的牌型暴露身份"
    category = "defensive"
    default_weight = 1.0

    def score(self, move: Move, analysis: SharedAnalysis) -> float:
        if move.is_pass():
            return 0.0

        has_red_ten = any(c.is_red_ten() for c in move.cards)
        if not has_red_ten:
            return 0.0

        if analysis.red_ten_status == "all_hidden":
            return -0.8
        elif analysis.red_ten_status == "partial":
            return -0.3
        return 0.0
