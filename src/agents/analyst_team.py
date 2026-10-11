"""
TeamAnalyst — wraps IdentityTracker to produce team-related analysis.

Populates SharedAnalysis fields:
  likely_teammates, likely_opponents, my_team, red_ten_status,
  ally_finish_advantage, teammate_needs_help, opp_finished_count,
  red_finished_count, our_min_remaining, opp_min_remaining
"""
from __future__ import annotations
from moves import Move
from state import GameState, Team
from identity import IdentityTracker
from shared_analysis import SharedAnalysis
from brain import BaseAgent


class TeamAnalyst(BaseAgent):
    """Analyzes team identity beliefs, red ten status, and teammate state."""

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
        my_id = self.player_id

        # My believed team
        if tracker.is_confirmed_red(my_id):
            my_team = Team.RED
        elif tracker.is_confirmed_non_red(my_id):
            my_team = Team.NON_RED
        else:
            my_team = None
        analysis.my_team = my_team

        # Teammate/opponent probabilities from my perspective
        teammates: list[float] = []
        opponents: list[float] = []
        for p in range(6):
            if tracker.is_confirmed_red(my_id):
                prob_teammate = tracker.p_red[p]
            elif tracker.is_confirmed_non_red(my_id):
                prob_teammate = 1.0 - tracker.p_red[p]
            else:
                # Unknown self — assume the more likely team
                prob_teammate = max(tracker.p_red[p], 1.0 - tracker.p_red[p])
            teammates.append(prob_teammate)
            opponents.append(1.0 - prob_teammate)
        analysis.likely_teammates = teammates
        analysis.likely_opponents = opponents

        # Red ten revelation status
        revealed = state.revealed_red_ten_count()
        if revealed == 0:
            analysis.red_ten_status = "all_hidden"
        elif state.all_red_tens_revealed():
            analysis.red_ten_status = "all_revealed"
        else:
            analysis.red_ten_status = "partial"

        # Ally finish advantage: (finished teammates) - (finished opponents)
        ally_fin = 0
        opp_fin = 0
        for p in state.finish_order:
            if analysis.likely_teammates[p] >= 0.5:
                ally_fin += 1
            else:
                opp_fin += 1
        analysis.red_finished_count = ally_fin
        analysis.opp_finished_count = opp_fin
        analysis.ally_finish_advantage = ally_fin - opp_fin

        # Teammates needing help: a likely teammate who played a non-pass move
        # that was beaten by a later likely opponent
        help_needed: list[int] = []
        best_move: Move | None = None
        best_player: int = -1
        for p, m in state.current_trick:
            if m.is_pass():
                continue
            # Check if the previous best was a teammate and is now beaten
            if best_move is not None and m.beats(best_move):
                if analysis.likely_teammates[best_player] >= 0.6:
                    if analysis.likely_opponents[p] >= 0.6:
                        if best_player not in help_needed:
                            help_needed.append(best_player)
            best_move = m
            best_player = p
        analysis.teammate_needs_help = help_needed

        # Min remaining cards among allies / opponents
        our_min = 27
        opp_min = 27
        for p in range(6):
            if state.player_statuses[p].finished:
                continue
            rem = state.player_statuses[p].cards_remaining
            if analysis.likely_teammates[p] >= 0.5:
                if rem < our_min:
                    our_min = rem
            else:
                if rem < opp_min:
                    opp_min = rem
        analysis.our_min_remaining = our_min
        analysis.opp_min_remaining = opp_min
