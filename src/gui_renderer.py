"""
GUIRenderer — drop-in replacement for GameLogger.
Records every game event as a snapshot list that the pygame GUI can play back.
"""
from __future__ import annotations
import copy
from dataclasses import dataclass, field
from typing import Optional

from cards import Card
from moves import Move
from state import Team, TerminalKind, HandResult
from logger import GameLogger


@dataclass
class GameSnapshot:
    """Full visual state at one point in the game."""
    # Per-player state
    hands: list[list[Card]]             # cards still in each player's hand
    trick_scores: list[int]             # points captured this hand per player
    cumulative_scores: list[int]        # running total across hands
    identities: list[Optional[Team]]    # None = unknown
    finished: list[bool]
    finish_order: list[int]             # in order of finishing
    # Current trick
    trick_plays: list[tuple[int, Move]] # (player, move) for current trick
    trick_winner: Optional[int]         # set after trick_end
    # Metadata
    hand_number: int
    trick_number: int


@dataclass
class GameEvent:
    kind: str          # "session_start" | "hand_start" | "deal" | "lead" | "action" |
                       # "trick_end" | "finish" | "reveal" | "gui_zhu" | "mo_gong" |
                       # "guan_ren" | "san_hong_shi" | "hand_end" | "session_end"
    description: str   # human-readable annotation shown in GUI
    snapshot: GameSnapshot
    # Event-specific payloads
    player: Optional[int] = None
    move: Optional[Move] = None
    beats_player: Optional[int] = None
    winner: Optional[int] = None
    scoring_cards: list[Card] = field(default_factory=list)
    points: int = 0
    result: Optional[HandResult] = None


class GUIRenderer(GameLogger):
    """Records game events for GUI playback. Pass to Hand/GameSession instead of GameLogger."""

    def __init__(self):
        super().__init__(verbose=False)
        self.events: list[GameEvent] = []

        # Mutable state — updated as events come in
        self._hands: list[list[Card]] = [[] for _ in range(6)]
        self._trick_scores: list[int] = [0] * 6
        self._cumulative: list[int] = [0] * 6
        self._identities: list[Optional[Team]] = [None] * 6
        self._finished: list[bool] = [False] * 6
        self._finish_order: list[int] = []
        self._trick_plays: list[tuple[int, Move]] = []
        self._trick_winner: Optional[int] = None
        self._hand_number: int = 0
        self._trick_number: int = 0
        self._teams: list[Optional[Team]] = [None] * 6  # actual teams (set at deal time)

    def _snap(self) -> GameSnapshot:
        return GameSnapshot(
            hands=copy.deepcopy(self._hands),
            trick_scores=list(self._trick_scores),
            cumulative_scores=list(self._cumulative),
            identities=list(self._identities),
            finished=list(self._finished),
            finish_order=list(self._finish_order),
            trick_plays=list(self._trick_plays),
            trick_winner=self._trick_winner,
            hand_number=self._hand_number,
            trick_number=self._trick_number,
        )

    def _emit(self, kind: str, desc: str, **kwargs) -> None:
        self.events.append(GameEvent(kind=kind, description=desc, snapshot=self._snap(), **kwargs))

    def _remove_cards_from_hand(self, player: int, move: Move):
        for card in move.cards:
            try:
                self._hands[player].remove(card)
            except ValueError:
                pass  # card already accounted for

    # ── GameLogger interface ──────────────────────────────────────────────

    def log_session_start(self, num_hands: int):
        self._emit("session_start", f"Session start — {num_hands} hands")

    def log_hand_header(self, hand_num: int, first_player: int, reason: str = ""):
        self._hand_number = hand_num
        self._trick_number = 0
        self._trick_plays = []
        self._trick_winner = None
        self._trick_scores = [0] * 6
        self._finished = [False] * 6
        self._finish_order = []
        self._identities = [None] * 6
        self._emit("hand_start", f"Hand {hand_num} — P{first_player} goes first ({reason})",
                   player=first_player)

    def log_deal(self, hands: list[list[Card]]):
        self._hands = copy.deepcopy(hands)
        # Infer teams from actual hands (ground truth, for rendering face-up)
        self._teams = [
            Team.RED if any(c.is_red_ten() for c in h) else Team.NON_RED
            for h in hands
        ]
        desc = "Dealt 27 cards each"
        self._emit("deal", desc)

    def log_trick_header(self, trick_num: int):
        self._trick_number = trick_num
        self._trick_plays = []
        self._trick_winner = None

    def log_trick_lead(self, player: int, move: Move):
        self._remove_cards_from_hand(player, move)
        self._trick_plays = [(player, move)]
        self._emit("lead", f"P{player} leads: {move}", player=player, move=move)

    def log_action(self, player: int, move: Move, beats_player: int | None = None):
        if not move.is_pass():
            self._remove_cards_from_hand(player, move)
            self._trick_plays.append((player, move))
        desc = f"P{player}: {'pass' if move.is_pass() else str(move)}"
        if beats_player is not None:
            desc += f"  ← beats P{beats_player}"
        self._emit("action", desc, player=player, move=move, beats_player=beats_player)

    def log_trick_end(self, winner: int, scoring_cards: list[Card], points: int):
        self._trick_scores[winner] += points
        self._trick_winner = winner
        desc = f"P{winner} wins trick"
        if points:
            desc += f" (+{points} pts)"
        self._emit("trick_end", desc, winner=winner, scoring_cards=scoring_cards, points=points)
        self._trick_plays = []
        self._trick_winner = None

    def log_player_finished(self, player: int, position: int):
        self._finished[player] = True
        self._finish_order.append(player)
        labels = {1: "大贡", 5: "末贡(last)"}
        label = labels.get(position, f"{position}nd/rd/th")
        self._emit("finish", f"P{player} finishes! ({label})", player=player, points=position)

    def log_identity_reveal(self, player: int):
        self._identities[player] = Team.RED
        self._emit("reveal", f"★ P{player} revealed: Red Team", player=player)

    def log_gui_zhu(self, finished_player: int, new_leader: int, case: int):
        desc = (f"归主 (case {case}): P{finished_player} finished → P{new_leader} inherits lead")
        self._emit("gui_zhu", desc, player=new_leader)

    def log_mo_gong(self, players: list[int]):
        pl = ", ".join(f"P{p}" for p in players)
        self._emit("mo_gong", f"末贡: {pl}")

    def log_guan_ren(self, winner_team: Team):
        self._emit("guan_ren", f"★★ 关人！{winner_team.value} team wins!", player=None)

    def log_san_hong_shi(self, player: int):
        self._emit("san_hong_shi", f"★★★ 3红十！ P{player} solo shut out all 5!", player=player)

    def log_hand_summary(self, result: HandResult, cumulative: list[int]):
        for p in range(6):
            self._cumulative[p] = cumulative[p]
        desc = f"Hand {self._hand_number} over — Red {result.final_team_scores[Team.RED]} | Non-Red {result.final_team_scores[Team.NON_RED]}"
        self._emit("hand_end", desc, result=result)

    def _p(self, msg: str):
        pass  # suppress all print output
