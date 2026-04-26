from __future__ import annotations
from dataclasses import dataclass
from enum import IntEnum, auto
from typing import List


class Suit(IntEnum):
    CLUBS    = 1
    DIAMONDS = 2
    HEARTS   = 3
    SPADES   = 4
    JOKER    = 5


class Rank(IntEnum):
    THREE       = 3
    FOUR        = 4
    FIVE        = 5
    SIX         = 6
    SEVEN       = 7
    EIGHT       = 8
    NINE        = 9
    TEN         = 10
    JACK        = 11
    QUEEN       = 12
    KING        = 13
    ACE         = 14
    TWO         = 15
    SMALL_JOKER = 16
    BIG_JOKER   = 17

# Sentinel rank for red ten in single-card ordering
RED_TEN_SENTINEL = 18

# Single-card ordering: red ten > big joker > small joker > 2 > A > K > ... > 3
_SINGLE_ORDER: list[int] = [
    RED_TEN_SENTINEL,
    Rank.BIG_JOKER,
    Rank.SMALL_JOKER,
    Rank.TWO,
    Rank.ACE,
    Rank.KING,
    Rank.QUEEN,
    Rank.JACK,
    Rank.TEN,
    Rank.NINE,
    Rank.EIGHT,
    Rank.SEVEN,
    Rank.SIX,
    Rank.FIVE,
    Rank.FOUR,
    Rank.THREE,
]
_SINGLE_RANK_MAP: dict[int, int] = {v: len(_SINGLE_ORDER) - i for i, v in enumerate(_SINGLE_ORDER)}

# Straight ordering: A(high) > K > Q > J > 10 > 9 > ... > 3; A can also be low (=1)
_STRAIGHT_ORDER: list[int] = [
    Rank.ACE,
    Rank.KING,
    Rank.QUEEN,
    Rank.JACK,
    Rank.TEN,
    Rank.NINE,
    Rank.EIGHT,
    Rank.SEVEN,
    Rank.SIX,
    Rank.FIVE,
    Rank.FOUR,
    Rank.THREE,
]
_STRAIGHT_RANK_MAP: dict[int, int] = {v: len(_STRAIGHT_ORDER) - i for i, v in enumerate(_STRAIGHT_ORDER)}


SUIT_SYMBOLS = {
    Suit.CLUBS:    "♣",
    Suit.DIAMONDS: "♦",
    Suit.HEARTS:   "♥",
    Suit.SPADES:   "♠",
    Suit.JOKER:    "",
}

RANK_LABELS = {
    Rank.THREE: "3", Rank.FOUR: "4", Rank.FIVE: "5",
    Rank.SIX: "6", Rank.SEVEN: "7", Rank.EIGHT: "8",
    Rank.NINE: "9", Rank.TEN: "10", Rank.JACK: "J",
    Rank.QUEEN: "Q", Rank.KING: "K", Rank.ACE: "A",
    Rank.TWO: "2",
    Rank.SMALL_JOKER: "小王",
    Rank.BIG_JOKER:   "大王",
}


@dataclass(frozen=True)
class Card:
    suit: Suit
    rank: Rank

    def is_red_ten(self) -> bool:
        return self.suit == Suit.HEARTS and self.rank == Rank.TEN

    def is_big_joker(self) -> bool:
        return self.rank == Rank.BIG_JOKER

    def is_small_joker(self) -> bool:
        return self.rank == Rank.SMALL_JOKER

    def is_joker(self) -> bool:
        return self.rank in (Rank.BIG_JOKER, Rank.SMALL_JOKER)

    def is_special(self) -> bool:
        return self.is_red_ten() or self.is_joker()

    def single_rank(self) -> int:
        key = RED_TEN_SENTINEL if self.is_red_ten() else int(self.rank)
        return _SINGLE_RANK_MAP[key]

    def straight_rank(self, ace_low: bool = False) -> int:
        if self.is_red_ten():
            return _STRAIGHT_RANK_MAP[Rank.TEN]
        if ace_low and self.rank == Rank.ACE:
            return 0
        return _STRAIGHT_RANK_MAP.get(int(self.rank), 0)

    def is_scoring(self) -> bool:
        return self.rank in (Rank.FIVE, Rank.TEN, Rank.KING)

    def score_value(self) -> int:
        if self.rank == Rank.FIVE:
            return 5
        if self.rank in (Rank.TEN, Rank.KING):
            return 10
        return 0

    def __str__(self) -> str:
        if self.rank == Rank.SMALL_JOKER:
            return "小王"
        if self.rank == Rank.BIG_JOKER:
            return "大王"
        return f"{RANK_LABELS[self.rank]}{SUIT_SYMBOLS[self.suit]}"

    def __repr__(self) -> str:
        return str(self)


def build_deck() -> List[Card]:
    """Build 3 standard 54-card decks (162 cards total)."""
    cards: List[Card] = []
    for _ in range(3):
        for suit in (Suit.CLUBS, Suit.DIAMONDS, Suit.HEARTS, Suit.SPADES):
            for rank in range(3, 16):  # 3..15 (THREE..TWO)
                cards.append(Card(Suit(suit), Rank(rank)))
        cards.append(Card(Suit.JOKER, Rank.SMALL_JOKER))
        cards.append(Card(Suit.JOKER, Rank.BIG_JOKER))
    assert len(cards) == 162
    return cards
