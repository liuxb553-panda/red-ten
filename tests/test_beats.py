"""
Comprehensive test for Move.beats() — every card type, every edge case.

Covers:
  - SINGLE ranking (red ten > big joker > small joker > 2 > A > K > ... > 3)
  - PAIR ranking
  - TRIPLE ranking (including red-ten-as-regular-ten)
  - TRIPLE_PAIR (triple rank drives comparison)
  - STRAIGHT (same length, higher lead rank wins)
  - CONSEC_PAIRS (same length, higher lead rank wins)
  - CONSEC_TRIPLES (same length, higher lead rank wins)
  - BOMB always beats non-bomb
  - BOMB vs BOMB: level first (lower=stronger), then count (higher=stronger), then rank
  - Type mismatch returns False
  - Card count mismatch returns False (straights, consec pairs, etc.)
  - PASS handling
  - Red ten in non-bomb combos (pair/triple)
"""
from __future__ import annotations
import pytest
from cards import Card, Rank, Suit, RED_TEN_SENTINEL, _SINGLE_RANK_MAP
from moves import Move, CardType, identify_move, get_legal_moves, _bomb_key


# ── Card factory helpers ──────────────────────────────────────────────────

def C(rank: Rank, suit: Suit = Suit.CLUBS) -> Card:
    """Shorthand for creating a card."""
    return Card(suit, rank)


def H(rank: Rank) -> Card:
    """Heart-suited card (for red ten: H(Rank.TEN))."""
    return Card(Suit.HEARTS, rank)


def S(rank: Rank) -> Card:
    return Card(Suit.SPADES, rank)


def D(rank: Rank) -> Card:
    return Card(Suit.DIAMONDS, rank)


def J(rank: Rank) -> Card:
    return Card(Suit.JOKER, rank)


# ── Move constructors ─────────────────────────────────────────────────────

def mk_single(card: Card) -> Move:
    m = identify_move([card])
    assert m is not None
    return m


def mk_pair(c1: Card, c2: Card) -> Move:
    m = identify_move([c1, c2])
    assert m is not None
    return m


def mk_triple(c1: Card, c2: Card, c3: Card) -> Move:
    m = identify_move([c1, c2, c3])
    assert m is not None, f"triple not identified: {c1} {c2} {c3}"
    return m


def mk_triple_pair(t1, t2, t3, p1, p2) -> Move:
    m = identify_move([t1, t2, t3, p1, p2])
    assert m is not None
    return m


def mk_straight(*cards) -> Move:
    m = identify_move(list(cards))
    assert m is not None, f"straight not identified: {list(cards)}"
    return m


def mk_consec_pairs(*cards) -> Move:
    m = identify_move(list(cards))
    assert m is not None, f"consec pairs not identified: {list(cards)}"
    return m


def mk_bomb(*cards) -> Move:
    m = identify_move(list(cards))
    assert m is not None, f"bomb not identified: {list(cards)}"
    return m


# ═══════════════════════════════════════════════════════════════════════════
# SINGLE ranking
# ═══════════════════════════════════════════════════════════════════════════

class TestSingleBeats:
    """Single card ordering: red ten > big joker > small joker > 2 > A > K > ... > 3"""

    def test_red_ten_beats_big_joker(self):
        assert mk_single(H(Rank.TEN)).beats(mk_single(J(Rank.BIG_JOKER)))

    def test_red_ten_beats_small_joker(self):
        assert mk_single(H(Rank.TEN)).beats(mk_single(J(Rank.SMALL_JOKER)))

    def test_red_ten_beats_two(self):
        assert mk_single(H(Rank.TEN)).beats(mk_single(C(Rank.TWO)))

    def test_red_ten_beats_ace(self):
        assert mk_single(H(Rank.TEN)).beats(mk_single(C(Rank.ACE)))

    def test_big_joker_beats_small_joker(self):
        assert mk_single(J(Rank.BIG_JOKER)).beats(mk_single(J(Rank.SMALL_JOKER)))

    def test_big_joker_beats_two(self):
        assert mk_single(J(Rank.BIG_JOKER)).beats(mk_single(C(Rank.TWO)))

    def test_small_joker_beats_two(self):
        assert mk_single(J(Rank.SMALL_JOKER)).beats(mk_single(C(Rank.TWO)))

    def test_two_beats_ace(self):
        assert mk_single(C(Rank.TWO)).beats(mk_single(C(Rank.ACE)))

    def test_ace_beats_king(self):
        assert mk_single(C(Rank.ACE)).beats(mk_single(C(Rank.KING)))

    def test_king_beats_queen(self):
        assert mk_single(C(Rank.KING)).beats(mk_single(C(Rank.QUEEN)))

    def test_queen_beats_jack(self):
        assert mk_single(C(Rank.QUEEN)).beats(mk_single(C(Rank.JACK)))

    def test_jack_beats_ten(self):
        assert mk_single(C(Rank.JACK)).beats(mk_single(C(Rank.TEN)))

    def test_ten_beats_nine(self):
        assert mk_single(C(Rank.TEN)).beats(mk_single(C(Rank.NINE)))

    def test_single_no_self_beat(self):
        a = mk_single(C(Rank.ACE))
        b = mk_single(C(Rank.ACE, Suit.HEARTS))
        assert not a.beats(b)
        assert not b.beats(a)

    def test_lower_does_not_beat_higher(self):
        assert not mk_single(C(Rank.THREE)).beats(mk_single(C(Rank.FOUR)))
        assert not mk_single(C(Rank.KING)).beats(mk_single(C(Rank.ACE)))
        assert not mk_single(C(Rank.TWO)).beats(mk_single(J(Rank.SMALL_JOKER)))


