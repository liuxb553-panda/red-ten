"""
OpponentAnalyst — tracks opponent hand distribution and unplayed threats.

Populates SharedAnalysis fields:
  scoring_cards_remaining, bombs_visible, high_cards_unplayed,
  estimated_opp_hand_strength, opponent_style_guess, opp_hand_counts
"""
from __future__ import annotations
from collections import Counter
from moves import Move, CardType
from cards import Card, Rank, Suit, build_deck
from state import GameState, Team
from identity import IdentityTracker
from shared_analysis import SharedAnalysis
from brain import BaseAgent

# Pre-computed full deck for unplayed-card tracking
_FULL_DECK_COUNTER: Counter = Counter(build_deck())

# High-value ranks that are important to track
_HIGH_RANKS = (Rank.TWO, Rank.ACE, Rank.SMALL_JOKER, Rank.BIG_JOKER)

# Scoring ranks: 5, 10, K
_SCORING_RANKS = (Rank.FIVE, Rank.TEN, Rank.KING)


class OpponentAnalyst(BaseAgent):
    """Tracks opponent card distribution, unplayed threats, and hand strength."""

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
        # Hand counts (ground truth from state)
        analysis.opp_hand_counts = [
            state.player_statuses[p].cards_remaining for p in range(6)
        ]

        # Scoring cards remaining per team
        played_counter = Counter(state.played_cards)
        # Also count cards currently on the table in this trick
        for _, m in state.current_trick:
            if not m.is_pass():
                played_counter.update(m.cards)

        red_score = 0
        non_red_score = 0
        for rank in _SCORING_RANKS:
            total_of_rank = sum(
                count for card, count in _FULL_DECK_COUNTER.items()
                if card.rank == rank
            )
            played_of_rank = sum(
                count for card, count in played_counter.items()
                if card.rank == rank
            )
            remaining = max(0, total_of_rank - played_of_rank)
            # Distribute by hand-size proportion among active players
            red_hand_total = 0
            non_red_hand_total = 0
            for p in range(6):
                if state.player_statuses[p].finished:
                    continue
                if analysis.likely_teammates[p] >= 0.5:
                    red_hand_total += state.player_statuses[p].cards_remaining
                else:
                    non_red_hand_total += state.player_statuses[p].cards_remaining
            total_active = red_hand_total + non_red_hand_total
            if total_active > 0:
                red_score += int(remaining * red_hand_total / total_active) * _score_for_rank(rank)
                non_red_score += int(remaining * non_red_hand_total / total_active) * _score_for_rank(rank)

        analysis.scoring_cards_remaining = {
            Team.RED: red_score,
            Team.NON_RED: non_red_score,
        }

        # Bombs visible in current trick
        analysis.bombs_visible = [
            m for _, m in state.current_trick if m.is_bomb()
        ]

        # High cards unplayed
        high_unplayed: list[Rank] = []
        for rank in _HIGH_RANKS:
            total_of_rank = sum(
                count for card, count in _FULL_DECK_COUNTER.items()
                if card.rank == rank
            )
            played_of_rank = sum(
                count for card, count in played_counter.items()
                if card.rank == rank
            )
            unplayed = max(0, total_of_rank - played_of_rank)
            for _ in range(unplayed):
                high_unplayed.append(rank)
        analysis.high_cards_unplayed = high_unplayed

        # Estimated opponent hand strength
        est_strength: list[float] = []
        for p in range(6):
            if p == self.player_id:
                est_strength.append(analysis.hand_strength)
                continue
            rem = state.player_statuses[p].cards_remaining
            progress = 1.0 - (rem / 27.0)
            # Heuristic: opponents who played bombs are stronger
            has_bomb = any(
                m.is_bomb() for player, m in state.current_trick if player == p
            )
            # More remaining high cards → likely held by players with more cards
            high_ratio = len(analysis.high_cards_unplayed) / max(1, sum(
                state.player_statuses[q].cards_remaining
                for q in range(6) if q != self.player_id
            ))
            likely_high = min(1.0, rem * high_ratio)
            strength = 0.5 * progress + 0.3 * (1.0 if has_bomb else 0.0) + 0.2 * likely_high
            est_strength.append(min(1.0, strength))
        analysis.estimated_opp_hand_strength = est_strength

        # Style guesses (Phase 8 feature, stub for now)
        analysis.opponent_style_guess = ["unknown"] * 6


def _score_for_rank(rank: Rank) -> int:
    if rank == Rank.FIVE:
        return 5
    if rank in (Rank.TEN, Rank.KING):
        return 10
    return 0
