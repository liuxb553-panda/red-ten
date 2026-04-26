from __future__ import annotations
from collections import Counter
from cards import Card, Rank, Suit
from moves import Move, CardType, get_legal_moves, _is_valid_bomb, _bomb_key


def scoring_value(hand: list[Card]) -> int:
    """Total trick-point value of scoring cards in hand."""
    return sum(c.score_value() for c in hand)


def bomb_tier(hand: list[Card]) -> int:
    """
    Best bomb level available in hand (lower = stronger, per bomb hierarchy).
    Returns 99 if no bombs available.
    """
    best = 99
    moves = get_legal_moves(hand, None)
    for m in moves:
        if m.is_bomb() and m.bomb_key:
            level = m.bomb_key[0]
            if level < best:
                best = level
    return best


def best_bomb(hand: list[Card]) -> Move | None:
    """Return the strongest bomb available, or None."""
    moves = get_legal_moves(hand, None)
    bombs = [m for m in moves if m.is_bomb()]
    if not bombs:
        return None
    return min(bombs, key=lambda m: (m.bomb_key[0], -m.bomb_key[1], -m.bomb_key[2]))


def cheapest_winning_move(hand: list[Card], current_best: Move) -> Move | None:
    """
    Return the weakest (cheapest) move from hand that beats current_best,
    or None if no such move exists.
    Cheapest = lowest bomb level for bombs, lowest rank for same type.
    """
    legal = get_legal_moves(hand, current_best)
    candidates = [m for m in legal if not m.is_pass() and m.beats(current_best)]
    if not candidates:
        return None

    # Prefer non-bomb over bomb (preserve bombs)
    non_bombs = [m for m in candidates if not m.is_bomb()]
    if non_bombs:
        return min(non_bombs, key=lambda m: (len(m.cards), m.rank))

    # Must use a bomb — pick the weakest
    return max(candidates, key=lambda m: (m.bomb_key[0], -m.bomb_key[1], -m.bomb_key[2]))


def hand_playability(hand: list[Card]) -> float:
    """
    Heuristic score for how efficiently the hand can be played out.
    Higher = more playable (fewer disconnected singles, more combos).
    Range: roughly 0..1.
    """
    if not hand:
        return 1.0

    n = len(hand)
    # Count how many cards can be grouped into pairs/triples/straights
    moves = get_legal_moves(hand, None)
    max_grouped = max((len(m.cards) for m in moves if not m.is_pass()), default=1)
    return min(1.0, max_grouped / n)


def trick_scoring_value(trick_plays: list[tuple[int, Move]]) -> int:
    """Sum of score values of all cards played in the current trick so far."""
    return sum(c.score_value() for _, m in trick_plays for c in m.cards)


def is_high_value_trick(trick_plays: list[tuple[int, Move]], threshold: int = 10) -> bool:
    return trick_scoring_value(trick_plays) >= threshold


def cards_to_finish(hand: list[Card]) -> int:
    """
    Minimum number of plays (tricks won) needed to empty hand.
    Approximated by finding the largest single-play combo from hand.
    """
    if not hand:
        return 0
    moves = get_legal_moves(hand, None)
    max_play = max((len(m.cards) for m in moves if not m.is_pass()), default=1)
    # Rough lower bound
    return max(1, len(hand) // max(1, max_play))


def best_lead(hand: list[Card]) -> Move:
    """
    Pick a good lead move:
    - Prefer moves that use many cards at once (drain hand faster)
    - Among same-size, prefer moves that are hard to beat
    - Singles/pairs are last resort
    """
    moves = [m for m in get_legal_moves(hand, None) if not m.is_pass() and not m.is_bomb()]
    if not moves:
        # Only bombs or pass — pick weakest bomb
        bombs = [m for m in get_legal_moves(hand, None) if m.is_bomb()]
        if bombs:
            return max(bombs, key=lambda m: (m.bomb_key[0], -m.bomb_key[1]))
        raise RuntimeError("No legal moves when leading")

    # Group by card count (prefer larger plays)
    by_size: dict[int, list[Move]] = {}
    for m in moves:
        by_size.setdefault(len(m.cards), []).append(m)

    max_size = max(by_size)
    # If there's a multi-card play, prefer the largest
    if max_size >= 5:
        candidates = by_size[max_size]
        # Among them, pick the one with the lowest lead rank (hardest for opponents to beat from below)
        return min(candidates, key=lambda m: m.rank)

    # Otherwise prefer pairs > triples > singles, biased toward mid-rank
    for size in sorted(by_size.keys(), reverse=True):
        if size >= 2:
            candidates = by_size[size]
            return min(candidates, key=lambda m: m.rank)

    # Singles: lead lowest
    return min(by_size[1], key=lambda m: m.rank)