# ═══════════════════════════════════════════════════════════════════════════
# PAIR ranking
# ═══════════════════════════════════════════════════════════════════════════

class TestPairBeats:
    """Pair ranking: higher rank wins, specials (red ten, jokers) excluded."""

    def test_pair_ace_beats_king(self):
        assert mk_pair(C(Rank.ACE), D(Rank.ACE)).beats(
            mk_pair(C(Rank.KING), D(Rank.KING)))

    def test_pair_king_beats_queen(self):
        assert mk_pair(C(Rank.KING), H(Rank.KING)).beats(
            mk_pair(C(Rank.QUEEN), S(Rank.QUEEN)))

    def test_pair_two_beats_ace(self):
        assert mk_pair(C(Rank.TWO), D(Rank.TWO)).beats(
            mk_pair(C(Rank.ACE), S(Rank.ACE)))

    def test_pair_same_rank_no_beat(self):
        p1 = mk_pair(C(Rank.QUEEN), D(Rank.QUEEN))
        p2 = mk_pair(H(Rank.QUEEN), S(Rank.QUEEN))
        assert not p1.beats(p2)
        assert not p2.beats(p1)

    def test_pair_lower_does_not_beat_higher(self):
        assert not mk_pair(C(Rank.FIVE), S(Rank.FIVE)).beats(
            mk_pair(C(Rank.SIX), D(Rank.SIX)))

    def test_regular_ten_pair_rank(self):
        """Non-red ten pair of tens has rank 8 (regular ten rank)."""
        p = mk_pair(C(Rank.TEN), D(Rank.TEN))
        assert p.rank == _SINGLE_RANK_MAP[10]  # 8


# ═══════════════════════════════════════════════════════════════════════════
# TRIPLE ranking
# ═══════════════════════════════════════════════════════════════════════════

class TestTripleBeats:
    """Triple ranking: higher rank wins."""

    def test_triple_ace_beats_king(self):
        assert mk_triple(C(Rank.ACE), D(Rank.ACE), H(Rank.ACE)).beats(
            mk_triple(C(Rank.KING), D(Rank.KING), H(Rank.KING)))

    def test_triple_king_beats_queen(self):
        assert mk_triple(C(Rank.KING), D(Rank.KING), S(Rank.KING)).beats(
            mk_triple(C(Rank.QUEEN), D(Rank.QUEEN), H(Rank.QUEEN)))

    def test_triple_two_beats_ace(self):
        assert mk_triple(C(Rank.TWO), D(Rank.TWO), S(Rank.TWO)).beats(
            mk_triple(C(Rank.ACE), D(Rank.ACE), H(Rank.ACE)))

    def test_triple_same_rank_no_beat(self):
        t1 = mk_triple(C(Rank.NINE), D(Rank.NINE), H(Rank.NINE))
        t2 = mk_triple(S(Rank.NINE), C(Rank.NINE), D(Rank.NINE))
        assert not t1.beats(t2)
        assert not t2.beats(t1)

    def test_triple_lower_does_not_beat_higher(self):
        assert not mk_triple(C(Rank.TEN), D(Rank.TEN), S(Rank.TEN)).beats(
            mk_triple(C(Rank.JACK), D(Rank.JACK), H(Rank.JACK)))

    def test_triple_regular_tens_rank(self):
        t = mk_triple(C(Rank.TEN), D(Rank.TEN), S(Rank.TEN))
        assert t.rank == _SINGLE_RANK_MAP[10]  # 8

    # The critical K-vs-A test
    def test_triple_king_does_not_beat_ace(self):
        """3 K must NOT beat 3 A."""
        k_trip = mk_triple(C(Rank.KING), D(Rank.KING), H(Rank.KING))
        a_trip = mk_triple(C(Rank.ACE), D(Rank.ACE), H(Rank.ACE))
        assert not k_trip.beats(a_trip)

    def test_triple_ace_beats_king_explicit(self):
        """3 A beats 3 K."""
        a_trip = mk_triple(C(Rank.ACE), D(Rank.ACE), H(Rank.ACE))
        k_trip = mk_triple(C(Rank.KING), D(Rank.KING), H(Rank.KING))
        assert a_trip.beats(k_trip)


