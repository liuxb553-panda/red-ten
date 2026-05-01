"""
Parallel data collection for MLPlayer training.

Modes:
  outcome      label = player's team score / 300  (RuleBasedPlayer games)
  eval         label = SearchPlayer.evaluate() per (candidate, world)
               Low noise; distills SearchPlayer's heuristic into the MLP.
  selfplay     label = outcome; P0/P2/P4 = MLPlayer(ε-greedy), P1/P3/P5 = --opponent
  selfplay-adv label = advantage per candidate (eval(i) - mean_eval_all_candidates)
               P0/P2/P4 = MLPlayer(ε), P1/P3/P5 = --opponent; oracle = SearchPlayer.evaluate()

Opponent flag (selfplay / selfplay-adv only):
  --opponent rule    P1/P3/P5 = RuleBasedPlayer  (default)
  --opponent search  P1/P3/P5 = SearchPlayer      (harder target, better signal)

Usage:
    # Bootstrap: eval-distillation
    python src/collect_data.py --games 1000 --out data/eval_labels.npz --mode eval

    # Self-play vs Search with advantage labels (recommended)
    python src/collect_data.py --games 500 --out data/sp_r1.npz \\
        --mode selfplay-adv --model data/model.pt --epsilon 0.4 --opponent search

    # Plain selfplay vs Rule (original behavior)
    python src/collect_data.py --games 500 --out data/sp_r1.npz \\
        --mode selfplay --model data/model.pt --epsilon 0.4
"""
from __future__ import annotations
import argparse
import multiprocessing as mp
import os
import random
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))

from features import extract_features, N_FEATURES
from search_player import (sample_world, simulate_trick, prune_candidates,
                            evaluate as search_evaluate)
from hand import Player


# ── Helper: build opponent players for given positions ────────────────────────

def _make_opponent(player_id: int, opponent: str) -> Player:
    if opponent == "search":
        from search_player import SearchPlayer
        return SearchPlayer(player_id)
    from rule_player import RuleBasedPlayer
    return RuleBasedPlayer(player_id)


# ── Recording wrappers ────────────────────────────────────────────────────────

class _OutcomeCollectingPlayer(Player):
    """Records (features for chosen move) per decision; labeled with outcome."""

    def __init__(self, inner: Player):
        super().__init__(inner.id)
        self.inner = inner
        self.decisions: list[tuple[np.ndarray, int]] = []

    def choose_action(self, state, legal_moves):
        move = self.inner.choose_action(state, legal_moves)
        world = sample_world(state, self.id)
        sh, ss = simulate_trick(state, world, self.id, move)
        p_red = getattr(getattr(self.inner, "tracker", None), "p_red", None)
        self.decisions.append((extract_features(state, sh, self.id, ss, p_red), self.id))
        return move


class _AdvantageCollectingPlayer(Player):
    """
    Records (features, advantage) for ALL pruned candidates at each decision.
    advantage_i = avg_search_eval(candidate_i) - mean(avg_search_eval(all_candidates))

    Using N_WORLDS per candidate averages out world-sampling noise while
    keeping collection fast enough for parallel use.
    """
    N_WORLDS = 4

    def __init__(self, inner: Player):
        super().__init__(inner.id)
        self.inner = inner
        self.X: list[np.ndarray] = []
        self.y: list[float]      = []

    def choose_action(self, state, legal_moves):
        move  = self.inner.choose_action(state, legal_moves)
        cands = prune_candidates(legal_moves)
        if len(cands) <= 1:
            return move   # no relative advantage to measure

        p_red = getattr(getattr(self.inner, "tracker", None), "p_red", None)

        # For each candidate, average evaluate() over N_WORLDS worlds.
        # Use world 0's features as the representative feature vector.
        feats_per_cand: list[np.ndarray] = []
        avg_eval_per_cand: list[float]   = []

        for cand in cands:
            evals: list[float] = []
            feat0: np.ndarray | None = None
            for w in range(self.N_WORLDS):
                world = sample_world(state, self.id)
                sh, ss = simulate_trick(state, world, self.id, cand)
                if w == 0:
                    feat0 = extract_features(state, sh, self.id, ss, p_red)
                evals.append(search_evaluate(state, sh, self.id, ss))
            feats_per_cand.append(feat0)       # type: ignore[arg-type]
            avg_eval_per_cand.append(sum(evals) / len(evals))

        mean_eval = sum(avg_eval_per_cand) / len(avg_eval_per_cand)
        for feat, avg_eval in zip(feats_per_cand, avg_eval_per_cand):
            self.X.append(feat)
            self.y.append(avg_eval - mean_eval)   # zero-sum per decision

        return move


