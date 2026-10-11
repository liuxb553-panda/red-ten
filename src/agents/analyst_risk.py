"""
RiskAnalyst — reads the first 4 analysts' output and computes risk metrics.

Populates SharedAnalysis fields:
  red_ten_exposure_risk, score_loss_risk, situation_advantage,
  bombs_visible_remaining
"""
from __future__ import annotations
from collections import Counter
from moves import Move, CardType
from cards import Rank, build_deck
from state import GameState
from identity import IdentityTracker
from shared_analysis import SharedAnalysis
from brain import BaseAgent

_FULL_DECK_COUNTER: Counter = Counter(build_deck())


class RiskAnalyst(BaseAgent):
    """Aggregates prior analysis into risk scores and situation assessment."""

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

        # Red ten exposure risk
        exposure = 0.0
        if analysis.red_ten_status == "all_hidden":
            for m in legal_moves:
                if any(c.is_red_ten() for c in m.cards):
                    exposure = 0.8
                    break
        elif analysis.red_ten_status == "partial":
            for m in legal_moves:
                if any(c.is_red_ten() for c in m.cards):
                    exposure = 0.4
                    break
        # Lower risk when last to act (fewer players can exploit)
        if analysis.is_last_to_act:
            exposure *= 0.5
        analysis.red_ten_exposure_risk = exposure

        # Score loss risk per card type
        score_risk: dict[CardType, int] = {}
        has_opponents_after = len(analysis.players_after_me) > 0
        weak_hand = analysis.hand_strength < 0.5
        for m in legal_moves:
            if m.is_pass():
                continue
            sv = sum(c.score_value() for c in m.cards)
            if sv > 0 and has_opponents_after and weak_hand:
                score_risk[m.type] = max(score_risk.get(m.type, 0), sv)
        analysis.score_loss_risk = score_risk

        # Situation advantage [-1, 1]
        ally_adv = max(-1.0, min(1.0, analysis.ally_finish_advantage / 3.0))
        hand_str = analysis.hand_strength
        # Team strength: ratio of teammates to opponents among confirmed players
        confirmed_team = sum(
            1 for p in range(6)
            if tracker.is_confirmed_red(p) or tracker.is_confirmed_non_red(p)
        )
        team_adv = 0.0
        if confirmed_team > 0:
            our_confirmed = sum(
                1 for p in range(6)
                if analysis.likely_teammates[p] >= 0.6
                and (tracker.is_confirmed_red(p) or tracker.is_confirmed_non_red(p))
            )
            team_adv = (our_confirmed / confirmed_team) * 2 - 1

        raw = 0.3 * ally_adv + 0.4 * hand_str + 0.3 * team_adv
        analysis.situation_advantage = max(-1.0, min(1.0, raw * 2 - 0.5))

        # Estimate remaining bombs
        played_counter = Counter(state.played_cards)
        for _, m in state.current_trick:
            if not m.is_pass():
                played_counter.update(m.cards)
        # Also count cards in our hand (we know exactly what we have)
        played_counter.update(state.hands[self.player_id])

        potential_bombs = 0
        for rank in range(3, 16):  # THREE through TWO
            total = sum(
                count for card, count in _FULL_DECK_COUNTER.items()
                if int(card.rank) == rank
            )
            played = sum(
                count for card, count in played_counter.items()
                if int(card.rank) == rank
            )
            unplayed = max(0, total - played)
            potential_bombs += unplayed // 4
        # Already visible bombs
        visible = len(analysis.bombs_visible)
        # Bombs we already know about (our own)
        my_bombs_count = len(analysis.my_bombs)
        # Remaining bombs that others might hold
        analysis.bombs_visible_remaining = max(0, potential_bombs - my_bombs_count + visible)