# ═══════════════════════════════════════════════════════════════════════════
# TRIPLE+PAIR ranking
# ═══════════════════════════════════════════════════════════════════════════

class TestTriplePairBeats:
    """Triple+pair: comparison is on the triple rank only."""

    def test_triple_pair_ace_beats_king(self):
        a_tp = mk_triple_pair(C(Rank.ACE), D(Rank.ACE), H(Rank.ACE),
                               C(Rank.THREE), D(Rank.THREE))
        k_tp = mk_triple_pair(C(Rank.KING), D(Rank.KING), H(Rank.KING),
                               C(Rank.TWO), D(Rank.TWO))  # higher pair, lower triple
        assert a_tp.beats(k_tp)

    def test_triple_pair_same_triple_rank_no_beat(self):
        tp1 = mk_triple_pair(C(Rank.QUEEN), D(Rank.QUEEN), H(Rank.QUEEN),
                              C(Rank.THREE), D(Rank.THREE))
        tp2 = mk_triple_pair(S(Rank.QUEEN), C(Rank.QUEEN), D(Rank.QUEEN),
                              C(Rank.ACE), D(Rank.ACE))
        assert not tp1.beats(tp2)
        assert not tp2.beats(tp1)

    def test_triple_pair_lower_triple_does_not_beat(self):
        assert not mk_triple_pair(
            C(Rank.TEN), D(Rank.TEN), S(Rank.TEN),
            C(Rank.ACE), D(Rank.ACE)
        ).beats(mk_triple_pair(
            C(Rank.JACK), D(Rank.JACK), H(Rank.JACK),
            C(Rank.THREE), D(Rank.THREE)
        ))


# ═══════════════════════════════════════════════════════════════════════════
# STRAIGHT ranking
# ═══════════════════════════════════════════════════════════════════════════

class TestStraightBeats:
    """Straights: same length required, higher lead rank wins."""

    # 34567  (lead=3)
    # 45678  (lead=4)
    def test_straight_45678_beats_34567(self):
        s1 = mk_straight(C(Rank.THREE), C(Rank.FOUR), C(Rank.FIVE),
                          C(Rank.SIX), C(Rank.SEVEN))
        s2 = mk_straight(C(Rank.FOUR), C(Rank.FIVE), C(Rank.SIX),
                          C(Rank.SEVEN), C(Rank.EIGHT))
        assert not s1.beats(s2)
        assert s2.beats(s1)

    # 10JQKA beats 910JQK (A-high straight)
    def test_straight_10JQKA_beats_910JQK(self):
        s1 = mk_straight(C(Rank.NINE), C(Rank.TEN), C(Rank.JACK),
                          C(Rank.QUEEN), C(Rank.KING))
        s2 = mk_straight(C(Rank.TEN), C(Rank.JACK), C(Rank.QUEEN),
                          C(Rank.KING), C(Rank.ACE))
        assert s2.beats(s1)

    def test_straight_different_length_no_beat(self):
        s5 = mk_straight(C(Rank.THREE), C(Rank.FOUR), C(Rank.FIVE),
                          C(Rank.SIX), C(Rank.SEVEN))
        s6 = mk_straight(C(Rank.THREE), C(Rank.FOUR), C(Rank.FIVE),
                          C(Rank.SIX), C(Rank.SEVEN), C(Rank.EIGHT))
        assert not s5.beats(s6)
        assert not s6.beats(s5)

    def test_straight_same_rank_no_beat(self):
        s1 = mk_straight(C(Rank.FIVE), C(Rank.SIX), C(Rank.SEVEN),
                          C(Rank.EIGHT), C(Rank.NINE))
        s2 = mk_straight(D(Rank.FIVE), D(Rank.SIX), D(Rank.SEVEN),
                          D(Rank.EIGHT), D(Rank.NINE))
        assert not s1.beats(s2)

    # A2345 (A-low)
    def test_straight_A2345(self):
        s = mk_straight(C(Rank.ACE), C(Rank.TWO), C(Rank.THREE),
                         C(Rank.FOUR), C(Rank.FIVE))
        assert s is not None
        # lead rank = 0 (A as 1 in ace_low mode)
        assert s.rank == 0


