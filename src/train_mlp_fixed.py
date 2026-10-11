"""
Fixed-deal self-play training engine.

Produces 100 random deals, then plays each deal 30 times with ε-greedy
exploration (ε=0.2).  Collects advantage labels from MLPlayer decisions
and trains a fresh MLP on the accumulated data.

Usage:
    python src/train_mlp_fixed.py                         # full training
    python src/train_mlp_fixed.py --hands 10 --reps 3     # smoke test
    python src/train_mlp_fixed.py --no-benchmark           # skip benchmark
"""
from __future__ import annotations
import argparse
import datetime
import json
import multiprocessing as mp
import os
import random
import sys
import time
from typing import Callable, Optional

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "agents"))

from features import extract_features, N_FEATURES
from search_player import sample_world, simulate_trick, prune_candidates, \
    evaluate as search_evaluate
from hand import Player, Hand
from cards import build_deck, Card
from logger import GameLogger
from gui_renderer import GUIRenderer
from serializers import ser_event


# ── Data-collection wrapper ──────────────────────────────────────────────────

class _AdvantageCollector(Player):
    """Wraps an MLPlayer and records advantage labels for every pruned
    candidate at each decision point."""

    N_WORLDS = 4

    def __init__(self, inner: Player):
        super().__init__(inner.id)
        self.inner = inner
        self.X: list[np.ndarray] = []
        self.y: list[float] = []

    def choose_action(self, state, legal_moves):
        move = self.inner.choose_action(state, legal_moves)
        cands = prune_candidates(legal_moves)
        if len(cands) <= 1:
            return move

        p_red = getattr(getattr(self.inner, "tracker", None), "p_red", None)
        feats_per_cand: list[np.ndarray] = []
        avg_eval_per_cand: list[float] = []

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
            self.y.append(avg_eval - mean_eval)

        return move


# ── Opponent helpers ─────────────────────────────────────────────────────────

def _make_opponent(player_id: int, opponent: str) -> Player:
    if opponent == "search":
        from search_player import SearchPlayer
        return SearchPlayer(player_id)
    from rule_player import RuleBasedPlayer
    return RuleBasedPlayer(player_id)


# ── Worker: one repetition of a fixed deal ───────────────────────────────────

def _run_fixeddeal_rep(args: tuple) -> tuple[np.ndarray, np.ndarray]:
    """Worker.  args = (seed, cards_per_player, model_path, epsilon, opponent, log_path)."""
    seed, cards_per_player, model_path, epsilon, opponent, log_path = args
    random.seed(seed)

    from ml_player import MLPlayer

    renderer = GUIRenderer()

    collectors: list[_AdvantageCollector] = []
    all_players: list[Player] = [None] * 6  # type: ignore[list-item]
    for i in range(6):
        if i % 2 == 0:
            w = _AdvantageCollector(
                MLPlayer(i, model_path=model_path, epsilon=epsilon))
            collectors.append(w)
            all_players[i] = w
        else:
            all_players[i] = _make_opponent(i, opponent)

    hand = Hand(all_players, random.randint(0, 5), renderer)
    hand.deal_preset(cards_per_player)
    hand.play()

    # Write JSONL log for replay
    if log_path:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as f:
            for ev in renderer.events:
                f.write(json.dumps(ser_event(ev), ensure_ascii=False) + "\n")

    X_all = [x for r in collectors for x in r.X]
    y_all = [y for r in collectors for y in r.y]
    if not X_all:
        return np.empty((0, N_FEATURES), dtype=np.float32), \
               np.empty(0, dtype=np.float32)
    return np.stack(X_all).astype(np.float32), \
           np.array(y_all, dtype=np.float32)


# ── Training helper ──────────────────────────────────────────────────────────

