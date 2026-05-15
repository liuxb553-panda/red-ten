"""
HelpTeammateRule — help a teammate whose play is being beaten by an opponent.
"""
from __future__ import annotations
from moves import Move
from shared_analysis import SharedAnalysis
from rules_base import StrategyRule


class HelpTeammateRule(StrategyRule):
    """Help teammates who are being beaten in the current trick."""

    name = "help_teammate"
    description = "队友被对手压制时解围"
    category = "teamwork"
    default_weight = 0.8

    def score(self, move: Move, analysis: SharedAnalysis) -> float:
        if not analysis.teammate_needs_help:
            return 0.0

        if move.is_bomb():
            return 0.6   # Bomb always beats the current best
        if move.is_pass():
            return -0.4  # Abandoning teammate
        return 0.3       # Non-bomb play — might help
