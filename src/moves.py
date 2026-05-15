from __future__ import annotations
from dataclasses import dataclass, field
from enum import IntEnum, auto
from typing import List, Optional
from itertools import combinations

from cards import Card, Rank, Suit, _SINGLE_RANK_MAP


class CardType(IntEnum):
    PASS           = 0
    SINGLE         = 1
    PAIR           = 2
    TRIPLE         = 3
    TRIPLE_PAIR    = 4
    STRAIGHT       = 5
    CONSEC_PAIRS   = 6
    BOMB           = 7
    CONSEC_TRIPLES = 8


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
        if t == CardType.CONSEC_TRIPLES:
            return f"consec-triples-{n}"
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
    rank_val = _SINGLE_RANK_MAP[int(c.rank)]
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

    # Normal bomb: 4+ cards of identical rank (no jokers)
    if n < 4:
        return False
    if any(c.is_joker() for c in cards):
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
    """5+ consecutive ranks. A: 常主牌(after K) or 数字1(before 2). 2: only 数字2(before 3)."""
    n = len(cards)
    if n < 5:
        return False
    if any(c.is_joker() for c in cards):
        return False

    has_A = any(c.rank == Rank.ACE for c in cards)
    has_2 = any(c.rank == Rank.TWO for c in cards)

    def is_consec(rs: list[int]) -> bool:
        return rs == list(range(rs[0], rs[0] + n))

    if has_2:
        # 2 must be 数字2. A (if present) must be 数字1 before 2.
        ranks_low = sorted([c.straight_rank(ace_low=True) for c in cards])
        return is_consec(ranks_low)

    # No 2: try A as 常主牌 (ace_low=False)
    ranks_high = sorted([c.straight_rank(ace_low=False) for c in cards])
    return is_consec(ranks_high)


def _straight_lead_rank(cards: list[Card]) -> int:
    """Return the rank of the lowest card in the straight (for comparison)."""
    has_2 = any(c.rank == Rank.TWO for c in cards)
    if has_2:
        return min(c.straight_rank(ace_low=True) for c in cards)
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

    has_A = Rank.ACE in cnt
    has_2 = Rank.TWO in cnt

    if has_2:
        # 2 must be 数字2. A (if present) must be 数字1.
        mapper = lambda r: Card(Suit.CLUBS, r).consec_pair_rank_low()
    else:
        # No 2: A (if present) must be 常主牌 (after K).
        mapper = lambda r: Card(Suit.CLUBS, r).consec_pair_rank_high()

    ranks_sorted = sorted(cnt.keys(), key=mapper)
    for i in range(1, len(ranks_sorted)):
        prev_r = mapper(ranks_sorted[i-1])
        curr_r = mapper(ranks_sorted[i])
        if curr_r - prev_r != 1:
            return False
    return True


def _consec_pairs_lead_rank(cards: list[Card]) -> int:
    from collections import Counter
    cnt = Counter(c.rank for c in cards)
    has_2 = Rank.TWO in cnt
    mapper = (lambda r: Card(Suit.CLUBS, r).consec_pair_rank_low()) if has_2 else \
             (lambda r: Card(Suit.CLUBS, r).consec_pair_rank_high())
    ranks = sorted(cnt.keys(), key=mapper)
    return mapper(ranks[0])


# ---------------------------------------------------------------------------
# Consecutive triples helpers
# ---------------------------------------------------------------------------

def _is_valid_consec_triples(cards: list[Card]) -> bool:
    n = len(cards)
    if n < 6 or n % 3 != 0:
        return False
    if any(c.is_joker() or c.is_red_ten() for c in cards):
        return False
    from collections import Counter
    cnt = Counter(c.rank for c in cards)
    if any(v != 3 for v in cnt.values()):
        return False

    has_A = Rank.ACE in cnt
    has_2 = Rank.TWO in cnt

    if has_2:
        mapper = lambda r: Card(Suit.CLUBS, r).consec_pair_rank_low()
    else:
        mapper = lambda r: Card(Suit.CLUBS, r).consec_pair_rank_high()

    ranks_sorted = sorted(cnt.keys(), key=mapper)
    for i in range(1, len(ranks_sorted)):
        if mapper(ranks_sorted[i]) - mapper(ranks_sorted[i-1]) != 1:
            return False
    return True