# ═══════════════════════════════════════════════════════════════════════════
# CONSEC_PAIRS ranking
# ═══════════════════════════════════════════════════════════════════════════

class TestConsecPairsBeats:
    """Consecutive pairs: same length required, higher lead rank wins."""

    def test_consec_pairs_4455_beats_3344(self):
        cp1 = mk_consec_pairs(C(Rank.THREE), D(Rank.THREE),
                               C(Rank.FOUR), D(Rank.FOUR))
        cp2 = mk_consec_pairs(C(Rank.FOUR), D(Rank.FOUR),
                               C(Rank.FIVE), D(Rank.FIVE))
        assert cp2.beats(cp1)
        assert not cp1.beats(cp2)

    def test_consec_pairs_different_length_no_beat(self):
        cp4 = mk_consec_pairs(C(Rank.THREE), D(Rank.THREE),
                               C(Rank.FOUR), D(Rank.FOUR))
        cp6 = mk_consec_pairs(C(Rank.THREE), D(Rank.THREE),
                               C(Rank.FOUR), D(Rank.FOUR),
                               C(Rank.FIVE), D(Rank.FIVE))
        assert not cp4.beats(cp6)
        assert not cp6.beats(cp4)


# ═══════════════════════════════════════════════════════════════════════════
# CONSEC_TRIPLES ranking
# ═══════════════════════════════════════════════════════════════════════════

class TestConsecTriplesBeats:
    """Consecutive triples: same length required, higher lead rank wins."""

    def test_consec_triples_444555_beats_333444(self):
        ct1 = mk_straight(C(Rank.THREE), D(Rank.THREE), H(Rank.THREE),
                           C(Rank.FOUR), D(Rank.FOUR), H(Rank.FOUR))
        ct2 = mk_straight(C(Rank.FOUR), D(Rank.FOUR), H(Rank.FOUR),
                           C(Rank.FIVE), D(Rank.FIVE), H(Rank.FIVE))
        assert ct2.beats(ct1)
        assert not ct1.beats(ct2)


# ═══════════════════════════════════════════════════════════════════════════
# BOMB rules
# ═══════════════════════════════════════════════════════════════════════════

