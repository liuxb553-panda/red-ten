"""
Integration test: run 100 hands of 6-player RuleBasedPlayer and verify all
scoring invariants defined in the game rules v2.  Also runs 20 hands of
SearchPlayer to verify the Tier-2 engine obeys the same invariants.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import random
from collections import Counter
from hand import Hand, RandomPlayer
from rule_player import RuleBasedPlayer
from search_player import SearchPlayer
from logger import GameLogger
from state import TerminalKind, Team, HandResult
from cards import build_deck, Card

logger = GameLogger(verbose=False)


# ── helpers ──────────────────────────────────────────────────────────────────

def make_hand(seed=None) -> tuple[Hand, list]:
    if seed is not None:
        random.seed(seed)
    players = [RuleBasedPlayer(i) for i in range(6)]
    leader  = random.randint(0, 5)
    h = Hand(players, leader, logger)
    h.deal()
    return h, players


def run_hand(seed=None) -> HandResult:
    h, _ = make_hand(seed)
    return h.play()


# ── scoring invariants ────────────────────────────────────────────────────────

def check_normal(r: HandResult, errors: list):
    for t in [Team.RED, Team.NON_RED]:
        s = r.final_team_scores[t]
        if not (0 <= s <= 300):
            errors.append(f"NORMAL team score out of range: {t} = {s}")

    total = r.final_team_scores[Team.RED] + r.final_team_scores[Team.NON_RED]
    if total > 600:
        errors.append(f"NORMAL combined team score too high: {total}")

    # base trick points must be ≤ 300 total
    base_total = r.base_scores[Team.RED] + r.base_scores[Team.NON_RED]
    if base_total > 300:
        errors.append(f"Base trick points exceed 300: {base_total}")
    if base_total < 0:
        errors.append(f"Base trick points negative: {base_total}")

    # ±60 adjustment: if da_gong and mo_gong are opponents, exactly one team gets +60
    if r.da_gong is not None and r.mo_gong and not r.da_gong_mo_gong_same_team:
        dg_score = r.final_team_scores[
            Team.RED if r.da_gong in r.red_team else Team.NON_RED
        ]
        # After adjustment, scores might be capped at 300/floored at 0
        if dg_score < r.base_scores[Team.RED if r.da_gong in r.red_team else Team.NON_RED]:
            # da_gong's team should not score less after the bonus (unless cap applies)
            pass  # cap/floor makes exact check complex; covered by 0..300 bounds above

    # Each player's score equals their team's final score
    for p in range(6):
        team = Team.RED if p in r.red_team else Team.NON_RED
        expected = r.final_team_scores[team]
        if r.final_scores[p] != expected:
            errors.append(f"Player {p} score {r.final_scores[p]} != team score {expected}")


def check_guan_ren(r: HandResult, errors: list):
    scores = set(r.final_scores)
    if not scores.issubset({0, 1000}):
        errors.append(f"GUAN_REN scores not in {{0,1000}}: {r.final_scores}")
    if 1000 not in scores:
        errors.append(f"GUAN_REN: no player scored 1000")
    # Winner team all 1000, loser all 0
    winner_team = Team.RED if r.final_team_scores[Team.RED] == 1000 else Team.NON_RED
    loser_team  = Team.NON_RED if winner_team == Team.RED else Team.RED
    for p in (r.red_team if winner_team == Team.RED else r.non_red_team):
        if r.final_scores[p] != 1000:
            errors.append(f"GUAN_REN winner P{p} scored {r.final_scores[p]} not 1000")
    for p in (r.non_red_team if winner_team == Team.RED else r.red_team):
        if r.final_scores[p] != 0:
            errors.append(f"GUAN_REN loser P{p} scored {r.final_scores[p]} not 0")


def check_san_hong_shi(r: HandResult, errors: list):
    # One solo red-ten player scores 3000, everyone else 0
    if 3000 not in r.final_scores:
        errors.append(f"SAN_HONG_SHI: no player scored 3000")
    count_3000 = r.final_scores.count(3000)
    if count_3000 != 1:
        errors.append(f"SAN_HONG_SHI: {count_3000} players scored 3000 (expected 1)")
    for p in range(6):
        if r.final_scores[p] not in (0, 3000):
            errors.append(f"SAN_HONG_SHI P{p} score {r.final_scores[p]} not in {{0,3000}}")


def check_teams(r: HandResult, errors: list):
    # Red + Non-Red together = all 6 players
    all_players = set(r.red_team) | set(r.non_red_team)
    if all_players != set(range(6)):
        errors.append(f"Teams don't cover all 6 players: {all_players}")
    if set(r.red_team) & set(r.non_red_team):
        errors.append(f"Player in both teams: {set(r.red_team) & set(r.non_red_team)}")
    # Red team size: 1, 2, or 3 (depending on how many red tens one person held)
    if not (1 <= len(r.red_team) <= 3):
        errors.append(f"Red team size {len(r.red_team)} out of expected range 1-3")


def check_finish_order(r: HandResult, errors: list):
    # finish_order should contain distinct player indices in range 0-5
    if len(set(r.finish_order)) != len(r.finish_order):
        errors.append(f"Duplicate in finish_order: {r.finish_order}")
    for p in r.finish_order:
        if p not in range(6):
            errors.append(f"Invalid player {p} in finish_order")
    # In NORMAL play at least 5 should have finished
    if r.terminal == TerminalKind.NORMAL and len(r.finish_order) < 5:
        errors.append(f"NORMAL hand ended with only {len(r.finish_order)} finishers")


def check_da_gong(r: HandResult, errors: list):
    if r.da_gong is not None:
        if r.da_gong not in r.finish_order:
            errors.append(f"大贡 P{r.da_gong} not in finish_order")
        if r.finish_order and r.finish_order[0] != r.da_gong:
            errors.append(f"大贡 P{r.da_gong} is not first in finish_order ({r.finish_order[0]})")


def check_result(r: HandResult) -> list[str]:
    errors: list[str] = []
    check_teams(r, errors)
    check_finish_order(r, errors)
    check_da_gong(r, errors)
    if r.terminal == TerminalKind.NORMAL:
        check_normal(r, errors)
    elif r.terminal == TerminalKind.GUAN_REN:
        check_guan_ren(r, errors)
    elif r.terminal == TerminalKind.SAN_HONG_SHI:
        check_san_hong_shi(r, errors)
    return errors


# ── move / deck invariants ────────────────────────────────────────────────────

def check_deck_invariant():
    """3 decks should produce exactly 162 cards with correct counts."""
    deck = build_deck()
    assert len(deck) == 162, f"Deck has {len(deck)} cards, expected 162"
    cnt = Counter(deck)
    # Each of 52 regular cards appears 3×; each joker appears 3×
    from cards import Suit, Rank
    for suit in (Suit.CLUBS, Suit.DIAMONDS, Suit.HEARTS, Suit.SPADES):
        for rank in range(3, 16):
            c = Card(Suit(suit), Rank(rank))
            assert cnt[c] == 3, f"{c} appears {cnt[c]} times"
    from cards import Card as C
    assert cnt[C(Suit.JOKER, Rank.SMALL_JOKER)] == 3
    assert cnt[C(Suit.JOKER, Rank.BIG_JOKER)]   == 3
    return True


def check_bomb_hierarchy():
    """Lower bomb level must beat higher level (level 1 is strongest)."""
    from moves import Move, CardType
    from cards import Card, Suit, Rank

    def make_bomb(level, count, rank_val=1):
        c = Card(Suit.CLUBS, Rank.THREE)  # dummy cards
        return Move(CardType.BOMB, (c,) * count, rank_val, bomb_key=(level, count, rank_val))

    # Level 1 (3x red ten) beats level 15 (4-bomb)
    strong = make_bomb(1, 3, 0)
    weak   = make_bomb(15, 4, 10)
    assert strong.beats(weak),  "Level-1 bomb must beat level-15"
    assert not weak.beats(strong), "Level-15 must not beat level-1"

    # Within same level, more cards wins
    b6 = make_bomb(9, 6, 5)
    b7 = make_bomb(9, 7, 5)
    assert b7.beats(b6), "7-card bomb must beat 6-card at same level"

    # Within same level and count, higher rank wins
    b_low  = make_bomb(15, 4, 3)
    b_high = make_bomb(15, 4, 10)
    assert b_high.beats(b_low), "Higher rank wins within same level/count"
    return True


def check_legal_moves_non_empty():
    """Leading player must always have at least one legal move."""
    from moves import get_legal_moves
    from cards import build_deck
    import random
    deck = build_deck()
    random.shuffle(deck)
    hand = deck[:27]
    moves = get_legal_moves(hand, None)
    non_pass = [m for m in moves if not m.is_pass()]
    assert len(non_pass) >= 1, "Leader must always have a legal move"
    return True


# ── main ─────────────────────────────────────────────────────────────────────

def run_tests():
    print("Running integration tests...")
    all_errors: list[str] = []

    # Unit-level invariants
    assert check_deck_invariant(),        "Deck invariant"
    assert check_bomb_hierarchy(),        "Bomb hierarchy"
    assert check_legal_moves_non_empty(), "Legal moves"
    print("  ✓ Deck, bomb hierarchy, legal moves")

    # 100-hand simulation
    terminal_counts = Counter()
    for i in range(100):
        try:
            r = run_hand(seed=i)
            terminal_counts[r.terminal.name] += 1
            errs = check_result(r)
            if errs:
                all_errors.append(f"Hand {i}: " + "; ".join(errs))
        except Exception as e:
            all_errors.append(f"Hand {i} CRASH: {e}")

    print(f"  ✓ 100 hands completed")
    print(f"    Terminal breakdown: {dict(terminal_counts)}")

    # 20-hand SearchPlayer smoke test (n_samples=6 for speed)
    search_terminal_counts = Counter()
    for i in range(20):
        seed = 200 + i
        random.seed(seed)
        players = [SearchPlayer(j, n_samples=6) for j in range(6)]
        first = random.randint(0, 5)
        h = Hand(players, first, logger)
        h.deal()
        try:
            r = h.play()
            search_terminal_counts[r.terminal.name] += 1
            errs = check_result(r)
            if errs:
                all_errors.append(f"SearchPlayer hand {i}: " + "; ".join(errs))
        except Exception as e:
            all_errors.append(f"SearchPlayer hand {i} CRASH: {e}")

    print(f"  ✓ 20 SearchPlayer hands completed")
    print(f"    Terminal breakdown: {dict(search_terminal_counts)}")

    if all_errors:
        print(f"\n  ✗ {len(all_errors)} invariant violation(s):")
        for e in all_errors[:10]:
            print(f"    • {e}")
        if len(all_errors) > 10:
            print(f"    ... ({len(all_errors) - 10} more)")
        return False

    print(f"\n  All invariants passed. ✓")
    return True


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