def _train_model(data_path: str, model_path: str,
                 epochs: int = 60, lr: float = 3e-4,
                 prog_cb: Optional[Callable] = None) -> float:
    """Train a fresh MLP on the collected data.  Returns best validation loss."""
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset, random_split
    from ml_player import RedTenMLP, save_model

    d = np.load(data_path)
    X = torch.from_numpy(d["X"])
    y = torch.from_numpy(d["y"])

    y_mean = y.mean().item()
    y_std = y.std().item()
    y = (y - y_mean) / (y_std + 1e-8)

    n_val = max(1, int(len(X) * 0.1))
    n_train = len(X) - n_val
    ds = TensorDataset(X, y)
    tr_ds, val_ds = random_split(
        ds, [n_train, n_val],
        generator=torch.Generator().manual_seed(42))

    batch = 1024
    tr_loader = DataLoader(tr_ds, batch_size=batch, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=batch * 4, shuffle=False, num_workers=0)

    if torch.backends.mps.is_available():
        device = torch.device("mps")
    elif torch.cuda.is_available():
        device = torch.device("cuda")
    else:
        device = torch.device("cpu")

    model = RedTenMLP().to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=5, factor=0.5)
    loss_fn = nn.MSELoss()

    best_val = float("inf")
    patience = 10
    no_imp = 0

    if prog_cb:
        prog_cb({"type": "train_phase", "phase": "mlp_training",
                 "samples": len(X), "epochs": epochs})

    for epoch in range(1, epochs + 1):
        model.train()
        tr_loss = 0.0
        for xb, yb in tr_loader:
            xb, yb = xb.to(device), yb.to(device)
            opt.zero_grad()
            loss = loss_fn(model(xb), yb)
            loss.backward()
            opt.step()
            tr_loss += loss.item() * len(xb)
        tr_loss /= n_train

        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for xb, yb in val_loader:
                xb, yb = xb.to(device), yb.to(device)
                val_loss += loss_fn(model(xb), yb).item() * len(xb)
        val_loss /= n_val
        sched.step(val_loss)

        if val_loss < best_val:
            best_val = val_loss
            no_imp = 0
            save_model(model.cpu(), model_path)
            model.to(device)
        else:
            no_imp += 1

        if no_imp >= patience:
            break

        if prog_cb and epoch % 5 == 0:
            prog_cb({"type": "train_progress", "phase": "mlp_training",
                     "epoch": epoch, "epochs": epochs,
                     "train_loss": round(tr_loss, 4),
                     "val_loss": round(val_loss, 4)})

    return best_val


# ── Benchmark helper ─────────────────────────────────────────────────────────

