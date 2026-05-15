"""
HandAnalyst — analyzes the player's own hand structure.

Populates SharedAnalysis fields:
  my_bombs, my_combos_by_type, dangerous_cards, hand_strength,
  estimated_tricks_to_finish
"""
from __future__ import annotations
from moves import Move, CardType, get_legal_moves
from state import GameState
from identity import IdentityTracker
from shared_analysis import SharedAnalysis
from brain import BaseAgent
from evaluator import best_bomb, cards_to_finish


class HandAnalyst(BaseAgent):
    """Analyzes the player's hand: bombs, playable combos, strength, danger cards."""

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
        hand = state.hands[self.player_id]
        leading_moves = get_legal_moves(hand, None)

        # Bombs
        best = best_bomb(hand)
        if best is not None:
            analysis.my_bombs.append(best)
        analysis.my_bombs.extend(
            [m for m in leading_moves if m.is_bomb() and m != best]
        )

        # Combos by type
        for m in leading_moves:
            analysis.my_combos_by_type.setdefault(m.type, []).append(m)

        # Dangerous cards: special cards (red tens, jokers) that are hard to shed
        for c in hand:
            if not c.is_special():
                continue
            if c.is_red_ten():
                # Red ten is dangerous if identity not yet revealed
                analysis.dangerous_cards.append(c)
            elif c.is_joker():
                # Jokers are dangerous if hand is small (hard to pair)
                if len(hand) <= 6:
                    analysis.dangerous_cards.append(c)

        # Hand strength [0, 1]
        has_bomb = len(analysis.my_bombs) > 0
        high_ranks = {15, 14, 16, 17}  # TWO, ACE, SMALL_JOKER, BIG_JOKER
        high_count = sum(1 for c in hand if int(c.rank) in high_ranks)
        high_ratio = min(1.0, high_count / max(1, len(hand)))
        playability = len(leading_moves) / max(1, len(hand))
        analysis.hand_strength = min(
            1.0,
            0.4 * (1.0 if has_bomb else 0.0)
            + 0.3 * high_ratio
            + 0.3 * playability,
        )

        # Estimated tricks to finish
        analysis.estimated_tricks_to_finish = cards_to_finish(hand)