def _consec_triples_lead_rank(cards: list[Card]) -> int:
    from collections import Counter
    cnt = Counter(c.rank for c in cards)
    has_2 = Rank.TWO in cnt
    mapper = (lambda r: Card(Suit.CLUBS, r).consec_pair_rank_low()) if has_2 else \
             (lambda r: Card(Suit.CLUBS, r).consec_pair_rank_high())
    ranks = sorted(cnt.keys(), key=mapper)
    return mapper(ranks[0])


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

    if n == 4:
        if _is_valid_consec_pairs(list(cards)):
            return Move(CardType.CONSEC_PAIRS, t, _consec_pairs_lead_rank(list(cards)))
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

    if n == 6:
        if _is_valid_consec_triples(list(cards)):
            return Move(CardType.CONSEC_TRIPLES, t, _consec_triples_lead_rank(list(cards)))

    if n >= 5:
        if _is_valid_straight(list(cards)):
            return Move(CardType.STRAIGHT, t, _straight_lead_rank(list(cards)))
        if _is_valid_consec_pairs(list(cards)):
            return Move(CardType.CONSEC_PAIRS, t, _consec_pairs_lead_rank(list(cards)))
        if n >= 6 and n % 3 == 0:
            if _is_valid_consec_triples(list(cards)):
                return Move(CardType.CONSEC_TRIPLES, t, _consec_triples_lead_rank(list(cards)))
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

    # Consecutive triples
    _add_consec_triple_combos(hand, all_moves, current_best, leading)

    # Bombs (always generated; filtered if following another bomb)
    _add_bomb_combos(hand, all_moves, current_best, leading)

    # Deduplicate by (type, card count, frozenset) — type+count needed
    # because with 3 decks identical cards collapse to same frozenset
    seen: set[tuple] = set()
    unique: list[Move] = []
    for m in all_moves:
        key = (m.type, len(m.cards), frozenset(m.cards))
        if key not in seen:
            seen.add(key)
            unique.append(m)

    return unique


def _add_same_rank_combos(hand, count, ctype, out, current_best, leading):
    from collections import defaultdict
    by_rank: dict[Rank, list[Card]] = defaultdict(list)
    for c in hand:
        by_rank[c.rank].append(c)
    for rank, cards in by_rank.items():
        if len(cards) < count:
            continue
        # Only one combo per rank — all combos of same rank are equivalent
        combo = tuple(list(cards)[:count])
        m = Move(ctype, combo, _SINGLE_RANK_MAP[int(combo[0].rank)])
        if leading or (current_best and m.beats(current_best)):
            out.append(m)


def _add_triple_combos(hand, out, current_best, leading):
    from collections import defaultdict
    by_rank: dict[Rank, list[Card]] = defaultdict(list)
    for c in hand:
        if not c.is_joker():
            by_rank[c.rank].append(c)
    for rank, cards in by_rank.items():
        if len(cards) < 3:
            continue
        # Only one combo per rank
        combo = tuple(list(cards)[:3])
        m = Move(CardType.TRIPLE, combo, _SINGLE_RANK_MAP[int(combo[0].rank)])
        if leading or (current_best and m.beats(current_best)):
            out.append(m)


