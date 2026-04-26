from __future__ import annotations
from math import comb
from state import GameState, Team
from cards import Card


def _prior_p_red() -> float:
    """P(a specific player holds ≥1 red ten) at game start via hypergeometric."""
    # 3 red tens in 162 cards, 27 drawn per player
    p_none = comb(159, 27) / comb(162, 27)
    return 1.0 - p_none


_PRIOR = _prior_p_red()  # ≈ 0.424


class IdentityTracker:
    """
    Maintains P(player_i is on Red team) for each of 6 players.

    Certainties are set immediately on reveal. Between reveals we apply
    soft Bayesian updates based on observable behaviour signals.
    """

    def __init__(self):
        self.p_red: list[float] = [_PRIOR] * 6
        self._confirmed: list[bool | None] = [None] * 6  # True=Red, False=Non-Red, None=unknown

    def confirm_red(self, player: int):
        self._confirmed[player] = True
        self.p_red[player] = 1.0
        self._renormalise_unknowns()

    def confirm_non_red(self, player: int):
        self._confirmed[player] = False
        self.p_red[player] = 0.0
        self._renormalise_unknowns()

    def _renormalise_unknowns(self):
        """
        After a confirmation, redistribute probability mass among unknowns.
        We know exactly 3 red ten holders exist in total; confirmed counts
        constrain how many unknowns can still be red.
        """
        confirmed_red   = sum(1 for c in self._confirmed if c is True)
        confirmed_non   = sum(1 for c in self._confirmed if c is False)
        unknown_count   = sum(1 for c in self._confirmed if c is None)
        remaining_red   = max(0, 3 - confirmed_red)   # red tens still unaccounted

        if unknown_count == 0:
            return

        if remaining_red == 0:
            for i in range(6):
                if self._confirmed[i] is None:
                    self.p_red[i] = 0.0
        else:
            # Spread remaining probability uniformly among unknowns
            # (simplified; a full hypergeometric update would be more accurate)
            base_p = min(1.0, remaining_red / unknown_count)
            for i in range(6):
                if self._confirmed[i] is None:
                    self.p_red[i] = base_p

    # ------------------------------------------------------------------
    # Soft signal updates (call after each observable action)
    # ------------------------------------------------------------------

    def update_played_against_red(self, player: int, aggressively: bool):
        """Player just played against a known-Red player."""
        if self._confirmed[player] is not None:
            return
        if aggressively:
            # Beating a Red player aggressively → probably Non-Red
            self.p_red[player] = max(0.0, self.p_red[player] * 0.7)
        else:
            # Passing when could beat a Red player → probably Red teammate
            self.p_red[player] = min(1.0, self.p_red[player] * 1.4)
        self._clamp_and_renorm(player)

    def update_bomb_protected_player(self, bomber: int, protected: int):
        """bomber used a bomb that saved protected (current winner) from losing the trick."""
        if self._confirmed[bomber] is None and self._confirmed[protected] is None:
            # Suggests they're teammates
            bump = 0.15
            self.p_red[bomber]    = min(1.0, self.p_red[bomber]    + bump)
            self.p_red[protected] = min(1.0, self.p_red[protected] + bump)
        elif self._confirmed[protected] is True:
            self.confirm_red(bomber)
        elif self._confirmed[protected] is False:
            self.confirm_non_red(bomber)

    def _clamp_and_renorm(self, changed: int):
        self.p_red[changed] = max(0.0, min(1.0, self.p_red[changed]))
        self._renormalise_unknowns()

    def is_confirmed_red(self, player: int) -> bool:
        return self._confirmed[player] is True

    def is_confirmed_non_red(self, player: int) -> bool:
        return self._confirmed[player] is False

    def is_confirmed(self, player: int) -> bool:
        return self._confirmed[player] is not None

    def is_likely_teammate(self, me: int, other: int, threshold: float = 0.6) -> bool:
        """True if other is probably on the same team as me."""
        if self._confirmed[me] is True and self._confirmed[other] is True:
            return True
        if self._confirmed[me] is False and self._confirmed[other] is False:
            return True
        if self._confirmed[me] is True:
            return self.p_red[other] >= threshold
        if self._confirmed[me] is False:
            return (1.0 - self.p_red[other]) >= threshold
        # Both unknown — can't say much
        return False

    def is_likely_opponent(self, me: int, other: int, threshold: float = 0.6) -> bool:
        if self._confirmed[me] is True and self._confirmed[other] is False:
            return True
        if self._confirmed[me] is False and self._confirmed[other] is True:
            return True
        if self._confirmed[me] is True:
            return (1.0 - self.p_red[other]) >= threshold
        if self._confirmed[me] is False:
            return self.p_red[other] >= threshold
        return False

    def sync_from_state(self, state: GameState):
        """Pull confirmed identities from game state after each trick."""
        for p in range(6):
            if state.player_statuses[p].identity_revealed and not self.is_confirmed_red(p):
                self.confirm_red(p)
            # Non-red confirmation only happens when all red tens are revealed
            if state.all_red_tens_revealed():
                if not self.is_confirmed(p):
                    self.confirm_non_red(p)
