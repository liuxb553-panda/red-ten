"""
LastActRule — last-to-act strategy: pass when teammate is winning, act when opponent is.
"""
from __future__ import annotations
from moves import Move
from shared_analysis import SharedAnalysis
from rules_base import StrategyRule


class LastActRule(StrategyRule):
    """Last-to-act positional strategy."""

    name = "last_act"
    description = "末位且队友领先时pass，对手领先时必须出手"
    category = "timing"
    default_weight = 1.0

    def score(self, move: Move, analysis: SharedAnalysis) -> float:
        if not analysis.is_last_to_act:
            return 0.0
        if analysis.trick_leader_team is None or analysis.my_team is None:
            return 0.0

        if analysis.trick_leader_team == analysis.my_team:
            # Teammate is winning — prefer passing
            return 1.0 if move.is_pass() else -0.5
        else:
            # Opponent is winning — must act
            return -0.5 if move.is_pass() else 0.0