def _add_triple_pair_combos(hand, out, current_best, leading):
    from collections import defaultdict
    by_rank: dict[Rank, list[Card]] = defaultdict(list)
    for c in hand:
        if not c.is_joker():
            by_rank[c.rank].append(c)

    triple_ranks = [r for r, cards in by_rank.items() if len(cards) >= 3]
    pair_ranks   = [r for r, cards in by_rank.items() if len(cards) >= 2]

    for tr in triple_ranks:
        for triple_combo in combinations(by_rank[tr], 3):
            triple_rank_val = _SINGLE_RANK_MAP[int(triple_combo[0].rank)]
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
    """Generate all valid straights (A-high or A-low, 5+ cards)."""
    eligible = [c for c in hand if not c.is_joker()]
    if len(eligible) < 5:
        return

    from collections import defaultdict

    def gen_from_mapping(ace_low, eligible_cards):
        """Generate straights using a specific ace_low interpretation."""
        by_srank: dict[int, list[Card]] = defaultdict(list)
        for c in eligible_cards:
            sr = c.straight_rank(ace_low=ace_low)
            if sr > 0 or (ace_low and sr >= 0):
                by_srank[sr].append(c)
        sranks = sorted(by_srank.keys())
        max_len = len(sranks)
        for start in range(len(sranks)):
            for length in range(5, max_len + 1):
                if start + length > len(sranks):
                    break
                run = sranks[start:start + length]
                # Check consecutive
                ok = all(run[i+1] == run[i] + 1 for i in range(len(run) - 1))
                if not ok:
                    if run[1] - run[0] != 1:
                        break  # gap at the start, no point checking longer runs
                    continue
                lead_rank = run[0]
                if not leading and current_best and current_best.type == CardType.STRAIGHT:
                    if len(run) != len(current_best.cards):
                        continue
                    if lead_rank <= current_best.rank:
                        continue
                # Pick one card per rank
                card_opts = [by_srank[r][:3] for r in run]
                _cartesian_product_moves(card_opts, CardType.STRAIGHT, lead_rank,
                                         out, current_best, leading)

    # A-high straights (no 2): 10JQKA, 34567, etc.
    high_eligible = [c for c in eligible if c.rank != Rank.TWO]
    gen_from_mapping(ace_low=False, eligible_cards=high_eligible)

    # A-low straights (with 2, A optional before 2): A2345, 23456, etc.
    if any(c.rank == Rank.TWO for c in eligible):
        gen_from_mapping(ace_low=True, eligible_cards=eligible)


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
    """Generate consecutive pair combos — both A-high (KKAA) and A-low (AA22)."""
    eligible = [c for c in hand if not c.is_joker() and not c.is_red_ten()]

    def gen_from_mapping(rank_fn, eligible_cards):
        from collections import defaultdict
        by_srank: dict[int, list[Card]] = defaultdict(list)
        for c in eligible_cards:
            sr = rank_fn(c)
            if sr > 0:
                by_srank[sr].append(c)
        pair_sranks = sorted([sr for sr, cards in by_srank.items() if len(cards) >= 2])
        if len(pair_sranks) < 2:
            return

        for start in range(len(pair_sranks)):
            for length in range(2, len(pair_sranks) - start + 1):
                run = pair_sranks[start:start + length]
                if not all(run[i+1] == run[i] + 1 for i in range(len(run) - 1)):
                    break
                lead_rank = run[0]
                if not leading and current_best and current_best.type == CardType.CONSEC_PAIRS:
                    if len(run) * 2 != len(current_best.cards):
                        continue
                    if lead_rank <= current_best.rank:
                        continue
                opts = [by_srank[r][:3] for r in run]
                pair_opts = [list(combinations(opts_lst, 2)) for opts_lst in opts]
                count = 0
                from itertools import product as iproduct
                for pair_combo in iproduct(*pair_opts):
                    if count >= 100:
                        break
                    cards_tuple = tuple(c for pair in pair_combo for c in pair)
                    m = Move(CardType.CONSEC_PAIRS, cards_tuple, lead_rank)
                    if leading or (current_best and m.beats(current_best)):
                        out.append(m)
                    count += 1

    # A-high (A=常主牌, no 2)
    high_eligible = [c for c in eligible if c.rank != Rank.TWO]
    gen_from_mapping(lambda c: c.consec_pair_rank_high(), high_eligible)

    # A-low (2=数字2, A=数字1 if present)
    if any(c.rank == Rank.TWO for c in eligible):
        gen_from_mapping(lambda c: c.consec_pair_rank_low(), eligible)


def _add_consec_triple_combos(hand, out, current_best, leading):
    """Generate consecutive triple combos — both A-high (KKKAAA) and A-low (AAA222)."""
    eligible = [c for c in hand if not c.is_joker() and not c.is_red_ten()]

    def gen_from_mapping(rank_fn, eligible_cards):
        from collections import defaultdict
        by_srank: dict[int, list[Card]] = defaultdict(list)
        for c in eligible_cards:
            sr = rank_fn(c)
            if sr > 0:
                by_srank[sr].append(c)
        triple_sranks = sorted([sr for sr, cards in by_srank.items() if len(cards) >= 3])
        if len(triple_sranks) < 2:
            return

        for start in range(len(triple_sranks)):
            for length in range(2, len(triple_sranks) - start + 1):
                run = triple_sranks[start:start + length]
                if not all(run[i+1] == run[i] + 1 for i in range(len(run) - 1)):
                    break
                lead_rank = run[0]
                if not leading and current_best and current_best.type == CardType.CONSEC_TRIPLES:
                    if len(run) * 3 != len(current_best.cards):
                        continue
                    if lead_rank <= current_best.rank:
                        continue
                opts = [by_srank[r][:5] for r in run]
                triple_opts = [list(combinations(opts_lst, 3)) for opts_lst in opts]
                count = 0
                from itertools import product as iproduct
                for triple_combo in iproduct(*triple_opts):
                    if count >= 100:
                        break
                    cards_tuple = tuple(c for triple in triple_combo for c in triple)
                    m = Move(CardType.CONSEC_TRIPLES, cards_tuple, lead_rank)
                    if leading or (current_best and m.beats(current_best)):
                        out.append(m)
                    count += 1

    # A-high (A=常主牌, no 2)
    high_eligible = [c for c in eligible if c.rank != Rank.TWO]
    gen_from_mapping(lambda c: c.consec_pair_rank_high(), high_eligible)

    # A-low (2=数字2, A=数字1 if present)
    if any(c.rank == Rank.TWO for c in eligible):
        gen_from_mapping(lambda c: c.consec_pair_rank_low(), eligible)


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

    # Normal bombs: 4+ same rank (no jokers; red tens count as regular tens)
    by_rank: dict[Rank, list[Card]] = defaultdict(list)
    for c in hand:
        if not c.is_joker():
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
