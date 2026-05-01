"""
Tier 2 — Heuristic Search Player.

For each candidate move, samples N possible worlds (determinization),
simulates the current trick to completion in each world using fast
heuristics, evaluates the resulting state with a multi-factor function,
and picks the move with the best average score.

Determinization: all cards not in our hand and not yet played are pooled,
shuffled, and dealt to other players according to their known hand sizes.
Identity inference biases the distribution toward more likely Red-team
assignments.
"""
from __future__ import annotations
import random
from collections import Counter
from typing import Optional

from cards import Card, build_deck
from moves import Move
from state import GameState
from hand import Player
from identity import IdentityTracker
from evaluator import best_bomb, cheapest_winning_move

# Pre-computed once at import time — avoids rebuilding 162 Cards on every sample
_FULL_DECK_COUNTER: Counter = Counter(build_deck())



# ── Determinization ───────────────────────────────────────────────────────────

def sample_world(state: GameState, my_id: int) -> list[list[Card]]:
    """
    Return a plausible full list of 6 hands consistent with what we know:
      - Our own hand is fixed.
      - Played cards are removed from the pool.
      - Unknown cards are shuffled and dealt to others by hand-size.
    """
    # Build pool of cards not yet accounted for
    known: Counter[Card] = Counter(state.hands[my_id]) + Counter(state.played_cards)

    # Also remove cards currently visible in the trick
    for _, move in state.current_trick:
        if not move.is_pass():
            known += Counter(move.cards)

    pool_counter = _FULL_DECK_COUNTER - known
    pool: list[Card] = list(pool_counter.elements())
    random.shuffle(pool)

    sampled: list[list[Card]] = [[] for _ in range(6)]
    sampled[my_id] = list(state.hands[my_id])

    idx = 0
    for p in range(6):
        if p == my_id:
            continue
        size = max(0, state.player_statuses[p].cards_remaining)
        sampled[p] = pool[idx: idx + size]
        idx += size

    return sampled


# ── State evaluation ──────────────────────────────────────────────────────────

def evaluate(state: GameState, sampled_hands: list[list[Card]],
             player: int, trick_scores: list[int]) -> float:
    """
    Multi-factor evaluation from player's perspective (higher = better for player).

    Factors:
      1. Team trick-point advantage (captured so far this hand)
      2. Scoring cards remaining in allied vs opponent hands (expected future)
      3. Finish-speed bonus (fewer cards = closer to 大贡)
      4. Bomb advantage (quality delta)
      5. 末贡 safety (penalty if a teammate has many cards left)
    """
    ps = state.player_statuses
    my_team = ps[player].team

    def allied(p):   return ps[p].team == my_team
    def opponent(p): return ps[p].team != my_team and ps[p].team is not None

    allies    = [p for p in range(6) if allied(p)]
    opponents = [p for p in range(6) if opponent(p)]

    # 1. Captured trick-point advantage
    ally_pts = sum(trick_scores[p] for p in allies)
    opp_pts  = sum(trick_scores[p] for p in opponents)
    score    = (ally_pts - opp_pts) * 1.0

    # 2. Scoring cards remaining
    ally_future = sum(c.score_value() for p in allies  for c in sampled_hands[p])
    opp_future  = sum(c.score_value() for p in opponents for c in sampled_hands[p])
    score += (ally_future - opp_future) * 0.4

    # 3. Finish-speed bonus for myself (大贡 is very valuable)
    my_cards = len(sampled_hands[player])
    score -= my_cards * 1.5

    # 4. Bomb quality advantage (large sentinel intentional: discourages using bombs,
    #    which is generally correct strategy in Red Ten — bombs should be saved)
    def best_bomb_level(hand):
        b = best_bomb(hand)
        return b.bomb_key[0] if b else 99

    my_bomb       = best_bomb_level(sampled_hands[player])
    opp_bombs     = [best_bomb_level(sampled_hands[p]) for p in opponents]
    best_opp_bomb = min(opp_bombs) if opp_bombs else 99
    score += (best_opp_bomb - my_bomb) * 2.0

    # 5. 末贡 safety: penalise if an ally has many cards left
    other_allies = [p for p in allies if p != player]
    if other_allies:
        max_ally_cards = max(len(sampled_hands[p]) for p in other_allies)
        if max_ally_cards > 10:
            score -= (max_ally_cards - 10) * 0.5

    return score


