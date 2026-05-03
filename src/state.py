from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional
from cards import Card


class Team(Enum):
    RED     = "Red"
    NON_RED = "Non-Red"


class TerminalKind(Enum):
    NORMAL      = auto()
    GUAN_REN    = auto()   # 关人: one team shuts out the other
    SAN_HONG_SHI = auto()  # 3红十 solo shutout


@dataclass
class HandResult:
    terminal: TerminalKind
    finish_order: list[int]           # all 6 in order
    red_team: list[int]
    non_red_team: list[int]
    da_gong: Optional[int]
    mo_gong: list[int]
    mo_gong_hands: dict               # {player_id: [remaining cards]}
    da_gong_mo_gong_same_team: bool
    base_scores: dict                 # {Team.RED: int, Team.NON_RED: int}
    final_team_scores: dict           # {Team.RED: int, Team.NON_RED: int}
    final_scores: list[int]           # per-player scores (6 values)


@dataclass
class PlayerStatus:
    cards_remaining: int = 27
    red_ten_count: int = 0  # how many red tens this player has played (max 3)
    finished: bool = False
    finish_position: Optional[int] = None  # 1-indexed

    # Inferred team (None until revealed or fully inferred)
    team: Optional[Team] = None

    @property
    def identity_revealed(self) -> bool:
        return self.red_ten_count > 0


@dataclass
class GameState:
    # hands[p] = list of cards in player p's hand
    hands: list[list[Card]] = field(default_factory=lambda: [[] for _ in range(6)])
    played_cards: list[Card] = field(default_factory=list)

    # Current trick state
    current_trick: list[tuple[int, object]] = field(default_factory=list)  # (player_idx, Move)
    trick_leader: int = 0

    # Counter-clockwise turn order starting from trick_leader
    # Stored as the canonical rotation; rebuilt each trick
    turn_order: list[int] = field(default_factory=lambda: list(range(6)))

    # Scores accumulated during the hand (trick points per player)
    trick_scores: list[int] = field(default_factory=lambda: [0] * 6)

    # Player statuses
    player_statuses: list[PlayerStatus] = field(default_factory=lambda: [PlayerStatus() for _ in range(6)])

    # Terminal tracking
    da_gong: Optional[int] = None          # first to finish
    finish_order: list[int] = field(default_factory=list)  # finish order
    mo_gong: list[int] = field(default_factory=list)       # players still holding when opposing team done
    terminal: Optional[TerminalKind] = None

    # Red ten tracking
    red_ten_holders: list[Optional[int]] = field(default_factory=lambda: [None, None, None])
    # Index i = which player holds red_ten i; set when revealed or at end

    def revealed_red_ten_count(self) -> int:
        return sum(self.player_statuses[p].red_ten_count for p in range(6))

    def all_red_tens_revealed(self) -> bool:
        return self.revealed_red_ten_count() >= 3

    def team_of(self, player: int) -> Optional[Team]:
        return self.player_statuses[player].team

    def red_team(self) -> list[int]:
        return [p for p in range(6) if self.player_statuses[p].team == Team.RED]

    def non_red_team(self) -> list[int]:
        return [p for p in range(6) if self.player_statuses[p].team == Team.NON_RED]

    def finished_players(self) -> list[int]:
        return [p for p in range(6) if self.player_statuses[p].finished]

    def active_players(self) -> list[int]:
        return [p for p in range(6) if not self.player_statuses[p].finished]

    def turn_order_from(self, start: int) -> list[int]:
        """Counter-clockwise order starting from start (wrapping around).
        Visually: P0 (bottom) → P5 (lower-right) → P4 (right) → P3 (top)
                  → P2 (left) → P1 (lower-left) → back to P0."""
        base = list(range(6))
        idx = base.index(start)
        return [base[(idx - i) % 6] for i in range(6)]
