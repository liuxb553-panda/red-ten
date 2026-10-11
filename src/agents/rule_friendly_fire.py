"""
FriendlyFireRule — don't bomb when the current best play is from a teammate.
"""
from __future__ import annotations
from moves import Move
from shared_analysis import SharedAnalysis
from rules_base import StrategyRule


class FriendlyFireRule(StrategyRule):
    """Avoid bombing when the trick leader is a teammate."""

    name = "friendly_fire"
    description = "领先是队友时不炸自己人"
    category = "teamwork"
    default_weight = 1.0

    def score(self, move: Move, analysis: SharedAnalysis) -> float:
        if not move.is_bomb():
            return 0.0
        if analysis.trick_leader_team is None or analysis.my_team is None:
            return 0.0
        if analysis.trick_leader_team == analysis.my_team:
            return -1.0
        return 0.0