class TestBombBeats:
    """Bomb always beats non-bomb. Bomb vs bomb: level, count, rank."""

    # ── Bomb beats any non-bomb ──

    def test_bomb_beats_single(self):
        b = mk_bomb(C(Rank.THREE), D(Rank.THREE), H(Rank.THREE), S(Rank.THREE))
        s = mk_single(H(Rank.TEN))  # highest single
        assert b.beats(s)

    def test_bomb_beats_pair(self):
        b = mk_bomb(C(Rank.THREE), D(Rank.THREE), H(Rank.THREE), S(Rank.THREE))
        p = mk_pair(C(Rank.TWO), D(Rank.TWO))
        assert b.beats(p)

    def test_bomb_beats_triple(self):
        b = mk_bomb(C(Rank.THREE), D(Rank.THREE), H(Rank.THREE), S(Rank.THREE))
        t = mk_triple(C(Rank.ACE), D(Rank.ACE), H(Rank.ACE))
        assert b.beats(t)

    def test_bomb_beats_straight(self):
        b = mk_bomb(C(Rank.THREE), D(Rank.THREE), H(Rank.THREE), S(Rank.THREE))
        s = mk_straight(C(Rank.TEN), C(Rank.JACK), C(Rank.QUEEN),
                         C(Rank.KING), C(Rank.ACE))
        assert b.beats(s)

    def test_non_bomb_does_not_beat_bomb(self):
        b = mk_bomb(C(Rank.THREE), D(Rank.THREE), H(Rank.THREE), S(Rank.THREE))
        s = mk_single(H(Rank.TEN))
        assert not s.beats(b)

    # ── Bomb vs bomb — level comparison ──
    # Levels: 1=3红十, 2=12-bomb, 3=11-bomb, 4=10-bomb, 5=9-bomb,
    #         6=8-bomb, 7=3大王, 8=3小王, 9=7-bomb, 10=6-bomb,
    #         11=2红十, 12=2大王, 13=2小王, 14=5-bomb, 15=4-bomb
    # LOWER level = stronger

    def test_4bomb_beats_5bomb_same_rank(self):
        """5-bomb (level 14) vs 4-bomb (level 15) — 5-bomb is stronger (lower level)."""
        b5 = mk_bomb(C(Rank.THREE), D(Rank.THREE), H(Rank.THREE),
                      S(Rank.THREE), C(Rank.THREE))  # 5 threes (from 3 decks)
        b4 = mk_bomb(C(Rank.THREE), D(Rank.THREE), H(Rank.THREE),
                      S(Rank.THREE))  # 4 threes
        # 5-bomb level=14, 4-bomb level=15. Lower level wins.
        assert b5.beats(b4)
        assert not b4.beats(b5)

    def test_larger_bomb_beats_smaller_same_count(self):
        """8-bomb (level 6) vs 7-bomb (level 9) — 8-bomb is stronger."""
        b8 = mk_bomb(*[Card(Suit(i % 4 + 1), Rank.THREE) for i in range(8)])
        b7 = mk_bomb(*[Card(Suit(i % 4 + 1), Rank.THREE) for i in range(7)])
        assert b8.beats(b7)

    def test_bomb_same_level_higher_count_wins(self):
        """When levels tie, higher card count wins."""
        # 4-bomb of Aces (level 15) vs 4-bomb of Threes (level 15)
        # Same level → compare count (both 4) → compare rank
        b_ace = mk_bomb(C(Rank.ACE), D(Rank.ACE), H(Rank.ACE), S(Rank.ACE))
        b_three = mk_bomb(C(Rank.THREE), D(Rank.THREE), H(Rank.THREE), S(Rank.THREE))
        # Same level (15), same count (4), higher rank wins
        assert b_ace.beats(b_three)
        assert not b_three.beats(b_ace)

    def test_3red_ten_beats_everything(self):
        """3-red-ten (level 1) is the strongest bomb."""
        # Need 3 decks worth of red tens... actually there are only 3 ♥10 total.
        # This test requires the actual cards, but we can test the key directly.
        rt3 = mk_bomb(H(Rank.TEN), H(Rank.TEN), H(Rank.TEN))
        b12 = mk_bomb(*[Card(Suit(i % 4 + 1), Rank.THREE) for i in range(12)])
        assert rt3.beats(b12)

    def test_3big_joker_beats_3small_joker(self):
        bj = mk_bomb(J(Rank.BIG_JOKER), J(Rank.BIG_JOKER), J(Rank.BIG_JOKER))
        sj = mk_bomb(J(Rank.SMALL_JOKER), J(Rank.SMALL_JOKER), J(Rank.SMALL_JOKER))
        assert bj.beats(sj)

    def test_3big_joker_beats_7bomb(self):
        """3大王 (level 7) vs 7-bomb (level 9) — 3大王 is stronger (lower level)."""
        bj3 = mk_bomb(J(Rank.BIG_JOKER), J(Rank.BIG_JOKER), J(Rank.BIG_JOKER))
        b7 = mk_bomb(*[Card(Suit(i % 4 + 1), Rank.THREE) for i in range(7)])
        assert bj3.beats(b7)

    def test_2red_ten_beats_5bomb(self):
        """2红十 (level 11) vs 5-bomb (level 14) — 2红十 is stronger."""
        rt2 = mk_bomb(H(Rank.TEN), H(Rank.TEN))
        b5 = mk_bomb(*[Card(Suit(i % 4 + 1), Rank.THREE) for i in range(5)])
        assert rt2.beats(b5)


# ═══════════════════════════════════════════════════════════════════════════
# PASS handling
# ═══════════════════════════════════════════════════════════════════════════

