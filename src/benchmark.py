"""
Benchmark two player tiers against each other.

P0/P2/P4 = "challenger" tier  |  P1/P3/P5 = "baseline" tier

Win = challenger team's final_team_score > baseline team's.
Tie = equal scores.

Usage:
    python src/benchmark.py                               # ml-vs-rule, N=80, seed=77
    python src/benchmark.py --tier mixed                  # search-vs-rule (historic baseline)
    python src/benchmark.py --tier ml-vs-search           # ml vs search
    python src/benchmark.py --tier ml-vs-rule --n 200     # more games
    python src/benchmark.py --tier ml-vs-rule --model data/model.pt
"""
from __future__ import annotations
import argparse
import multiprocessing as mp
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))


# ── Worker ────────────────────────────────────────────────────────────────────

def _run_hand(args: tuple) -> int:
    """
    Worker: run one hand and return +1 (P0 team wins), -1 (baseline wins), 0 (tie).
    args = (seed, tier, n_samples, model_path)
    """
    seed, tier, n_samples, model_path = args
    random.seed(seed)

    from session import make_players
    from logger import GameLogger
    from hand import Hand
    from state import Team

    players = make_players(tier, n_samples=n_samples,
                           model_path=model_path if model_path else None)
    logger  = GameLogger(verbose=False)
    first   = random.randint(0, 5)
    hand    = Hand(players, first, logger)
    hand.deal()
    result  = hand.play()

    # P0 is always on a team; determine which team that is
    p0_team   = hand.state.player_statuses[0].team
    other_team = Team.NON_RED if p0_team == Team.RED else Team.RED

    p0_score  = result.final_team_scores[p0_team]
    opp_score = result.final_team_scores[other_team]

    if p0_score > opp_score:
        return 1
    if p0_score < opp_score:
        return -1
    return 0


# ── Main ──────────────────────────────────────────────────────────────────────

def run_benchmark(tier: str, n: int, seed: int, n_samples: int,
                  model_path: str | None, workers: int):
    seeds = [seed + i for i in range(n)]
    job_args = [(s, tier, n_samples, model_path) for s in seeds]

    print(f"Benchmarking: {tier}  N={n}  seed={seed}  workers={workers}")
    t0 = time.time()

    if workers <= 1:
        results = [_run_hand(a) for a in job_args]
    else:
        with mp.Pool(workers) as pool:
            results = pool.map(_run_hand, job_args)

    wins  = results.count(1)
    losses = results.count(-1)
    ties  = results.count(0)
    pct   = 100 * wins / n
    elapsed = time.time() - t0

    # Label challenger vs baseline
    parts = tier.split("-vs-")
    challenger = parts[0]
    baseline   = parts[1] if len(parts) > 1 else "rule"

    print(f"  {challenger.upper():10s} wins: {wins:3d}  "
          f"{baseline.upper():10s} wins: {losses:3d}  "
          f"Ties: {ties:3d}  "
          f"({pct:.1f}%)")
    print(f"  Time: {elapsed:.1f}s  ({elapsed/n:.1f}s/hand)")
    return wins, losses, ties


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier",     default="ml-vs-rule",
                    help="Matchup tier (see session.make_players for options)")
    ap.add_argument("--n",        type=int, default=80,  help="Number of hands")
    ap.add_argument("--seed",     type=int, default=77,  help="Base random seed")
    ap.add_argument("--samples",  type=int, default=12,  help="n_samples for search/ml")
    ap.add_argument("--model",    default=None,          help="Path to model.pt")
    ap.add_argument("--workers",  type=int,
                    default=min(8, mp.cpu_count()),      help="Parallel workers")
    args = ap.parse_args()

    run_benchmark(args.tier, args.n, args.seed, args.samples, args.model, args.workers)
