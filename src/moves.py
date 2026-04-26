from __future__ import annotations
from dataclasses import dataclass, field
from enum import IntEnum, auto
from typing import List, Optional
from itertools import combinations

from cards import Card, Rank, Suit


class CardType(IntEnum):
    PASS          = 0
    SINGLE        = 1
    PAIR          = 2
    TRIPLE        = 3
    TRIPLE_PAIR   = 4
    STRAIGHT      = 5
    CONSEC_PAIRS  = 6
    BOMB          = 7


@dataclass(frozen=True)
class Move:
    type: CardType
    cards: tuple[Card, ...]
    # Primary comparison key within same type:
    #   non-bombs: single_rank of the lead card
    #   bombs:     (bomb_level, len(cards), single_rank of card)
    rank: int
    bomb_key: Optional[tuple[int, int, int]] = None  # (level, count, rank) for bombs

    @staticmethod
    def pass_move() -> "Move":
        return Move(CardType.PASS, (), 0)

    def is_pass(self) -> bool:
        return self.type == CardType.PASS

    def is_bomb(self) -> bool:
        return self.type == CardType.BOMB

    def beats(self, other: "Move") -> bool:
        """Return True if self strictly beats other."""
        if other.is_pass():
            return not self.is_pass()
        if self.is_bomb() and not other.is_bomb():
            return True
        if not self.is_bomb() and other.is_bomb():
            return False
        if self.is_bomb() and other.is_bomb():
            # Compare by (level desc, count desc, rank desc) — lower level = stronger
            # bomb_key = (level, count, rank); lower level wins
            assert self.bomb_key and other.bomb_key
            sl, sc, sr = self.bomb_key
            ol, oc, or_ = other.bomb_key
            if sl != ol:
                return sl < ol  # lower level number = stronger bomb
            if sc != oc:
                return sc > oc
            return sr > or_
        # Same non-bomb type — must match type and have higher rank
        if self.type != other.type:
            return False
        if len(self.cards) != len(other.cards):
            return False
        return self.rank > other.rank

    def label(self) -> str:
        if self.is_pass():
            return "pass"
        n = len(self.cards)
        t = self.type
        if t == CardType.SINGLE:
            return "single"
        if t == CardType.PAIR:
            return "pair"
        if t == CardType.TRIPLE:
            return "triple"
        if t == CardType.TRIPLE_PAIR:
            return "triple+pair"
        if t == CardType.STRAIGHT:
            return f"straight-{n}"
        if t == CardType.CONSEC_PAIRS:
            return f"consec-pairs-{n}"
        if t == CardType.BOMB:
            assert self.bomb_key
            level = self.bomb_key[0]
            labels = {1: "3x红十", 7: "3x大王", 8: "3x小王", 11: "2x红十", 12: "2x大王", 13: "2x小王"}
            return labels.get(level, f"{n}-bomb")
        return "unknown"

    def __str__(self) -> str:
        if self.is_pass():
            return "pass"
        cards_str = " ".join(str(c) for c in self.cards)
        return f"{cards_str}  [{self.label()}]"


# ---------------------------------------------------------------------------
# Bomb level table
# ---------------------------------------------------------------------------
# Level 1  = 3x red ten
# Level 2  = 12-card normal bomb
# ...
# Level 8  = 6-card normal bomb
# Level 9  = 3x big joker
# Level 10 = 3x small joker
# Level 11 = 7-card normal bomb
# Level 12 = 6-card normal bomb  (Note: 6-bomb appears BOTH at level 8 and 12 in the doc)
#   Reading the rules more carefully:
#   Order (strongest to weakest):
#     3红十, 12,11,10,9,8张炸弹, 3大王, 3小王, 7张炸弹, 6张炸弹, 2红十, 2大王, 2小王, 5张炸弹, 4张炸弹
#   Levels 1..15:
#     1=3红十, 2=12-bomb, 3=11-bomb, 4=10-bomb, 5=9-bomb, 6=8-bomb,
#     7=3大王, 8=3小王, 9=7-bomb, 10=6-bomb,
#     11=2红十, 12=2大王, 13=2小王, 14=5-bomb, 15=4-bomb

_NORMAL_COUNT_TO_LEVEL = {
    12: 2, 11: 3, 10: 4, 9: 5, 8: 6,
    7: 9, 6: 10, 5: 14, 4: 15,
}