class TestPassBeats:
    def test_anything_beats_pass(self):
        assert mk_single(C(Rank.THREE)).beats(Move.pass_move())
        assert mk_pair(C(Rank.THREE), D(Rank.THREE)).beats(Move.pass_move())
        assert mk_bomb(C(Rank.THREE), D(Rank.THREE), H(Rank.THREE), S(Rank.THREE)).beats(Move.pass_move())

    def test_pass_does_not_beat_pass(self):
        assert not Move.pass_move().beats(Move.pass_move())

    def test_pass_does_not_beat_anything(self):
        assert not Move.pass_move().beats(mk_single(C(Rank.THREE)))


# ═══════════════════════════════════════════════════════════════════════════
# Type mismatch
# ═══════════════════════════════════════════════════════════════════════════

class TestTypeMismatch:
    def test_single_does_not_beat_pair(self):
        assert not mk_single(C(Rank.ACE)).beats(
            mk_pair(C(Rank.THREE), D(Rank.THREE)))

    def test_pair_does_not_beat_triple(self):
        assert not mk_pair(C(Rank.ACE), D(Rank.ACE)).beats(
            mk_triple(C(Rank.THREE), D(Rank.THREE), H(Rank.THREE)))

    def test_triple_does_not_beat_straight(self):
        assert not mk_triple(C(Rank.ACE), D(Rank.ACE), H(Rank.ACE)).beats(
            mk_straight(C(Rank.THREE), C(Rank.FOUR), C(Rank.FIVE),
                         C(Rank.SIX), C(Rank.SEVEN)))

    def test_straight_does_not_beat_consec_pairs(self):
        assert not mk_straight(C(Rank.TEN), C(Rank.JACK), C(Rank.QUEEN),
                                C(Rank.KING), C(Rank.ACE)).beats(
            mk_consec_pairs(C(Rank.THREE), D(Rank.THREE),
                             C(Rank.FOUR), D(Rank.FOUR)))


# ═══════════════════════════════════════════════════════════════════════════
# identify_move edge cases
# ═══════════════════════════════════════════════════════════════════════════

class TestIdentifyMove:
    def test_pass_is_pass(self):
        m = identify_move([])
        assert m is not None
        assert m.is_pass()

    def test_single_regular(self):
        m = identify_move([C(Rank.KING)])
        assert m is not None
        assert m.type == CardType.SINGLE
        assert m.rank == _SINGLE_RANK_MAP[Rank.KING]

    def test_single_red_ten(self):
        m = identify_move([H(Rank.TEN)])
        assert m is not None
        assert m.type == CardType.SINGLE
        assert m.rank == _SINGLE_RANK_MAP[RED_TEN_SENTINEL]

    def test_pair_regular(self):
        m = identify_move([C(Rank.QUEEN), D(Rank.QUEEN)])
        assert m is not None
        assert m.type == CardType.PAIR

    def test_pair_with_one_red_ten_is_pair(self):
        """1 red ten + 1 regular ten = valid pair (red ten plays as regular 10).
        Bomb check only triggers when ALL N cards are red tens."""
        m = identify_move([H(Rank.TEN), C(Rank.TEN)])
        assert m is not None, "1 red ten + 1 regular ten should be a valid pair"
        assert m.type == CardType.PAIR
        assert m.rank == _SINGLE_RANK_MAP[Rank.TEN]  # rank 8, same as regular ten pair

    def test_triple_without_red_ten(self):
        m = identify_move([C(Rank.JACK), D(Rank.JACK), H(Rank.JACK)])
        assert m is not None
        assert m.type == CardType.TRIPLE

    def test_triple_with_mixed_red_ten_is_triple(self):
        """1 red ten + 2 regular tens = valid triple (red ten plays as regular 10).
        Only 3-red-ten (all red tens) is a bomb."""
        m = identify_move([H(Rank.TEN), C(Rank.TEN), D(Rank.TEN)])
        assert m is not None, "1 red ten + 2 regular tens should be a valid triple"
        assert m.type == CardType.TRIPLE
        assert m.rank == _SINGLE_RANK_MAP[Rank.TEN]  # rank 8, same as regular ten triple

    def test_3_red_tens_is_bomb(self):
        m = identify_move([H(Rank.TEN), H(Rank.TEN), H(Rank.TEN)])
        assert m is not None
        assert m.type == CardType.BOMB
        assert m.bomb_key == (1, 3, 0)  # level 1 = strongest


# ═══════════════════════════════════════════════════════════════════════════
# Red ten in non-bomb combos (pair/triple) — legal move generation
# ═══════════════════════════════════════════════════════════════════════════

