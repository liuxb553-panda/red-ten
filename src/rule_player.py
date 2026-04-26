from __future__ import annotations
from cards import Card
from moves import Move, CardType, get_legal_moves
from state import GameState, Team
from hand import Player
from identity import IdentityTracker
from evaluator import (
    scoring_value, bomb_tier, best_bomb, cheapest_winning_move,
    hand_playability, trick_scoring_value, is_high_value_trick, best_lead,
)


class RuleBasedPlayer(Player):
    """
    Tier 1 rule-based AI. Implements lead/follow/always heuristics.
    Each player instance owns its own IdentityTracker.
    """

    # Bomb level threshold: don't use bombs stronger than this on low-value tricks
    _BOMB_RESERVE_LEVEL = 9   # don't burn level 1-8 bombs unnecessarily

    def __init__(self, player_id: int):
        super().__init__(player_id)
        self.tracker = IdentityTracker()

    def choose_action(self, state: GameState, legal_moves: list[Move]) -> Move:
        self.tracker.sync_from_state(state)
        hand = state.hands[self.id]
        trick = state.current_trick  # list of (player, Move) so far this trick

        if not legal_moves:
            raise RuntimeError(f"P{self.id}: no legal moves")

        # Determine if we are leading or following
        current_best = self._current_best_move(state)

        if current_best is None or current_best.is_pass():
            return self._lead(state, legal_moves, hand)
        else:
            return self._follow(state, legal_moves, hand, current_best)

    # ------------------------------------------------------------------
    # Leading
    # ------------------------------------------------------------------

    def _lead(self, state: GameState, legal_moves: list[Move], hand: list[Card]) -> Move:
        non_pass = [m for m in legal_moves if not m.is_pass()]
        if not non_pass:
            return Move.pass_move()

        # If we can finish in one play, do it
        for m in non_pass:
            if len(m.cards) == len(hand):
                return m

        # Separate bombs from normal plays
        bombs    = [m for m in non_pass if m.is_bomb()]
        normals  = [m for m in non_pass if not m.is_bomb()]

        trick_pts = self._trick_pts_in_current_trick(state)
        high_value = trick_pts >= 10  # not applicable when leading fresh; just check our hand

        # Check if we're nearly done (≤5 cards) — lead aggressively to empty hand
        if len(hand) <= 5:
            return self._lead_drain(normals or non_pass, hand)

        # Try to lead a strong multi-card play
        if normals:
            return best_lead(hand)

        # Only bombs left — use the weakest one
        if bombs:
            return max(bombs, key=lambda m: (m.bomb_key[0], -m.bomb_key[1]))

        return non_pass[0]

    def _lead_drain(self, moves: list[Move], hand: list[Card]) -> Move:
        """When nearly empty, pick move that uses the most cards."""
        if not moves:
            return Move.pass_move()
        return max(moves, key=lambda m: len(m.cards))

    # ------------------------------------------------------------------
    # Following
    # ------------------------------------------------------------------

    def _follow(
        self,
        state: GameState,
        legal_moves: list[Move],
        hand: list[Card],
        current_best: Move,
    ) -> Move:
        pass_move   = Move.pass_move()
        current_winner = self._current_trick_winner(state)

        trick_pts = self._trick_pts_in_current_trick(state)
        high_value = trick_pts >= 10

        # 1. If current winner is a confirmed/likely teammate → pass to preserve their lead
        if current_winner is not None and current_winner != self.id:
            if self.tracker.is_likely_teammate(self.id, current_winner, threshold=0.65):
                # Only beat if protecting them from losing a big trick to an opponent
                # For now: always pass when winner is a teammate
                return pass_move

        # 2. If trick has no scoring cards → prefer to pass (save cards for scoring tricks)
        if not high_value:
            # Still beat if it's cheap and we're near the end of the hand
            if len(hand) <= 4:
                cheap = cheapest_winning_move(hand, current_best)
                if cheap and not cheap.is_bomb():
                    return cheap
            return pass_move

        # 3. High-value trick — try to win it
        cheap = cheapest_winning_move(hand, current_best)
        if cheap is None:
            return pass_move  # can't beat, must pass

        # Don't burn a strong bomb on a modest trick
        if cheap.is_bomb():
            level = cheap.bomb_key[0]
            if level <= self._BOMB_RESERVE_LEVEL and trick_pts < 30:
                return pass_move
            # Weak bomb is fine
            return cheap

        return cheap

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _current_best_move(self, state: GameState) -> Move | None:
        """The current best (winning) move in the active trick, or None if leading."""
        if not state.current_trick:
            return None
        _, move = state.current_trick[-1]
        # The "current best" is the last non-pass move
        for _, m in reversed(state.current_trick):
            if not m.is_pass():
                return m
        return None

    def _current_trick_winner(self, state: GameState) -> int | None:
        """Player index of whoever is currently winning the trick, or None."""
        for player, m in reversed(state.current_trick):
            if not m.is_pass():
                return player
        return None

    def _trick_pts_in_current_trick(self, state: GameState) -> int:
        return sum(c.score_value() for _, m in state.current_trick for c in m.cards)


