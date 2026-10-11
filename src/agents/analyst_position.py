"""
PositionAnalyst — analyzes the player's position in the current trick.

Populates SharedAnalysis fields:
  my_position_in_trick, players_after_me, is_last_to_act, trick_leader_team
"""
from __future__ import annotations
from typing import Optional
from moves import Move
from state import GameState, Team
from identity import IdentityTracker
from shared_analysis import SharedAnalysis
from brain import BaseAgent


class PositionAnalyst(BaseAgent):
    """Analyzes seat position, turn order, and who acts after the player."""

    def __init__(self, player_id: int, name: str = "") -> None:
        super().__init__(name)
        self.player_id = player_id

    def analyze(
        self,
        state: GameState,
        legal_moves: list[Move],
        tracker: IdentityTracker,
        analysis: SharedAnalysis,
    ) -> None:
        # Position in trick
        already_played = {p for p, _ in state.current_trick}
        if self.player_id not in already_played:
            analysis.my_position_in_trick = len(already_played)
        else:
            analysis.my_position_in_trick = 0  # leading (or already played, shouldn't happen)

        # Players after me who haven't played and aren't finished
        order = state.turn_order_from(self.player_id)
        players_after: list[int] = []
        for p in order:
            if p == self.player_id:
                continue
            if p in already_played:
                continue
            if state.player_statuses[p].finished:
                continue
            players_after.append(p)
        analysis.players_after_me = players_after
        analysis.is_last_to_act = len(players_after) == 0

        # Trick leader's team (from our belief, not ground truth)
        leader = state.trick_leader
        leader_team: Optional[Team] = None
        if tracker.is_confirmed_red(leader):
            leader_team = Team.RED
        elif tracker.is_confirmed_non_red(leader):
            leader_team = Team.NON_RED
        analysis.trick_leader_team = leader_team