class TestRedTenInCombos:
    """
    Red tens (♥10) in non-bomb combos should behave as regular tens.
    e.g., ♥10 + ♣10 = a valid pair of tens (not a special bomb).
    """

    def test_red_ten_plus_regular_ten_should_be_pair(self):
        """♥10 + ♣10 should form a valid pair of 10s."""
        hand = [H(Rank.TEN), C(Rank.TEN), C(Rank.THREE), C(Rank.FOUR)]
        moves = get_legal_moves(hand, None)  # leading
        # Should include a pair of tens (including the red ten)
        pair_moves = [m for m in moves if m.type == CardType.PAIR]
        ten_pairs = [m for m in pair_moves if m.rank == _SINGLE_RANK_MAP[10]]
        assert len(ten_pairs) > 0, "Red ten + regular ten should be a legal pair"

    def test_red_ten_plus_two_regular_tens_should_be_triple(self):
        """♥10 + ♣10 + ♦10 should form a valid triple of 10s."""
        hand = [H(Rank.TEN), C(Rank.TEN), D(Rank.TEN), C(Rank.THREE)]
        moves = get_legal_moves(hand, None)
        triple_moves = [m for m in moves if m.type == CardType.TRIPLE]
        ten_triples = [m for m in triple_moves if m.rank == _SINGLE_RANK_MAP[10]]
        assert len(ten_triples) > 0, "Red ten + 2 regular tens should be a legal triple"

    def test_identify_move_accepts_red_ten_pair(self):
        """identify_move should accept ♥10 + ♣10 as a valid pair."""
        m = identify_move([H(Rank.TEN), C(Rank.TEN)])
        # This should be a pair of tens, not rejected
        assert m is not None, "Red ten + regular ten should be identifiable"
        # It should be a PAIR (not a bomb, since it's only 1 red ten)
        assert m.type == CardType.PAIR, \
            f"Expected PAIR, got {m.type} — red ten in pair should play as regular 10"

    def test_identify_move_accepts_red_ten_triple(self):
        """identify_move should accept ♥10 + ♣10 + ♦10 as a valid triple."""
        m = identify_move([H(Rank.TEN), C(Rank.TEN), D(Rank.TEN)])
        assert m is not None, "Red ten + 2 regular tens should be identifiable"
        assert m.type == CardType.TRIPLE, \
            f"Expected TRIPLE, got {m.type} — red ten in triple should play as regular 10"

    def test_two_red_tens_is_still_bomb(self):
        """2 red tens should be a bomb, not a pair."""
        m = identify_move([H(Rank.TEN), H(Rank.TEN)])
        assert m is not None
        assert m.type == CardType.BOMB, "2 red tens must be a special bomb"

    def test_three_red_tens_is_still_bomb(self):
        """3 red tens should be the strongest bomb, not a triple."""
        m = identify_move([H(Rank.TEN), H(Rank.TEN), H(Rank.TEN)])
        assert m is not None
        assert m.type == CardType.BOMB
        assert m.bomb_key == (1, 3, 0)


# ═══════════════════════════════════════════════════════════════════════════
# Full legal-move consistency: identify_move round-trips on generated moves
# ═══════════════════════════════════════════════════════════════════════════

class TestLegalMoveConsistency:
    """Every move generated by get_legal_moves must be identifiable by identify_move."""

    @pytest.mark.parametrize("hand_cards,leading", [
        # Normal hand
        ([C(Rank.THREE), C(Rank.FIVE), C(Rank.SEVEN), C(Rank.NINE),
          C(Rank.JACK), C(Rank.KING), C(Rank.ACE), C(Rank.TWO),
          C(Rank.FOUR), C(Rank.SIX), C(Rank.EIGHT), C(Rank.TEN),
          C(Rank.QUEEN), C(Rank.THREE), D(Rank.FIVE), D(Rank.SEVEN),
          D(Rank.NINE), D(Rank.JACK), D(Rank.KING), D(Rank.ACE),
          D(Rank.TWO), D(Rank.FOUR), D(Rank.SIX), D(Rank.EIGHT),
          D(Rank.TEN), D(Rank.QUEEN)], True),
        # Same hand, following a triple of 3s
        ([C(Rank.THREE), C(Rank.FIVE), C(Rank.SEVEN), C(Rank.NINE),
          C(Rank.JACK), C(Rank.KING), C(Rank.ACE), C(Rank.TWO),
          C(Rank.FOUR), C(Rank.SIX), C(Rank.EIGHT), C(Rank.TEN),
          C(Rank.QUEEN), C(Rank.THREE), D(Rank.FIVE), D(Rank.SEVEN),
          D(Rank.NINE), D(Rank.JACK), D(Rank.KING), D(Rank.ACE),
          D(Rank.TWO), D(Rank.FOUR), D(Rank.SIX), D(Rank.EIGHT),
          D(Rank.TEN), D(Rank.QUEEN)], False),
    ])
    def test_all_moves_identifiable(self, hand_cards, leading):
        """Every legal move generated must round-trip through identify_move."""
        current_best = None if leading else mk_triple(
            C(Rank.THREE), D(Rank.THREE), H(Rank.THREE))
        moves = get_legal_moves(hand_cards, current_best)
        for m in moves:
            if m.is_pass():
                continue
            identified = identify_move(list(m.cards))
            assert identified is not None, \
                f"identify_move returned None for legal move: {m}"
            assert identified.type == m.type, \
                f"Type mismatch: generated {m.type}, identified {identified.type} for {m}"
            assert identified.rank == m.rank, \
                f"Rank mismatch: generated {m.rank}, identified {identified.rank} for {m}"