def _benchmark(model_path: str, n: int = 200, seed: int = 77,
               workers: int | None = None,
               prog_cb: Callable[[dict], None] | None = None) -> dict:
    """Benchmark ML vs RuleBased.  Returns dict with results."""
    if workers is None:
        workers = min(8, mp.cpu_count())
    from benchmark import run_benchmark

    # Run in a subprocess pool and report progress as results arrive
    from benchmark import _run_hand
    seeds = [seed + i for i in range(n)]
    job_args = [(s, "ml-vs-rule", 12, model_path) for s in seeds]

    if workers <= 1:
        results = [_run_hand(a) for a in job_args]
    else:
        results = []
        with mp.Pool(workers) as pool:
            for i, r in enumerate(pool.imap_unordered(_run_hand, job_args)):
                results.append(r)
                if prog_cb and (i + 1) % max(1, n // 10) == 0:
                    prog_cb({"type": "benchmark_progress", "done": i + 1, "total": n})

    wins = results.count(1)
    losses = results.count(-1)
    ties = results.count(0)
    return {"wins": wins, "losses": losses, "ties": ties,
            "total": n, "win_pct": round(100 * wins / n, 1)}


# ── FixedDealTrainer ─────────────────────────────────────────────────────────

class FixedDealTrainer:
    """Orchestrates the fixed-deal training pipeline.

    Parameters
    ----------
    session_dir : str
        Directory for this training session (e.g. data/training/session_20260509_143000).
    progress_cb : callable or None
        If provided, called with dict status updates for WebSocket push.
    """

    def __init__(self, session_dir: str,
                 progress_cb: Callable[[dict], None] | None = None):
        self.session_dir = session_dir
        self.progress_cb = progress_cb
        self._aborted = False
        self._config: dict = {}   # set by web_server before run()

        os.makedirs(os.path.join(session_dir, "hands"), exist_ok=True)

    def abort(self) -> None:
        self._aborted = True

    def _push(self, data: dict) -> None:
        if self.progress_cb:
            self.progress_cb(data)

    # ── Deal generation ──────────────────────────────────────────────────────

    def generate_deals(self, n_hands: int = 100,
                       seed: int = 42) -> list[list[list[Card]]]:
        """Generate n_hands random deals and save to deals.json."""
        random.seed(seed)
        deals: list[list[list[Card]]] = []

        for i in range(n_hands):
            deck = build_deck()
            random.shuffle(deck)
            cards_per_player = [deck[p * 27:(p + 1) * 27] for p in range(6)]
            deals.append(cards_per_player)

        # Serialize for storage (ranks + suits as strings)
        serialized = []
        for hand_idx, hands in enumerate(deals):
            entry = {"hand_id": hand_idx + 1,
                     "cards": [[f"{c.rank.value}{c.suit.value}"
                                for c in player_cards]
                               for player_cards in hands]}
            serialized.append(entry)

        deals_path = os.path.join(self.session_dir, "deals.json")
        with open(deals_path, "w", encoding="utf-8") as f:
            json.dump(serialized, f, ensure_ascii=False, indent=2)

        return deals

    # ── Full training pipeline ───────────────────────────────────────────────

    def run(self, n_hands: int = 100, n_reps: int = 30,
            epsilon: float = 0.2, opponent: str = "search",
            model_before: str = "data/model.pt",
            epochs: int = 60, lr: float = 3e-4,
            workers: int | None = None,
            benchmark: bool = True, bench_n: int = 40) -> str:
        """Run the complete training pipeline.

        Returns the path to the trained model.
        """
        if workers is None:
            workers = min(8, mp.cpu_count())

        t_start = time.time()

        # ── Load existing model ──────────────────────────────────────────────
        if not os.path.exists(model_before):
            # Bootstrap a fresh model if none exists
            import torch
            from ml_player import RedTenMLP, save_model
            save_model(RedTenMLP(), model_before)

        # Save a copy as model_before.pt
        import shutil
        model_before_copy = os.path.join(self.session_dir, "model_before.pt")
        shutil.copy(model_before, model_before_copy)

        # ── Benchmark before ─────────────────────────────────────────────────
        bench_before = None
        bench_after = None
        if benchmark:
            self._push({"type": "train_phase", "phase": "benchmark_before"})
            bench_before = _benchmark(model_before, n=bench_n, workers=workers,
                                      prog_cb=self.progress_cb)
            bench_path = os.path.join(self.session_dir, "benchmark_before.json")
            with open(bench_path, "w", encoding="utf-8") as f:
                json.dump(bench_before, f, ensure_ascii=False)
            self._push({"type": "benchmark_result", "stage": "before",
                        **bench_before})

        # ── Generate deals ───────────────────────────────────────────────────
        self._push({"type": "train_phase", "phase": "generating_deals",
                    "n_hands": n_hands})
        deals = self.generate_deals(n_hands=n_hands)
        self._push({"type": "train_phase", "phase": "deals_ready",
                    "n_hands": len(deals)})

        # ── Collect data: n_hands × n_reps repetitions ──────────────────────
        all_X: list[np.ndarray] = []
        all_y: list[np.ndarray] = []

        for hand_idx, cards_per_player in enumerate(deals):
            if self._aborted:
                self._push({"type": "train_aborted"})
                return os.path.join(self.session_dir, "model.pt")

            hand_seed = hand_idx * 10000
            hand_dir = os.path.join(self.session_dir, "hands", f"hand_{hand_idx + 1:05d}")
            rep_args = [(hand_seed + rep, cards_per_player,
                         model_before_copy, epsilon, opponent,
                         os.path.join(hand_dir, f"rep_{rep + 1:02d}.jsonl"))
                        for rep in range(n_reps)]

            if workers <= 1:
                rep_results = [_run_fixeddeal_rep(a) for a in rep_args]
            else:
                with mp.Pool(workers) as pool:
                    rep_results = pool.map(_run_fixeddeal_rep, rep_args)

            # Accumulate results
            rep_X = []
            rep_y = []
            for rx, ry in rep_results:
                if rx.size:
                    rep_X.append(rx)
                    rep_y.append(ry)
            if rep_X:
                all_X.append(np.concatenate(rep_X, axis=0))
                all_y.append(np.concatenate(rep_y, axis=0))

            self._push({"type": "train_progress",
                        "hand": hand_idx + 1, "total_hands": n_hands,
                        "reps_done": n_reps})

        if self._aborted:
            self._push({"type": "train_aborted"})
            return os.path.join(self.session_dir, "model.pt")

        # ── Save samples ─────────────────────────────────────────────────────
        self._push({"type": "train_phase", "phase": "saving_samples"})
        X_final = np.concatenate(all_X, axis=0).astype(np.float32)
        y_final = np.concatenate(all_y, axis=0).astype(np.float32)
        samples_path = os.path.join(self.session_dir, "samples.npz")
        np.savez_compressed(samples_path, X=X_final, y=y_final)
        self._push({"type": "samples_saved", "n_samples": len(X_final)})

        # ── Train MLP ────────────────────────────────────────────────────────
        model_path = os.path.join(self.session_dir, "model.pt")
        best_val = _train_model(samples_path, model_path,
                                epochs=epochs, lr=lr,
                                prog_cb=self.progress_cb)
        shutil.copy(model_path,
                    os.path.join(self.session_dir, "model_after.pt"))

        # ── Benchmark after ──────────────────────────────────────────────────
        if benchmark:
            self._push({"type": "train_phase", "phase": "benchmark_after"})
            bench_after = _benchmark(model_path, n=bench_n, workers=workers,
                                      prog_cb=self.progress_cb)
            bench_path = os.path.join(self.session_dir, "benchmark_after.json")
            with open(bench_path, "w", encoding="utf-8") as f:
                json.dump(bench_after, f, ensure_ascii=False)
            self._push({"type": "benchmark_result", "stage": "after",
                        **bench_after})

        # ── Write meta ───────────────────────────────────────────────────────
        elapsed = time.time() - t_start
        meta = {
            "hands": n_hands, "reps": n_reps,
            "epsilon": epsilon, "opponent": opponent,
            "epochs": epochs, "lr": lr,
            "n_samples": int(len(X_final)),
            "best_val_loss": round(best_val, 6),
            "elapsed_s": round(elapsed, 1),
            "benchmark_before": bench_before,
            "benchmark_after": bench_after,
            "model_before": "model_before.pt",
            "model_after": "model_after.pt",
        }
        meta_path = os.path.join(self.session_dir, "meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        self._push({"type": "train_complete", "model_path": model_path,
                    "elapsed_s": round(elapsed, 1), **meta})

        return model_path


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Fixed-deal self-play training engine")
    ap.add_argument("--hands",       type=int,   default=100)
    ap.add_argument("--reps",        type=int,   default=30)
    ap.add_argument("--epsilon",     type=float, default=0.2)
    ap.add_argument("--opponent",    default="search", choices=["rule", "search"])
    ap.add_argument("--epochs",      type=int,   default=60)
    ap.add_argument("--lr",          type=float, default=3e-4)
    ap.add_argument("--model",       default="data/model.pt")
    ap.add_argument("--workers",     type=int,
                    default=min(8, mp.cpu_count()))
    ap.add_argument("--no-benchmark", action="store_true")
    ap.add_argument("--bench-n",     type=int,   default=40)
    ap.add_argument("--output-dir",  default=None,
                    help="Override session dir (default: auto-generated)")
    args = ap.parse_args()

    if args.output_dir:
        session_dir = args.output_dir
    else:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        session_dir = os.path.join("data", "training", f"session_{ts}")

    def _print_prog(data: dict) -> None:
        kind = data.get("type", "?")
        if kind == "train_progress" and "hand" in data:
            print(f"  Hand {data['hand']}/{data['total_hands']}")
        elif kind == "train_progress" and data.get("phase") == "mlp_training":
            print(f"  MLP Epoch {data['epoch']}/{data['epochs']}  "
                  f"train={data['train_loss']}  val={data['val_loss']}")
        elif kind == "benchmark_result":
            print(f"  Benchmark {data['stage']}: {data['win_pct']}% "
                  f"({data['wins']}W {data['losses']}L {data['ties']}T)")
        elif kind == "samples_saved":
            print(f"  Saved {data['n_samples']:,} samples")
        elif kind == "train_complete":
            print(f"  Complete!  Model → {data['model_path']}")
            print(f"  Time: {data['elapsed_s']:.0f}s")
            if data.get("benchmark_before"):
                bb = data["benchmark_before"]
                ba = data["benchmark_after"]
                print(f"  Win rate: {bb['win_pct']}% → {ba['win_pct']}%")
        elif kind == "benchmark_progress":
            print(f"  Benchmark: {data['done']}/{data['total']}")
        elif kind == "train_phase":
            print(f"  Phase: {data['phase']}")
        else:
            print(f"  [{kind}]")

    trainer = FixedDealTrainer(session_dir, progress_cb=_print_prog)
    trainer.run(
        n_hands=args.hands,
        n_reps=args.reps,
        epsilon=args.epsilon,
        opponent=args.opponent,
        model_before=args.model,
        epochs=args.epochs,
        lr=args.lr,
        workers=args.workers,
        benchmark=not args.no_benchmark,
        bench_n=args.bench_n,
    )


if __name__ == "__main__":
    main()
