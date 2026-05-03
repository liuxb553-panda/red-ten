"""
Unit test: When leading a new trick (after winning previous trick),
all valid card combos should be available, including triples.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cards import Card, Rank, Suit, _SINGLE_RANK_MAP
from moves import Move, CardType, get_legal_moves


def build_hand(rank_counts: dict):
    """Build a hand with specified rank counts. Each card gets a unique suit."""
    hand = []
    suit_cycle = [Suit.SPADES, Suit.HEARTS, Suit.CLUBS, Suit.DIAMONDS]
    for rank, count in rank_counts.items():
        for i in range(count):
            hand.append(Card(suit_cycle[i % 4], rank))
    return hand


def test_leading_all_combo_types():
    """When leading (current_best=None), every valid combo type should be generated."""
    # Hand: 3 Queens + 2 Aces + 2 Kings + 3 Threes + 1 extra
    hand = build_hand({
        Rank.QUEEN: 3,   # triple Q
        Rank.ACE: 2,     # pair of Aces
        Rank.KING: 2,    # pair of Kings
        Rank.THREE: 4,   # 4-of-a-kind bomb + singles
        Rank.FIVE: 1,    # single
    })

    moves = get_legal_moves(hand, None)  # None = leading

    # Categorize moves
    by_type = {}
    for m in moves:
        if m.is_pass():
            continue
        t = m.type
        if t not in by_type:
            by_type[t] = []
        by_type[t].append(m)

    print(f"Total legal moves (leading): {len(moves)}")
    print(f"  Singles: {len(by_type.get(CardType.SINGLE, []))}")
    print(f"  Pairs:   {len(by_type.get(CardType.PAIR, []))}")
    print(f"  Triples: {len(by_type.get(CardType.TRIPLE, []))}")
    print(f"  Bombs:   {len(by_type.get(CardType.BOMB, []))}")

    # Assertions
    assert CardType.SINGLE in by_type, "FAIL: No single cards available!"
    assert CardType.PAIR in by_type, "FAIL: No pairs available!"
    assert CardType.TRIPLE in by_type, "FAIL: No triples available — TRIPLE Qs should be playable!"
    assert CardType.BOMB in by_type, "FAIL: No bombs available!"

    # Specifically check for triple Qs
    triple_qs = [m for m in by_type[CardType.TRIPLE]
                 if m.cards[0].rank == Rank.QUEEN]
    assert len(triple_qs) > 0, "FAIL: Triple Qs not found in legal moves!"

    # Check rank is correct (not elevated)
    for m in triple_qs:
        expected_rank = _SINGLE_RANK_MAP[int(Rank.QUEEN)]
        assert m.rank == expected_rank, \
            f"FAIL: Triple Qs rank={m.rank}, expected={expected_rank}"

    print("\n[OK] All assertions passed!")


def test_leading_with_pairs():
    """Pairs should be available when leading."""
    hand = build_hand({
        Rank.QUEEN: 2,
        Rank.THREE: 3,
    })
    moves = get_legal_moves(hand, None)
    pairs = [m for m in moves if not m.is_pass() and m.type == CardType.PAIR]
    assert len(pairs) > 0, f"FAIL: Pairs not available when leading, got {len(pairs)}"
    print(f"[OK] Leading pairs test passed: {len(pairs)} pair(s)")


def test_leading_with_bombs():
    """Bombs should be available when leading."""
    hand = build_hand({
        Rank.THREE: 4,
    })
    moves = get_legal_moves(hand, None)
    bombs = [m for m in moves if not m.is_pass() and m.type == CardType.BOMB]
    assert len(bombs) > 0, f"FAIL: Bombs not available when leading, got {len(bombs)}"
    print(f"[OK] Leading bombs test passed: {len(bombs)} bomb(s)")


def test_serialization_roundtrip():
    """Simulate full roundtrip: server Move -> serialized -> client matching."""
    from serializers import ser_card, ser_move

    # Build hand with 3 Qs
    q1 = Card(Suit.SPADES, Rank.QUEEN)
    q2 = Card(Suit.HEARTS, Rank.QUEEN)
    q3 = Card(Suit.CLUBS, Rank.QUEEN)
    hand = [q1, q2, q3, Card(Suit.DIAMONDS, Rank.FIVE)]

    # Generate legal moves (leading)
    moves = get_legal_moves(hand, None)

    # Find the triple Q move
    triple_q_moves = [m for m in moves
                      if not m.is_pass() and m.type == CardType.TRIPLE
                      and m.cards[0].rank == Rank.QUEEN]
    assert len(triple_q_moves) > 0, "FAIL: No triple Q move generated"

    # Serialize as 'your_turn' message (with the fix from room_manager.py)
    your_turn_legal = []
    for i, m in enumerate(moves):
        if m.is_pass():
            your_turn_legal.append({
                "idx": i, "desc": "Pass", "is_pass": True,
                "cards": []
            })
        else:
            your_turn_legal.append({
                "idx": i, "desc": str(m), "is_pass": False,
                "cards": [ser_card(c) for c in m.cards]
            })

    # Simulate client-side matching (JavaScript cardKey logic)
    def cardKey(c):
        return c["rl"] + '|' + c["s"]

    # User selects the 3 Qs from hand
    hand_serialized = [ser_card(c) for c in hand]
    selected_indices = [0, 1, 2]  # 3 Qs
    sel_cards = [hand_serialized[i] for i in selected_indices]
    sel_key = sorted(cardKey(c) for c in sel_cards)
    sel_str = ','.join(sel_key)

    # Try to match against legal moves
    match_found = None
    for m in your_turn_legal:
        if m["is_pass"]:
            continue
        m_cards = m["cards"]
        if len(m_cards) != len(sel_cards):
            continue
        m_key = sorted(cardKey(c) for c in m_cards)
        m_str = ','.join(m_key)
        if m_str == sel_str:
            match_found = m
            break

    if match_found is None:
        print("\nFAIL: Client-side matching failed!")
        print(f"  Selected cards key: {sel_str}")
        print(f"  Selected cards: {[(c['rl'], c['s']) for c in sel_cards]}")
        print(f"\n  Legal moves keys:")
        for m in your_turn_legal:
            if not m["is_pass"]:
                m_key = sorted(cardKey(c) for c in m["cards"])
                print(f"    [{m['desc']}] -> {','.join(m_key)}")
        raise AssertionError("Client matching failed — Play button would be gray!")

    print(f"[OK] Serialization roundtrip passed! Matched: {match_found['desc']}")


def test_3deck_duplicate_rank_matching():
    """With 3 decks, multiple identical cards exist. Rank-based matching must work."""
    # Simulate a hand with 4 Qs (could be from 3 decks)
    q_cards = [
        Card(Suit.SPADES, Rank.QUEEN),
        Card(Suit.SPADES, Rank.QUEEN),   # duplicate — 2nd Q♠
        Card(Suit.SPADES, Rank.QUEEN),   # duplicate — 3rd Q♠
        Card(Suit.HEARTS, Rank.QUEEN),
    ]
    hand = q_cards + [Card(Suit.DIAMONDS, Rank.FIVE)]

    moves = get_legal_moves(hand, None)
    triples = [m for m in moves if not m.is_pass() and m.type == CardType.TRIPLE]

    # With 4 Qs, we should have exactly 1 triple for Q (not C(4,3)=4 combos)
    q_triples = [t for t in triples if t.cards[0].rank == Rank.QUEEN]
    assert len(q_triples) == 1, \
        f"FAIL: Expected 1 triple Q move, got {len(q_triples)}. Duplicate combos not deduplicated!"

    # Serialize and check rank-based matching
    from serializers import ser_card

    your_turn_legal = []
    for i, m in enumerate(moves):
        if m.is_pass():
            your_turn_legal.append({"idx": i, "desc": "Pass", "is_pass": True, "cards": []})
        else:
            your_turn_legal.append({
                "idx": i, "desc": str(m), "is_pass": False,
                "cards": [ser_card(c) for c in m.cards]
            })

    # Simulate user selecting 3 Qs (different specific cards than the move)
    # User selects Q♠₁, Q♠₂, Q♥ (indices 0, 1, 3)
    hand_ser = [ser_card(c) for c in hand]
    sel_cards = [hand_ser[0], hand_ser[1], hand_ser[3]]
    sel_ranks = sorted(c["rl"] for c in sel_cards)
    sel_str = ','.join(sel_ranks)

    # Match by rank labels (new client logic)
    match = None
    for m in your_turn_legal:
        if m["is_pass"]:
            continue
        m_cards = m["cards"]
        if len(m_cards) != len(sel_cards):
            continue
        m_ranks = sorted(c["rl"] for c in m_cards)
        m_str = ','.join(m_ranks)
        if m_str == sel_str:
            match = m
            break

    assert match is not None, \
        f"FAIL: Rank-based matching failed! Selection ranks: {sel_str}"
    print(f"[OK] 3-deck duplicate matching passed: {match['desc']}")


def test_pair_rank_matching():
    """Pairs with duplicate cards should also match by rank."""
    hand = [
        Card(Suit.SPADES, Rank.ACE),
        Card(Suit.SPADES, Rank.ACE),   # duplicate A♠
        Card(Suit.HEARTS, Rank.ACE),
        Card(Suit.DIAMONDS, Rank.FIVE),
    ]
    moves = get_legal_moves(hand, None)
    pairs = [m for m in moves if not m.is_pass() and m.type == CardType.PAIR]
    a_pairs = [p for p in pairs if p.cards[0].rank == Rank.ACE]

    # Only 1 pair of Aces, not C(3,2)=3
    assert len(a_pairs) == 1, \
        f"FAIL: Expected 1 pair of Aces, got {len(a_pairs)}"
    print(f"[OK] Pair deduplication: {len(a_pairs)} pair of Aces (expected 1)")


def test_red_ten_in_normal_bomb():
    """Red ten + 3 regular tens = 4-card ten bomb when leading."""
    hand = [
        Card(Suit.HEARTS, Rank.TEN),     # red ten (heart 10)
        Card(Suit.SPADES, Rank.TEN),
        Card(Suit.CLUBS, Rank.TEN),
        Card(Suit.DIAMONDS, Rank.TEN),
        Card(Suit.DIAMONDS, Rank.FIVE),  # extra single
    ]
    moves = get_legal_moves(hand, None)
    bombs = [m for m in moves if not m.is_pass() and m.type == CardType.BOMB]

    ten_bombs = [b for b in bombs
                 if b.cards[0].rank == Rank.TEN and len(b.cards) == 4]
    assert len(ten_bombs) >= 1, \
        f"FAIL: Expected 4-card ten bomb (with red ten), got {len(ten_bombs)} ten bomb(s)"

    # Rank should be regular ten rank (8), not elevated red ten rank (16)
    for b in ten_bombs:
        expected_rank = _SINGLE_RANK_MAP[int(Rank.TEN)]
        assert b.rank == expected_rank, \
            f"FAIL: Ten bomb rank={b.rank}, expected={expected_rank}"
    print(f"[OK] Red ten in normal bomb: {len(ten_bombs)} ten bomb(s) — rank correct")


if __name__ == "__main__":
    print("=" * 60)
    print("TEST: Leading (current_best=None) — all combos available")
    print("=" * 60)
    test_leading_all_combo_types()

    print("\n" + "=" * 60)
    print("TEST: Leading pairs")
    print("=" * 60)
    test_leading_with_pairs()

    print("\n" + "=" * 60)
    print("TEST: Leading bombs")
    print("=" * 60)
    test_leading_with_bombs()

    print("\n" + "=" * 60)
    print("TEST: Full serialization roundtrip (server -> client)")
    print("=" * 60)
    test_serialization_roundtrip()

    print("\n" + "=" * 60)
    print("TEST: 3-deck duplicate cards — rank-based matching")
    print("=" * 60)
    test_3deck_duplicate_rank_matching()

    print("\n" + "=" * 60)
    print("TEST: Pair deduplication with duplicates")
    print("=" * 60)
    test_pair_rank_matching()

    print("\n" + "=" * 60)
    print("TEST: Red ten in normal 4+ card bomb")
    print("=" * 60)
    test_red_ten_in_normal_bomb()

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
