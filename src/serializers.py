"""
Shared serialization helpers — convert game objects to JSON-safe dicts.
Used by both web_server.py (replay API) and room_manager.py (live broadcast).
"""
from __future__ import annotations
from typing import Optional

from cards import Card
from moves import Move
from state import Team, HandResult
from gui_renderer import GameEvent, GameSnapshot

_RANK_LBL = {
    3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8", 9: "9", 10: "10",
    11: "J", 12: "Q", 13: "K", 14: "A", 15: "2",
    16: "小王", 17: "大王",
}
_SUIT_SYM = {"CLUBS": "♣", "DIAMONDS": "♦", "HEARTS": "♥", "SPADES": "♠", "JOKER": ""}


def ser_card(c: Card) -> dict:
    return {
        "rl":  _RANK_LBL.get(c.rank.value, "?"),
        "s":   c.suit.name,
        "ss":  _SUIT_SYM.get(c.suit.name, ""),
        "rt":  c.is_red_ten(),
        "bj":  c.is_big_joker(),
        "sj":  c.is_small_joker(),
        "red": c.suit.name in ("HEARTS", "DIAMONDS"),
        "sv":  c.score_value(),
    }


def ser_move(m: Optional[Move]) -> Optional[dict]:
    if m is None:
        return None
    return {
        "cards": [ser_card(c) for c in m.cards],
        "pass":  m.is_pass(),
        "bomb":  m.is_bomb(),
        "desc":  "pass" if m.is_pass() else str(m),
    }


def ser_snap(s: GameSnapshot) -> dict:
    return {
        "hands":   [[ser_card(c) for c in h] for h in s.hands],
        "ts":      s.trick_scores,
        "cs":      s.cumulative_scores,
        "ids":     [i.value if i else None for i in s.identities],
        "rtc":     s.red_ten_counts,
        "fin":     s.finished,
        "fo":      s.finish_order,
        "tp":      [[p, ser_move(m)] for p, m in s.trick_plays],
        "tw":      s.trick_winner,
        "hn":      s.hand_number,
        "tn":      s.trick_number,
    }


def ser_result(r: Optional[HandResult]) -> Optional[dict]:
    if r is None:
        return None
    return {
        "terminal": r.terminal.name,
        "red":      r.red_team,
        "non_red":  r.non_red_team,
        "team_pts": {
            "RED":     r.final_team_scores[Team.RED],
            "NON_RED": r.final_team_scores[Team.NON_RED],
        },
        "scores":    r.final_scores,
        "da_gong":   r.da_gong,
        "mo_gong":   r.mo_gong,
        "mg_hands":  {str(p): [ser_card(c) for c in cards]
                      for p, cards in r.mo_gong_hands.items()},
    }


def ser_snap_pov(s: GameSnapshot, pov: int) -> dict:
    """Snapshot with other players' hands masked — only pov seat sees cards."""
    return {
        "hands":  [[ser_card(c) for c in s.hands[p]] if p == pov else []
                   for p in range(6)],
        "hcnt":   [len(h) for h in s.hands],   # true hand counts for all seats
        "ts":     s.trick_scores,
        "cs":     s.cumulative_scores,
        "ids":    [i.value if i else None for i in s.identities],
        "rtc":    s.red_ten_counts,
        "fin":    s.finished,
        "fo":     s.finish_order,
        "tp":     [[p, ser_move(m)] for p, m in s.trick_plays],
        "tw":     s.trick_winner,
        "hn":     s.hand_number,
        "tn":     s.trick_number,
    }


def ser_event(e: GameEvent) -> dict:
    return {
        "kind":   e.kind,
        "desc":   e.description,
        "player": e.player,
        "pts":    e.points,
        "move":   ser_move(e.move),
        "beats":  e.beats_player,
        "winner": e.winner,
        "result": ser_result(e.result),
        "snap":   ser_snap(e.snapshot),
    }


def ser_event_pov(e: GameEvent, pov: int) -> dict:
    """Event with snapshot masked to pov seat's perspective."""
    return {
        "kind":   e.kind,
        "desc":   e.description,
        "player": e.player,
        "pts":    e.points,
        "move":   ser_move(e.move),
        "beats":  e.beats_player,
        "winner": e.winner,
        "result": ser_result(e.result),
        "snap":   ser_snap_pov(e.snapshot, pov),
    }