# ── Fast trick simulator ──────────────────────────────────────────────────────

def _fast_follow(hand: list[Card], current_best: Move, trick_value: int = 0) -> Move:
    """
    Simplified follow logic for simulated players (not full RuleBasedPlayer).
    Beat cheaply; use a bomb only when the trick is worth ≥30 pts (mirrors
    RuleBasedPlayer's heuristic of not burning bombs on cheap tricks).
    """
    cheap = cheapest_winning_move(hand, current_best)
    if cheap is None:
        return Move.pass_move()
    if cheap.is_bomb():
        return cheap if trick_value >= 30 else Move.pass_move()
    return cheap


def simulate_trick(state: GameState, sampled_hands: list[list[Card]],
                   my_id: int, my_move: Move) -> tuple[list[list[Card]], list[int]]:
    """
    Simulate the rest of the current trick starting from my_move being played by my_id.
    Returns (updated_hands, updated_trick_scores).
    Works on copies — does not modify state.
    """
    hands = [list(h) for h in sampled_hands]
    trick_scores = list(state.trick_scores)

    # Track who has already played this trick — they cannot play again
    played_this_trick: set[int] = {p for p, _ in state.current_trick} | {my_id}

    def turn_order_from(start):
        return [(start + i) % 6 for i in range(1, 6)]

    def build_queue(from_player: int) -> list[int]:
        return [q for q in turn_order_from(from_player)
                if not state.player_statuses[q].finished
                and q not in played_this_trick]

    simulated_plays: list[Move] = []

    # Running tally of scoring-card value in this trick (used by _fast_follow to
    # decide whether to use a bomb)
    trick_value = (sum(c.score_value() for _, m in state.current_trick
                       for c in m.cards)
                   + sum(c.score_value() for c in my_move.cards))

    if my_move.is_pass():
        # Find the current leader from the already-played portion of the trick
        current_best = None
        current_best_player = my_id
        for p, m in reversed(state.current_trick):
            if not m.is_pass():
                current_best = m
                current_best_player = p
                break
        if current_best is None:
            return hands, trick_scores  # nothing to simulate (shouldn't happen)
    else:
        for c in my_move.cards:
            if c in hands[my_id]:
                hands[my_id].remove(c)
        current_best = my_move
        current_best_player = my_id

    queue = build_queue(my_id)
    while queue:
        p = queue.pop(0)
        if state.player_statuses[p].finished:
            continue

        move = _fast_follow(hands[p], current_best, trick_value)

        if not move.is_pass():
            trick_value += sum(c.score_value() for c in move.cards)
            for c in move.cards:
                if c in hands[p]:
                    hands[p].remove(c)
            simulated_plays.append(move)
            played_this_trick.add(p)
            current_best = move
            current_best_player = p
            queue = build_queue(p)

    # Award scoring cards to winner (including cards played mid-simulation)
    all_played_in_trick: list[Card] = []
    if not my_move.is_pass():
        all_played_in_trick.extend(my_move.cards)
    for _, m in state.current_trick:
        if not m.is_pass():
            all_played_in_trick.extend(m.cards)
    for m in simulated_plays:
        all_played_in_trick.extend(m.cards)
    pts = sum(c.score_value() for c in all_played_in_trick)
    trick_scores[current_best_player] += pts

    return hands, trick_scores


# ── Move pruning ─────────────────────────────────────────────────────────────