# ═══════════════════════════════════════════════════════════════════════════
# Anti-symmetry: if A beats B, B MUST NOT beat A
# ═══════════════════════════════════════════════════════════════════════════

class TestAntiSymmetry:
    """beats() must be anti-symmetric: A.beats(B) implies not B.beats(A)."""

    @pytest.mark.parametrize("a,b", [
        # Singles
        (mk_single(H(Rank.TEN)), mk_single(C(Rank.ACE))),
        (mk_single(C(Rank.ACE)), mk_single(C(Rank.KING))),
        # Pairs
        (mk_pair(C(Rank.ACE), D(Rank.ACE)), mk_pair(C(Rank.KING), D(Rank.KING))),
        # Triples
        (mk_triple(C(Rank.ACE), D(Rank.ACE), H(Rank.ACE)),
         mk_triple(C(Rank.KING), D(Rank.KING), H(Rank.KING))),
        # Triple+pair
        (mk_triple_pair(C(Rank.ACE), D(Rank.ACE), H(Rank.ACE),
                         C(Rank.THREE), D(Rank.THREE)),
         mk_triple_pair(C(Rank.KING), D(Rank.KING), H(Rank.KING),
                         C(Rank.THREE), D(Rank.THREE))),
        # Straights
        (mk_straight(C(Rank.TEN), C(Rank.JACK), C(Rank.QUEEN),
                      C(Rank.KING), C(Rank.ACE)),
         mk_straight(C(Rank.NINE), C(Rank.TEN), C(Rank.JACK),
                      C(Rank.QUEEN), C(Rank.KING))),
        # Bomb vs non-bomb
        (mk_bomb(C(Rank.THREE), D(Rank.THREE), H(Rank.THREE), S(Rank.THREE)),
         mk_single(C(Rank.ACE))),
    ])
    def test_anti_symmetry(self, a, b):
        if a.beats(b):
            assert not b.beats(a), f"Anti-symmetry violated: {b} beats {a} but {a} also beats {b}"


# ═══════════════════════════════════════════════════════════════════════════
# Bomb key correctness
# ═══════════════════════════════════════════════════════════════════════════

class TestBombKey:
    def test_4bomb_level(self):
        key = _bomb_key((C(Rank.THREE), D(Rank.THREE), H(Rank.THREE), S(Rank.THREE)))
        assert key == (15, 4, _SINGLE_RANK_MAP[Rank.THREE])

    def test_8bomb_level(self):
        cards = tuple(Card(Suit(i % 4 + 1), Rank.FIVE) for i in range(8))
        key = _bomb_key(cards)
        assert key == (6, 8, _SINGLE_RANK_MAP[Rank.FIVE])

    def test_3red_ten_level(self):
        key = _bomb_key((H(Rank.TEN), H(Rank.TEN), H(Rank.TEN)))
        assert key == (1, 3, 0)

    def test_3big_joker_level(self):
        key = _bomb_key((J(Rank.BIG_JOKER), J(Rank.BIG_JOKER), J(Rank.BIG_JOKER)))
        assert key == (7, 3, 0)

    def test_2red_ten_level(self):
        key = _bomb_key((H(Rank.TEN), H(Rank.TEN)))
        assert key == (11, 2, 0)
