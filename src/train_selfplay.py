"""
Iterative self-play training loop for MLPlayer.

Each round:
  1. Collect games with current MLPlayer at ε-greedy exploration
  2. Accumulate data in a capped replay buffer (keeps last --keep rounds)
  3. Retrain model from scratch on all buffered data
  4. Benchmark vs RuleBasedPlayer; also vs SearchPlayer when --opponent search
  5. Save checkpoint: data/model_r{round}.pt

Epsilon schedule (linear decay):
  Round 1  →  --eps-start
  Round N  →  --eps-end
  Intermediate rounds interpolated linearly.

Key flags:
  --label-mode outcome      Plain outcome labels (original behaviour)
  --label-mode advantage    Advantage labels (eval(i) - mean_eval); lower noise
  --opponent rule           Opponents = RuleBasedPlayer  (default)
  --opponent search         Opponents = SearchPlayer (harder target, better signal)

Usage:
    # Recommended: advantage labels vs Search opponents
    python src/train_selfplay.py --label-mode advantage --opponent search

    # Original behaviour
    python src/train_selfplay.py --label-mode outcome --opponent rule

    # Resume from checkpoint
    python src/train_selfplay.py --start-model data/model_r6.pt --start-round 7 \\
        --label-mode advantage --opponent search

    # Quick smoke test
    python src/train_selfplay.py --rounds 2 --games 20 --bench-n 10 --epochs 5 \\
        --label-mode advantage --opponent search
"""
from __future__ import annotations
import argparse
import multiprocessing as mp
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))


def _epsilon(round_idx: int, total_rounds: int,
             eps_start: float, eps_end: float) -> float:
    """Linear epsilon decay from eps_start to eps_end over total_rounds."""
    if total_rounds <= 1:
        return eps_start
    t = round_idx / (total_rounds - 1)
    return eps_start + t * (eps_end - eps_start)


def _benchmark(model_path: str, n: int, seed: int, workers: int,
               also_vs_search: bool = False) -> float:
    """Benchmark ML vs Rule (and optionally vs Search). Returns vs-Rule win fraction."""
    from benchmark import run_benchmark
    wins, losses, ties = run_benchmark(
        tier="ml-vs-rule", n=n, seed=seed, n_samples=12,
        model_path=model_path, workers=workers
    )
    if also_vs_search:
        run_benchmark(
            tier="ml-vs-search", n=n, seed=seed, n_samples=12,
            model_path=model_path, workers=workers
        )
    return wins / n


def _train_round(data_paths: list[str], model_path: str,
                 epochs: int, lr: float) -> None:
    """Train a fresh model on all buffered data files."""
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset, random_split
    from ml_player import RedTenMLP, save_model

    # Load and concatenate all buffered data
    chunks_X, chunks_y = [], []
    for p in data_paths:
        d = np.load(p)
        chunks_X.append(d["X"])
        chunks_y.append(d["y"])
    X = torch.from_numpy(np.concatenate(chunks_X, axis=0))
    y = torch.from_numpy(np.concatenate(chunks_y, axis=0))

    y_mean = y.mean().item()
    y_std  = y.std().item()
    y = (y - y_mean) / (y_std + 1e-8)
    print(f"  Training on {len(X):,} samples  "
          f"(y_orig: mean={y_mean:.3f} std={y_std:.3f})")

    n_val   = max(1, int(len(X) * 0.1))
    n_train = len(X) - n_val
    ds      = TensorDataset(X, y)
    tr_ds, val_ds = random_split(
        ds, [n_train, n_val],
        generator=torch.Generator().manual_seed(42)
    )

    batch = 1024
    tr_loader  = DataLoader(tr_ds,  batch_size=batch,   shuffle=True,  num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=batch*4, shuffle=False, num_workers=0)

    if torch.backends.mps.is_available():
        device = torch.device("mps")
    elif torch.cuda.is_available():
        device = torch.device("cuda")
    else:
        device = torch.device("cpu")

    model   = RedTenMLP().to(device)
    opt     = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    sched   = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=5, factor=0.5)
    loss_fn = nn.MSELoss()

    best_val = float("inf")
    patience = 10
    no_imp   = 0

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

        marker = ""
        if val_loss < best_val:
            best_val = val_loss
            no_imp   = 0
            save_model(model.cpu(), model_path)
            model.to(device)
            marker = " ✓"
        else:
            no_imp += 1

        if epoch % 10 == 0 or epoch == 1 or marker:
            print(f"  Epoch {epoch:3d}/{epochs}  "
                  f"train={tr_loss:.4f}  val={val_loss:.4f}{marker}")

        if no_imp >= patience:
            print(f"  Early stop at epoch {epoch} (val={best_val:.4f})")
            break

    print(f"  Best val loss: {best_val:.4f} → {model_path}")