# ── Label helper ──────────────────────────────────────────────────────────────

def _label_outcome(collectors: list[_OutcomeCollectingPlayer],
                   hand_state, result) -> tuple[np.ndarray, np.ndarray]:
    X_rows: list[np.ndarray] = []
    y_rows: list[float]      = []
    for w in collectors:
        team    = hand_state.player_statuses[w.id].team
        outcome = result.final_team_scores[team] / 300.0
        for feats, _ in w.decisions:
            X_rows.append(feats)
            y_rows.append(outcome)
    if not X_rows:
        return np.empty((0, N_FEATURES), dtype=np.float32), np.empty(0, dtype=np.float32)
    return np.stack(X_rows).astype(np.float32), np.array(y_rows, dtype=np.float32)


def _label_advantage(recorders: list[_AdvantageCollectingPlayer]
                     ) -> tuple[np.ndarray, np.ndarray]:
    X_all = [x for r in recorders for x in r.X]
    y_all = [y for r in recorders for y in r.y]
    if not X_all:
        return np.empty((0, N_FEATURES), dtype=np.float32), np.empty(0, dtype=np.float32)
    return np.stack(X_all).astype(np.float32), np.array(y_all, dtype=np.float32)


# ── Worker functions ──────────────────────────────────────────────────────────

def _run_outcome_hand(seed: int) -> tuple[np.ndarray, np.ndarray]:
    """RuleBasedPlayer games, outcome labels."""
    random.seed(seed)
    from rule_player import RuleBasedPlayer
    from logger import GameLogger
    from hand import Hand

    inner    = [RuleBasedPlayer(i) for i in range(6)]
    wrappers = [_OutcomeCollectingPlayer(p) for p in inner]
    hand     = Hand(wrappers, random.randint(0, 5), GameLogger(verbose=False))
    hand.deal()
    result = hand.play()
    return _label_outcome(wrappers, hand.state, result)


def _run_selfplay_hand(args: tuple) -> tuple[np.ndarray, np.ndarray]:
    """
    Selfplay: P0/P2/P4 = MLPlayer(ε-greedy), P1/P3/P5 = opponent.
    Collects outcome labels from ML team only.
    """
    seed, model_path, epsilon, opponent = args
    random.seed(seed)
    from ml_player import MLPlayer
    from logger import GameLogger
    from hand import Hand

    collectors: list[_OutcomeCollectingPlayer] = []
    all_players: list[Player] = [None] * 6  # type: ignore[list-item]
    for i in range(6):
        if i % 2 == 0:
            w = _OutcomeCollectingPlayer(MLPlayer(i, model_path=model_path, epsilon=epsilon))
            collectors.append(w)
            all_players[i] = w
        else:
            all_players[i] = _make_opponent(i, opponent)

    hand = Hand(all_players, random.randint(0, 5), GameLogger(verbose=False))
    hand.deal()
    result = hand.play()
    return _label_outcome(collectors, hand.state, result)


def _run_selfplay_adv_hand(args: tuple) -> tuple[np.ndarray, np.ndarray]:
    """
    Selfplay-adv: P0/P2/P4 = MLPlayer(ε-greedy), P1/P3/P5 = opponent.
    Labels each candidate with advantage = eval(i) - mean_eval (SearchPlayer oracle).
    Zero label noise from hand quality — only relative ranking matters.
    """
    seed, model_path, epsilon, opponent = args
    random.seed(seed)
    from ml_player import MLPlayer
    from logger import GameLogger
    from hand import Hand

    recorders: list[_AdvantageCollectingPlayer] = []
    all_players: list[Player] = [None] * 6  # type: ignore[list-item]
    for i in range(6):
        if i % 2 == 0:
            w = _AdvantageCollectingPlayer(MLPlayer(i, model_path=model_path, epsilon=epsilon))
            recorders.append(w)
            all_players[i] = w
        else:
            all_players[i] = _make_opponent(i, opponent)

    hand = Hand(all_players, random.randint(0, 5), GameLogger(verbose=False))
    hand.deal()
    hand.play()
    return _label_advantage(recorders)


