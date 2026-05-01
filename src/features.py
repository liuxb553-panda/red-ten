"""
Feature extraction for MLPlayer.

extract_features(state, sampled_hands, player, trick_scores, p_red) → np.ndarray[N_FEATURES]

Feature layout (65 total):
  [0-7]   My hand: size, scoring value, 5s, 10s, red-tens, jokers,
                   bomb-available, bomb-strength                    (8)
  [8-22]  Rank distribution counts for ranks 3-17                  (15)
  [23-26] Score state: ally_pts, opp_pts, differential, total      (4)
  [27-51] Per other player ×5: size, scoring, finished, relation,  (25)
           P(Red)
  [52-56] Game progress: n_finished, best_ally, best_opp,          (5)
           worst_ally (mo_gong risk), worst_opp
  [57-60] Trick context: pts, plays, ally_leading, opp_leading      (4)
  [61-64] Identity: confirmed_red, confirmed_non_red,               (4)
          ally_count, opp_count

Note: hand_playability was removed — it called get_legal_moves(full_hand, None)
which is expensive. Rank distribution (15 features) captures the same signal.
Bomb features use fast inline counting instead of bomb_tier().
"""
from __future__ import annotations
import numpy as np
from typing import Optional

from cards import Card
from state import GameState, Team

N_FEATURES = 65

_PRIOR_P_RED = 0.424   # P(player holds ≥1 red ten) at game start


def extract_features(
    state: GameState,
    sampled_hands: list[list[Card]],
    player: int,
    trick_scores: list[int],
    p_red: Optional[list[float]] = None,
) -> np.ndarray:
    """
    Build a fixed-length float32 feature vector for the given (world, player).

    state         – current game state (trick context, identities, statuses)
    sampled_hands – hands after simulate_trick (player's hand has move removed)
    player        – the acting player
    trick_scores  – per-player trick-point totals after simulate_trick
    p_red         – per-player P(Red) from IdentityTracker; defaults to
                    confirmed certainties + prior for unknowns
    """
    ps = state.player_statuses

    if p_red is None:
        p_red = []
        for p in range(6):
            t = ps[p].team
            if t == Team.RED:
                p_red.append(1.0)
            elif t == Team.NON_RED:
                p_red.append(0.0)
            else:
                p_red.append(_PRIOR_P_RED)

    my_team = ps[player].team

    def is_ally(p: int) -> bool:
        return ps[p].team is not None and ps[p].team == my_team

    def is_opp(p: int) -> bool:
        return ps[p].team is not None and ps[p].team != my_team

    hand = sampled_hands[player]
    f: list[float] = []

    # ── 1. My hand (23 features) ──────────────────────────────────────────────
    # Build rank_cnt first so bomb detection and scoring loops share it
    rank_cnt = [0] * 18     # index = rank value 0..17 (3..17 used)
    joker_cnt = 0
    score_5 = 0; score_10 = 0; red_ten_cnt = 0
    for c in hand:
        rv = c.rank.value
        if 3 <= rv <= 17:
            rank_cnt[rv] += 1
        if rv >= 16:
            joker_cnt += 1
        sv = c.score_value()
        if sv == 5:
            score_5 += 1
        elif sv == 10:
            if c.is_red_ten():
                red_ten_cnt += 1
            else:
                score_10 += 1

    # Fast bomb detection: 4-of-a-kind of any rank, or double joker
    has_bomb = joker_cnt >= 2 or any(v >= 4 for v in rank_cnt)
    # Best bomb rank (lower = stronger): best 4-of-a-kind rank (3=weakest, 17=strongest)
    quad_ranks = [rv for rv, cnt in enumerate(rank_cnt) if cnt >= 4]
    best_quad = max(quad_ranks) if quad_ranks else 0  # highest rank quad is strongest non-joker bomb

    hand_sv = score_5 * 5 + (score_10 + red_ten_cnt) * 10
    f.append(len(hand) / 27.0)
    f.append(hand_sv / 100.0)
    f.append(score_5 / 5.0)
    f.append(score_10 / 5.0)
    f.append(red_ten_cnt / 3.0)
    f.append(joker_cnt / 2.0)
    f.append(1.0 if has_bomb else 0.0)
    f.append(best_quad / 17.0)   # 0 if no quad; joker bomb implicitly covered by feature 5

    for rv in range(3, 18):
        f.append(rank_cnt[rv] / 4.0)

    # ── 2. Score state (4 features) ──────────────────────────────────────────
    allies       = [p for p in range(6) if is_ally(p)]
    opps         = [p for p in range(6) if is_opp(p)]
    ally_pts     = sum(trick_scores[p] for p in allies)
    opp_pts      = sum(trick_scores[p] for p in opps)
    f.append(ally_pts / 300.0)
    f.append(opp_pts  / 300.0)
    f.append((ally_pts - opp_pts) / 300.0)
    f.append((ally_pts + opp_pts) / 300.0)

    # ── 3. Per-other-player (5 × 5 = 25 features) ────────────────────────────
    for p in range(6):
        if p == player:
            continue
        h = sampled_hands[p]
        h_sv = sum(c.score_value() for c in h)
        f.append(len(h) / 27.0)
        f.append(h_sv / 100.0)
        f.append(1.0 if ps[p].finished else 0.0)
        if is_ally(p):
            rel = 1.0
        elif is_opp(p):
            rel = -1.0
        else:
            rel = 0.0
        f.append(rel)
        f.append(p_red[p])

    # ── 4. Game progress (5 features) ────────────────────────────────────────
    n_fin = sum(1 for p in range(6) if ps[p].finished)
    f.append(n_fin / 6.0)

    ally_sizes = [len(sampled_hands[p]) for p in allies] or [0]
    opp_sizes  = [len(sampled_hands[p]) for p in opps]  or [0]
    f.append(min(ally_sizes) / 27.0)   # best ally (closest to out)
    f.append(min(opp_sizes)  / 27.0)   # best opp
    f.append(max(ally_sizes) / 27.0)   # worst ally (末贡 risk)
    f.append(max(opp_sizes)  / 27.0)   # worst opp

    # ── 5. Current trick context (4 features) ────────────────────────────────
    trick_pts = sum(c.score_value() for _, m in state.current_trick for c in m.cards)
    f.append(trick_pts / 50.0)
    f.append(len(state.current_trick) / 6.0)

    trick_winner: Optional[int] = None
    for p, m in reversed(state.current_trick):
        if not m.is_pass():
            trick_winner = p
            break
    f.append(1.0 if trick_winner is not None and is_ally(trick_winner) else 0.0)
    f.append(1.0 if trick_winner is not None and is_opp(trick_winner)  else 0.0)

    # ── 6. Identity info (4 features) ────────────────────────────────────────
    f.append(1.0 if my_team == Team.RED     else 0.0)
    f.append(1.0 if my_team == Team.NON_RED else 0.0)
    other_allies = [p for p in range(6) if p != player and is_ally(p)]
    other_opps   = [p for p in range(6) if p != player and is_opp(p)]
    f.append(len(other_allies) / 2.0)
    f.append(len(other_opps)   / 3.0)

    arr = np.array(f, dtype=np.float32)
    assert len(arr) == N_FEATURES, f"feature count mismatch: {len(arr)} != {N_FEATURES}"
    return arr