def run(rounds: int, games_per_round: int, workers: int, keep: int,
        eps_start: float, eps_end: float,
        epochs: int, lr: float,
        bench_n: int, bench_seed: int,
        start_model: str, start_round: int,
        data_dir: str,
        label_mode: str = "advantage",
        opponent: str = "search") -> None:

    os.makedirs(data_dir, exist_ok=True)
    model_path = start_model     # current active model
    buf: list[str] = []          # paths to buffered data files (oldest first)

    # Warm-start buffer with eval-label bootstrap data if it exists.
    # It is treated as a normal buffer entry and will cycle out once full.
    seed_data = os.path.join(data_dir, "eval_labels.npz")
    if start_round == 1 and os.path.exists(seed_data):
        buf.append(seed_data)
        print(f"Seeding buffer with {seed_data} (will cycle out after {keep} rounds)")

    collect_mode = "selfplay-adv" if label_mode == "advantage" else "selfplay"

    print(f"\n{'='*60}")
    print(f"Self-play training loop: {rounds} rounds × {games_per_round} games")
    print(f"ε: {eps_start:.2f} → {eps_end:.2f}  |  keep={keep} rounds  |  epochs={epochs}")
    print(f"labels={label_mode}  opponent={opponent}")
    print(f"Starting model: {start_model}")
    print(f"{'='*60}\n")

    for r in range(start_round, start_round + rounds):
        eps = _epsilon(r - start_round, rounds, eps_start, eps_end)
        print(f"\n── Round {r}  ε={eps:.3f} {'─'*40}")

        # ── 1. Collect ────────────────────────────────────────────────────────
        from collect_data import collect as _collect
        data_path = os.path.join(data_dir, f"sp_r{r}.npz")
        seed = r * 1000   # deterministic, non-overlapping seeds per round
        _collect(games_per_round, data_path, workers, seed,
                 mode=collect_mode, model_path=model_path,
                 epsilon=eps, opponent=opponent)
        buf.append(data_path)

        # Trim to keep only the most recent `keep` entries (oldest drops first).
        # The seed eval data is treated like any other entry and cycles out
        # once enough self-play data has accumulated.
        while len(buf) > keep:
            removed = buf.pop(0)
            print(f"  Buffer full — dropped {os.path.basename(removed)}")

        # ── 2. Train ──────────────────────────────────────────────────────────
        new_model = os.path.join(data_dir, f"model_r{r}.pt")
        t0 = time.time()
        _train_round(buf, new_model, epochs=epochs, lr=lr)
        print(f"  Training time: {time.time()-t0:.1f}s")
        model_path = new_model

        # Also update the canonical model.pt so MLPlayer uses it by default
        import shutil
        shutil.copy(model_path, os.path.join(data_dir, "model.pt"))

        # ── 3. Benchmark ──────────────────────────────────────────────────────
        win_rate = _benchmark(model_path, bench_n, bench_seed, workers,
                              also_vs_search=(opponent == "search"))
        print(f"  Benchmark vs Rule: {win_rate*100:.1f}%  (N={bench_n})")

    print(f"\n{'='*60}")
    print(f"Self-play done.  Final model: {model_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds",      type=int,   default=10)
    ap.add_argument("--games",       type=int,   default=500,
                    help="Self-play games per round")
    ap.add_argument("--workers",     type=int,   default=min(8, mp.cpu_count()))
    ap.add_argument("--keep",        type=int,   default=4,
                    help="Replay buffer depth (rounds of data to keep)")
    ap.add_argument("--eps-start",   type=float, default=0.4)
    ap.add_argument("--eps-end",     type=float, default=0.1)
    ap.add_argument("--epochs",      type=int,   default=60)
    ap.add_argument("--lr",          type=float, default=3e-4)
    ap.add_argument("--bench-n",     type=int,   default=40,
                    help="Games per benchmark (fewer = faster, noisier)")
    ap.add_argument("--bench-seed",  type=int,   default=77)
    ap.add_argument("--start-model", default="data/model.pt",
                    help="Checkpoint to start from")
    ap.add_argument("--start-round", type=int,   default=1)
    ap.add_argument("--data-dir",    default="data")
    ap.add_argument("--label-mode",  default="advantage",
                    choices=["outcome", "advantage"],
                    help="outcome=raw team score; advantage=eval(i)-mean_eval per decision")
    ap.add_argument("--opponent",    default="search", choices=["rule", "search"],
                    help="Opponent type for P1/P3/P5 in selfplay")
    args = ap.parse_args()

    run(
        rounds=args.rounds,
        games_per_round=args.games,
        workers=args.workers,
        keep=args.keep,
        eps_start=args.eps_start,
        eps_end=args.eps_end,
        epochs=args.epochs,
        lr=args.lr,
        bench_n=args.bench_n,
        bench_seed=args.bench_seed,
        start_model=args.start_model,
        start_round=args.start_round,
        data_dir=args.data_dir,
        label_mode=args.label_mode,
        opponent=args.opponent,
    )