def _run_eval_hand(seed: int) -> tuple[np.ndarray, np.ndarray]:
    """
    RuleBasedPlayer games; labels = SearchPlayer.evaluate() (absolute) per
    candidate × world.  Bootstrap data for training from scratch.
    """
    random.seed(seed)
    from rule_player import RuleBasedPlayer
    from logger import GameLogger
    from hand import Hand
    from state import GameState

    N_WORLDS = 6

    class _EvalRecordingPlayer(Player):
        def __init__(self, inner):
            super().__init__(inner.id)
            self.inner = inner
            self.X: list[np.ndarray] = []
            self.y: list[float]      = []

        def choose_action(self, state: GameState, legal_moves):
            move  = self.inner.choose_action(state, legal_moves)
            cands = prune_candidates(legal_moves)
            p_red = getattr(getattr(self.inner, "tracker", None), "p_red", None)
            for cand in cands:
                for _ in range(N_WORLDS):
                    world = sample_world(state, self.id)
                    sh, ss = simulate_trick(state, world, self.id, cand)
                    self.X.append(extract_features(state, sh, self.id, ss, p_red))
                    self.y.append(search_evaluate(state, sh, self.id, ss))
            return move

    inner = [RuleBasedPlayer(i) for i in range(6)]
    recs  = [_EvalRecordingPlayer(p) for p in inner]
    hand  = Hand(recs, random.randint(0, 5), GameLogger(verbose=False))
    hand.deal()
    hand.play()

    X_all = [x for r in recs for x in r.X]
    y_all = [y for r in recs for y in r.y]
    if not X_all:
        return np.empty((0, N_FEATURES), dtype=np.float32), np.empty(0, dtype=np.float32)
    return np.stack(X_all).astype(np.float32), np.array(y_all, dtype=np.float32)


# ── Collection orchestrator ───────────────────────────────────────────────────

def collect(n_games: int, out_path: str, n_workers: int, base_seed: int,
            mode: str, model_path: str | None = None,
            epsilon: float = 0.0,
            opponent: str = "rule") -> tuple[np.ndarray, np.ndarray]:
    """Run collection and save to out_path.  Returns (X, y) arrays."""
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    seeds = [base_seed + i for i in range(n_games)]

    selfplay_modes = {"selfplay", "selfplay-adv"}
    if mode in selfplay_modes and not model_path:
        raise ValueError(f"--model required for {mode} mode")

    if mode == "selfplay":
        worker   = _run_selfplay_hand
        job_args = [(s, model_path, epsilon, opponent) for s in seeds]
    elif mode == "selfplay-adv":
        worker   = _run_selfplay_adv_hand
        job_args = [(s, model_path, epsilon, opponent) for s in seeds]
    elif mode == "eval":
        worker   = _run_eval_hand        # type: ignore[assignment]
        job_args = seeds                 # type: ignore[assignment]
    else:
        worker   = _run_outcome_hand     # type: ignore[assignment]
        job_args = seeds                 # type: ignore[assignment]

    extra = ""
    if mode in selfplay_modes:
        extra = f"  ε={epsilon:.2f}  opp={opponent}"
    print(f"Collecting {n_games} hands  mode={mode}{extra}  workers={n_workers} …")
    t0 = time.time()

    if n_workers <= 1:
        results = [worker(a) for a in job_args]
    else:
        with mp.Pool(n_workers) as pool:
            results = pool.map(worker, job_args)

    elapsed = time.time() - t0
    X_all = np.concatenate([r[0] for r in results if r[0].size], axis=0)
    y_all = np.concatenate([r[1] for r in results if r[1].size], axis=0)

    np.savez_compressed(out_path, X=X_all, y=y_all)
    print(f"Saved {len(X_all):,} samples → {out_path}  "
          f"({elapsed:.1f}s, {len(X_all)/elapsed:.0f} samples/s)")
    if y_all.size:
        print(f"y: [{y_all.min():.3f}, {y_all.max():.3f}]  "
              f"mean={y_all.mean():.3f}  std={y_all.std():.3f}")
    return X_all, y_all


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--games",    type=int, default=500)
    ap.add_argument("--out",      default="data/collected.npz")
    ap.add_argument("--mode",     default="selfplay-adv",
                    choices=["outcome", "eval", "selfplay", "selfplay-adv"])
    ap.add_argument("--model",    default=None,
                    help="Path to model.pt (required for selfplay modes)")
    ap.add_argument("--epsilon",  type=float, default=0.3,
                    help="ε-greedy exploration rate (selfplay modes)")
    ap.add_argument("--opponent", default="search", choices=["rule", "search"],
                    help="Opponent type for selfplay modes")
    ap.add_argument("--workers",  type=int, default=min(8, mp.cpu_count()))
    ap.add_argument("--seed",     type=int, default=0)
    args = ap.parse_args()

    collect(args.games, args.out, args.workers, args.seed,
            args.mode, args.model, args.epsilon, args.opponent)