def _bomb_key(cards: tuple[Card, ...]) -> tuple[int, int, int]:
    """Compute (level, count, rank) for a bomb."""
    n = len(cards)
    c = cards[0]

    red_tens   = [x for x in cards if x.is_red_ten()]
    big_jokers = [x for x in cards if x.is_big_joker()]
    sml_jokers = [x for x in cards if x.is_small_joker()]

    if len(red_tens) == 3 and n == 3:
        return (1, 3, 0)
    if len(big_jokers) == 3 and n == 3:
        return (7, 3, 0)
    if len(sml_jokers) == 3 and n == 3:
        return (8, 3, 0)
    if len(red_tens) == 2 and n == 2:
        return (11, 2, 0)
    if len(big_jokers) == 2 and n == 2:
        return (12, 2, 0)
    if len(sml_jokers) == 2 and n == 2:
        return (13, 2, 0)

    # Normal same-rank bomb (all same rank, no jokers/red-tens, or red-ten plays as 10 in normal bomb context)
    level = _NORMAL_COUNT_TO_LEVEL.get(n)
    if level is None:
        raise ValueError(f"Invalid bomb count: {n}")
    rank_val = c.single_rank()
    return (level, n, rank_val)


def _is_valid_bomb(cards: list[Card]) -> bool:
    n = len(cards)
    if n < 2:
        return False
    red_tens   = [c for c in cards if c.is_red_ten()]
    big_jokers = [c for c in cards if c.is_big_joker()]
    sml_jokers = [c for c in cards if c.is_small_joker()]

    # Special bombs: pure joker/red-ten pairs or triples
    if len(red_tens) == n and n in (2, 3):
        return True
    if len(big_jokers) == n and n in (2, 3):
        return True
    if len(sml_jokers) == n and n in (2, 3):
        return True

    # Normal bomb: 4+ cards of identical rank (jokers and red tens not mixed in)
    if n < 4:
        return False
    if any(c.is_joker() or c.is_red_ten() for c in cards):
        return False
    ranks = {c.rank for c in cards}
    return len(ranks) == 1


def _make_bomb(cards: tuple[Card, ...]) -> Move:
    key = _bomb_key(cards)
    rank_val = key[2]
    return Move(CardType.BOMB, cards, rank_val, bomb_key=key)


# ---------------------------------------------------------------------------
# Straight helpers
# ---------------------------------------------------------------------------

def _is_valid_straight(cards: list[Card]) -> bool:
    """5+ consecutive ranks; no jokers; A can be low or high; 2 cannot be high end."""
    n = len(cards)
    if n < 5:
        return False
    if any(c.is_joker() for c in cards):
        return False
    # Treat red tens as 10 in straights
    ranks_high = sorted([c.straight_rank(ace_low=False) for c in cards])
    ranks_low  = sorted([c.straight_rank(ace_low=True)  for c in cards])

    def is_consec(rs: list[int]) -> bool:
        if 0 in rs:  # ace_low gave us a 0 — check as A=low
            non_zero = [r for r in rs if r != 0]
            if not non_zero:
                return False
            # A-2-3-4-5 not valid (2 can't appear); A is rank 0, 3=1?, need to re-examine
            # Actually 2 cannot be in straights at all
            if any(c.rank == Rank.TWO for c in cards):
                return False
            return rs == list(range(min(rs), min(rs) + n))
        return rs == list(range(rs[0], rs[0] + n))

    # 2 cannot be the high end
    if any(c.rank == Rank.TWO for c in cards):
        return False
    if any(c.is_joker() for c in cards):
        return False

    return is_consec(ranks_high) or is_consec(ranks_low)


def _straight_lead_rank(cards: list[Card]) -> int:
    """Return the rank of the lowest card in the straight (for comparison)."""
    if any(c.rank == Rank.ACE for c in cards):
        # Could be A-low straight — use minimum straight_rank(ace_low=True)
        ranks_low = sorted([c.straight_rank(ace_low=True) for c in cards])
        ranks_high = sorted([c.straight_rank(ace_low=False) for c in cards])
        if ranks_low == list(range(ranks_low[0], ranks_low[0] + len(cards))):
            return ranks_low[0]
        return ranks_high[0]
    return min(c.straight_rank(ace_low=False) for c in cards)


# ---------------------------------------------------------------------------
# Consecutive pairs helpers
# ---------------------------------------------------------------------------