def prune_candidates(moves: list[Move], max_moves: int = 8) -> list[Move]:
    """
    Reduce the candidate set to at most max_moves representative moves.
    Keeps: pass, all bombs, best & worst of each non-bomb type+size bucket.
    """
    if len(moves) <= max_moves:
        return moves

    result: list[Move] = []

    # Always keep pass
    passes = [m for m in moves if m.is_pass()]
    result.extend(passes)

    # Keep all bombs (usually few)
    bombs = [m for m in moves if m.is_bomb()]
    result.extend(bombs)

    # Group non-bomb moves by (type, card_count)
    from collections import defaultdict
    buckets: dict = defaultdict(list)
    for m in moves:
        if not m.is_pass() and not m.is_bomb():
            buckets[(m.type, len(m.cards))].append(m)

    for key, bucket in buckets.items():
        bucket.sort(key=lambda m: m.rank)
        result.append(bucket[0])               # weakest of this type/size
        if len(bucket) > 1:
            result.append(bucket[-1])          # strongest of this type/size
        if len(bucket) > 2:
            result.append(bucket[len(bucket) // 2])  # middle

    # Deduplicate
    seen: set = set()
    final: list[Move] = []
    for m in result:
        k = frozenset(m.cards)
        if k not in seen:
            seen.add(k)
            final.append(m)

    return final[:max_moves]


# ── Search player ─────────────────────────────────────────────────────────────

class SearchPlayer(Player):
    """
    Tier 2: determinized 1-step lookahead.

    For each candidate move, samples n_samples plausible worlds, simulates the
    current trick to completion in each world, scores the resulting state, and
    picks the move with the highest average score.  Passes immediately on
    zero-value tricks (score cards = 0) to save cards for scoring opportunities.
    """

    def __init__(self, player_id: int, n_samples: int = 12):
        super().__init__(player_id)
        self.n_samples = n_samples
        self.tracker   = IdentityTracker()

    def choose_action(self, state: GameState, legal_moves: list[Move]) -> Move:
        self.tracker.sync_from_state(state)

        if not legal_moves:
            raise RuntimeError(f"P{self.id}: no legal moves")

        # Trivial: only one real choice
        non_pass = [m for m in legal_moves if not m.is_pass()]
        if not non_pass:
            return Move.pass_move()
        if len(non_pass) == 1 and non_pass[0] == legal_moves[0]:
            return non_pass[0]

        # Following on a zero-value trick: always pass unless near the end.
        # Matches RuleBasedPlayer rule 2 — saves cards for scoring tricks.
        current_winner = self._trick_winner(state)
        trick_pts      = sum(c.score_value() for _, m in state.current_trick
                             for c in m.cards)
        is_following   = bool(state.current_trick)
        # On a zero-value trick, pass only when a known teammate is winning —
        # don't auto-pass when identity is unknown (let the search decide).
        if is_following and trick_pts == 0 and len(state.hands[self.id]) > 4:
            if (current_winner is not None and current_winner != self.id
                    and self.tracker.is_likely_teammate(self.id, current_winner, 0.65)):
                return Move.pass_move()

        # If following and current winner is a confirmed/likely teammate → pass.
        if (current_winner is not None and current_winner != self.id
                and self.tracker.is_likely_teammate(self.id, current_winner, 0.6)):
            return Move.pass_move()

        # Uniform determinized sampling over pruned candidates.
        candidates = prune_candidates(legal_moves)
        k = len(candidates)
        scores = [0.0] * k

        for _ in range(self.n_samples):
            world = sample_world(state, self.id)
            for i, cand in enumerate(candidates):
                h, s = simulate_trick(state, world, self.id, cand)
                scores[i] += evaluate(state, h, self.id, s)

        best_idx = max(range(k), key=lambda i: scores[i])
        return candidates[best_idx]

    def _trick_winner(self, state: GameState) -> Optional[int]:
        for player, m in reversed(state.current_trick):
            if not m.is_pass():
                return player
        return None