def _is_valid_consec_pairs(cards: list[Card]) -> bool:
    n = len(cards)
    if n < 4 or n % 2 != 0:
        return False
    if any(c.is_joker() or c.is_red_ten() for c in cards):
        return False
    from collections import Counter
    cnt = Counter(c.rank for c in cards)
    if any(v != 2 for v in cnt.values()):
        return False
    ranks_sorted = sorted(cnt.keys(), key=lambda r: Card(Suit.CLUBS, r).straight_rank(ace_low=False))
    # Must be strictly consecutive (no gaps)
    for i in range(1, len(ranks_sorted)):
        prev_r = Card(Suit.CLUBS, ranks_sorted[i-1]).straight_rank(ace_low=False)
        curr_r = Card(Suit.CLUBS, ranks_sorted[i]).straight_rank(ace_low=False)
        if curr_r - prev_r != 1:
            return False
    # 2 cannot be part of consecutive pairs
    if Rank.TWO in cnt:
        return False
    return True


def _consec_pairs_lead_rank(cards: list[Card]) -> int:
    from collections import Counter
    cnt = Counter(c.rank for c in cards)
    ranks = sorted(cnt.keys(), key=lambda r: Card(Suit.CLUBS, r).straight_rank(ace_low=False))
    return Card(Suit.CLUBS, ranks[0]).straight_rank(ace_low=False)


# ---------------------------------------------------------------------------
# Move identification
# ---------------------------------------------------------------------------

def identify_move(cards: list[Card]) -> Optional[Move]:
    """Try to identify what move type a set of cards represents. Returns None if invalid."""
    n = len(cards)
    t = tuple(cards)
    if n == 0:
        return Move.pass_move()

    if _is_valid_bomb(list(cards)):
        return _make_bomb(t)

    if n == 1:
        return Move(CardType.SINGLE, t, cards[0].single_rank())

    if n == 2:
        if cards[0].rank == cards[1].rank and not any(c.is_special() for c in cards):
            return Move(CardType.PAIR, t, cards[0].single_rank())
        return None

    if n == 3:
        ranks = {c.rank for c in cards}
        if len(ranks) == 1 and not any(c.is_joker() for c in cards) and not any(c.is_red_ten() for c in cards):
            return Move(CardType.TRIPLE, t, cards[0].single_rank())
        return None

    if n == 5:
        # Could be triple+pair or straight or consec-pairs (4 cards minimum but 5 is valid)
        from collections import Counter
        cnt = Counter(c.rank for c in cards)
        counts = sorted(cnt.values(), reverse=True)
        if counts == [3, 2]:
            triple_rank = [r for r, v in cnt.items() if v == 3][0]
            pair_rank   = [r for r, v in cnt.items() if v == 2][0]
            # Validate: triple cannot be jokers/special for triple+pair
            if not any(c.is_joker() for c in cards):
                tr = Card(Suit.CLUBS, triple_rank).single_rank()
                return Move(CardType.TRIPLE_PAIR, t, tr)
        if _is_valid_straight(list(cards)):
            return Move(CardType.STRAIGHT, t, _straight_lead_rank(list(cards)))
        if _is_valid_consec_pairs(list(cards)):
            return Move(CardType.CONSEC_PAIRS, t, _consec_pairs_lead_rank(list(cards)))
        return None

    if n >= 5:
        if _is_valid_straight(list(cards)):
            return Move(CardType.STRAIGHT, t, _straight_lead_rank(list(cards)))
        if _is_valid_consec_pairs(list(cards)):
            return Move(CardType.CONSEC_PAIRS, t, _consec_pairs_lead_rank(list(cards)))
    return None


# ---------------------------------------------------------------------------
# Legal move generation
# ---------------------------------------------------------------------------

def get_legal_moves(hand: list[Card], current_best: Optional[Move]) -> list[Move]:
    """
    Generate all legal moves from hand.
    If current_best is None (leading), generate all valid card combos.
    If current_best is set, generate all combos that beat it, plus pass.
    Always include all valid bombs (they can beat anything non-bomb, or a weaker bomb).
    """
    leading = current_best is None or current_best.is_pass()
    all_moves: list[Move] = []

    # Always include pass when following
    if not leading:
        all_moves.append(Move.pass_move())

    n = len(hand)

    # Singles
    for card in hand:
        m = Move(CardType.SINGLE, (card,), card.single_rank())
        if leading or (current_best and m.beats(current_best)):
            all_moves.append(m)

    # Pairs
    _add_same_rank_combos(hand, 2, CardType.PAIR, all_moves, current_best, leading)

    # Triples
    _add_triple_combos(hand, all_moves, current_best, leading)

    # Triple + pair
    _add_triple_pair_combos(hand, all_moves, current_best, leading)

    # Straights (5+)
    _add_straight_combos(hand, all_moves, current_best, leading)

    # Consecutive pairs
    _add_consec_pair_combos(hand, all_moves, current_best, leading)

    # Bombs (always generated; filtered if following another bomb)
    _add_bomb_combos(hand, all_moves, current_best, leading)

    # Deduplicate by card frozenset (same cards in different order = same move)
    seen: set[frozenset] = set()
    unique: list[Move] = []
    for m in all_moves:
        key = frozenset(m.cards)
        if key not in seen:
            seen.add(key)
            unique.append(m)

    return unique


def _add_same_rank_combos(hand, count, ctype, out, current_best, leading):
    from collections import defaultdict
    by_rank: dict[Rank, list[Card]] = defaultdict(list)
    for c in hand:
        if not c.is_joker() and not c.is_red_ten():
            by_rank[c.rank].append(c)
    for rank, cards in by_rank.items():
        if len(cards) < count:
            continue
        for combo in combinations(cards, count):
            m = Move(ctype, combo, combo[0].single_rank())
            if leading or (current_best and m.beats(current_best)):
                out.append(m)


def _add_triple_combos(hand, out, current_best, leading):
    from collections import defaultdict
    by_rank: dict[Rank, list[Card]] = defaultdict(list)
    for c in hand:
        if not c.is_joker() and not c.is_red_ten():
            by_rank[c.rank].append(c)
    for rank, cards in by_rank.items():
        if len(cards) < 3:
            continue
        for combo in combinations(cards, 3):
            m = Move(CardType.TRIPLE, combo, combo[0].single_rank())
            if leading or (current_best and m.beats(current_best)):
                out.append(m)


def _add_triple_pair_combos(hand, out, current_best, leading):
    from collections import defaultdict
    by_rank: dict[Rank, list[Card]] = defaultdict(list)
    for c in hand:
        if not c.is_joker() and not c.is_red_ten():
            by_rank[c.rank].append(c)

    triple_ranks = [r for r, cards in by_rank.items() if len(cards) >= 3]
    pair_ranks   = [r for r, cards in by_rank.items() if len(cards) >= 2]

    for tr in triple_ranks:
        for triple_combo in combinations(by_rank[tr], 3):
            triple_rank_val = triple_combo[0].single_rank()
            if not leading and current_best and current_best.type == CardType.TRIPLE_PAIR:
                if triple_rank_val <= current_best.rank:
                    continue
            for pr in pair_ranks:
                if pr == tr:
                    remaining_pair = [c for c in by_rank[pr] if c not in triple_combo]
                    if len(remaining_pair) < 2:
                        continue
                    pair_cards = remaining_pair
                else:
                    pair_cards = by_rank[pr]
                for pair_combo in combinations(pair_cards, 2):
                    cards = triple_combo + pair_combo
                    m = Move(CardType.TRIPLE_PAIR, cards, triple_rank_val)
                    if leading or (current_best and m.beats(current_best)):
                        out.append(m)


def _add_straight_combos(hand, out, current_best, leading):
    """Generate all valid straights of length 5 or more."""
    # Filter out jokers; red tens count as 10
    eligible = [c for c in hand if not c.is_joker() and c.rank != Rank.TWO]
    if len(eligible) < 5:
        return

    # Group by straight_rank (ace high)
    from collections import defaultdict
    by_srank: dict[int, list[Card]] = defaultdict(list)
    for c in eligible:
        sr = c.straight_rank(ace_low=False)
        by_srank[sr].append(c)

    sranks = sorted(by_srank.keys())

    def gen_straights_from(start_idx: int, length: int, min_len: int = 5):
        # Find all consecutive runs starting at start_idx with given length
        run = []
        for i in range(length):
            expected_rank = sranks[start_idx] + i
            # find sranks[start_idx + i] == expected_rank
            if start_idx + i >= len(sranks) or sranks[start_idx + i] != expected_rank:
                return
            run.append(sranks[start_idx + i])
        # Generate all combos picking one card per rank
        _gen_straight_combos_from_ranks(run, by_srank, out, current_best, leading)

    # Try all windows of length 5..len(eligible)
    max_len = len(eligible)
    for start in range(len(sranks)):
        for length in range(5, max_len + 1):
            if start + length > len(sranks):
                break
            # Check if consecutive
            consecutive = True
            for i in range(1, length):
                if sranks[start + i] != sranks[start] + i:
                    consecutive = False
                    break
            if not consecutive:
                break
            run = [sranks[start + i] for i in range(length)]
            _gen_straight_combos_from_ranks(run, by_srank, out, current_best, leading)

    # Also try ace-low straights (A-2-3-4-5 is invalid since 2 excluded; A-3-4-5-6 not valid)
    # A-low: A=0 in straight_rank(ace_low=True); valid A-low straight = A,3,4,5,6? No.
    # A-low means A=rank 0, so a valid straight must be A(0),2,3,4,5 but 2 is excluded.
    # Actually looking at rules: "起始的牌最小是A，此时A相当于1" and example is A-2-3-4-5
    # But 2 is explicitly excluded from straights. So A-low straights are NOT possible.
    # Skip ace-low.


def _gen_straight_combos_from_ranks(run, by_srank, out, current_best, leading):
    lead_rank = run[0]  # lowest rank in straight
    if not leading and current_best and current_best.type == CardType.STRAIGHT:
        if len(run) != len(current_best.cards):
            return
        if lead_rank <= current_best.rank:
            return

    # Pick one card per rank in the run — limit combinations to avoid explosion
    # For large hands, this can be huge. We prune to first 3 cards per rank.
    card_options = [by_srank[r][:3] for r in run]
    _cartesian_product_moves(card_options, CardType.STRAIGHT, lead_rank, out, current_best, leading)


def _cartesian_product_moves(options, ctype, rank_val, out, current_best, leading, max_combos=200):
    from itertools import product as iproduct
    count = 0
    for combo in iproduct(*options):
        if count >= max_combos:
            break
        m = Move(ctype, combo, rank_val)
        if leading or (current_best and m.beats(current_best)):
            out.append(m)
        count += 1


def _add_consec_pair_combos(hand, out, current_best, leading):
    eligible = [c for c in hand if not c.is_joker() and not c.is_red_ten() and c.rank != Rank.TWO]
    from collections import defaultdict
    by_srank: dict[int, list[Card]] = defaultdict(list)
    for c in eligible:
        sr = c.straight_rank(ace_low=False)
        by_srank[sr].append(c)

    # Only ranks where we have >=2 cards
    pair_sranks = sorted([sr for sr, cards in by_srank.items() if len(cards) >= 2])
    if len(pair_sranks) < 2:
        return

    # Find consecutive windows of pair ranks
    for start in range(len(pair_sranks)):
        for length in range(2, len(pair_sranks) - start + 1):
            run = pair_sranks[start:start + length]
            # Check consecutive
            consecutive = all(run[i+1] == run[i] + 1 for i in range(len(run) - 1))
            if not consecutive:
                break
            lead_rank = run[0]
            if not leading and current_best and current_best.type == CardType.CONSEC_PAIRS:
                if len(run) * 2 != len(current_best.cards):
                    continue
                if lead_rank <= current_best.rank:
                    continue
            # Pick 2 cards per rank
            options = [by_srank[r][:3] for r in run]
            pair_options = [list(combinations(opts, 2)) for opts in options]
            count = 0
            from itertools import product as iproduct
            for pair_combo in iproduct(*pair_options):
                if count >= 100:
                    break
                cards = tuple(c for pair in pair_combo for c in pair)
                m = Move(CardType.CONSEC_PAIRS, cards, lead_rank)
                if leading or (current_best and m.beats(current_best)):
                    out.append(m)
                count += 1


def _add_bomb_combos(hand, out, current_best, leading):
    from collections import defaultdict

    # Special: red ten bombs
    red_tens = [c for c in hand if c.is_red_ten()]
    big_jkrs = [c for c in hand if c.is_big_joker()]
    sml_jkrs = [c for c in hand if c.is_small_joker()]

    for group, n_needed, level in [
        (red_tens, 3, 1), (red_tens, 2, 11),
        (big_jkrs, 3, 7), (big_jkrs, 2, 12),
        (sml_jkrs, 3, 8), (sml_jkrs, 2, 13),
    ]:
        if len(group) >= n_needed:
            for combo in combinations(group, n_needed):
                key = (level, n_needed, 0)
                m = Move(CardType.BOMB, combo, 0, bomb_key=key)
                if leading or not current_best or current_best.is_pass() or m.beats(current_best):
                    out.append(m)

    # Normal bombs: 4+ same rank (no jokers, no red tens)
    by_rank: dict[Rank, list[Card]] = defaultdict(list)
    for c in hand:
        if not c.is_joker() and not c.is_red_ten():
            by_rank[c.rank].append(c)

    for rank, cards in by_rank.items():
        n = len(cards)
        if n < 4:
            continue
        for bomb_size in range(4, n + 1):
            if bomb_size not in _NORMAL_COUNT_TO_LEVEL:
                continue
            for combo in combinations(cards, bomb_size):
                m = _make_bomb(combo)
                if leading or not current_best or current_best.is_pass() or m.beats(current_best):
                    out.append(m)
