"""
Train the RedTenMLP model on collected (features, outcome) data.

Usage:
    python src/train_model.py --data data/games.npz --out data/model.pt
    python src/train_model.py --data data/games.npz --epochs 50 --lr 3e-4

Input:  data/games.npz — 'X' (N×66 float32), 'y' (N float32, values 0-1)
Output: data/model.pt  — state_dict usable by MLPlayer
"""
from __future__ import annotations
import argparse
import os
import sys
import time

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset, random_split

sys.path.insert(0, os.path.dirname(__file__))
from ml_player import RedTenMLP, save_model


def train(data_path: str, out_path: str, epochs: int, lr: float,
          batch_size: int, val_frac: float, patience: int):

    # ── Load data ─────────────────────────────────────────────────────────────
    npz = np.load(data_path)
    X = torch.from_numpy(npz["X"])
    y = torch.from_numpy(npz["y"])
    print(f"Loaded {len(X):,} samples from {data_path}  (features={X.shape[1]})")

    # Normalise labels to zero-mean unit-variance for training stability.
    # Ordinal ranking is preserved so argmax decisions are unaffected.
    y_mean = y.mean().item()
    y_std  = y.std().item()
    y = (y - y_mean) / (y_std + 1e-8)
    print(f"Labels normalised: original mean={y_mean:.3f} std={y_std:.3f}")

    dataset = TensorDataset(X, y)
    n_val = max(1, int(len(dataset) * val_frac))
    n_train = len(dataset) - n_val
    train_ds, val_ds = random_split(dataset, [n_train, n_val],
                                    generator=torch.Generator().manual_seed(42))

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=0)
    val_loader   = DataLoader(val_ds,   batch_size=batch_size * 4, shuffle=False, num_workers=0)

    # ── Device ────────────────────────────────────────────────────────────────
    if torch.backends.mps.is_available():
        device = torch.device("mps")
    elif torch.cuda.is_available():
        device = torch.device("cuda")
    else:
        device = torch.device("cpu")
    print(f"Device: {device}")

    # ── Model, optimizer, scheduler ──────────────────────────────────────────
    model = RedTenMLP().to(device)
    opt   = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, patience=5, factor=0.5)
    loss_fn = nn.MSELoss()

    best_val_loss = float("inf")
    best_epoch    = 0
    no_improve    = 0

    # ── Training loop ─────────────────────────────────────────────────────────
    for epoch in range(1, epochs + 1):
        t0 = time.time()
        model.train()
        train_loss = 0.0
        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            opt.zero_grad()
            pred = model(xb)
            loss = loss_fn(pred, yb)
            loss.backward()
            opt.step()
            train_loss += loss.item() * len(xb)
        train_loss /= n_train

        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for xb, yb in val_loader:
                xb, yb = xb.to(device), yb.to(device)
                pred = model(xb)
                val_loss += loss_fn(pred, yb).item() * len(xb)
        val_loss /= n_val
        sched.step(val_loss)

        elapsed = time.time() - t0
        marker = ""
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_epoch    = epoch
            no_improve    = 0
            save_model(model.cpu(), out_path)
            model.to(device)
            marker = " ✓"
        else:
            no_improve += 1

        print(f"Epoch {epoch:3d}/{epochs}  "
              f"train={train_loss:.4f}  val={val_loss:.4f}  "
              f"lr={opt.param_groups[0]['lr']:.1e}  {elapsed:.1f}s{marker}")

        if no_improve >= patience:
            print(f"Early stopping (no improvement for {patience} epochs).")
            break

    print(f"\nBest val loss {best_val_loss:.4f} at epoch {best_epoch} → {out_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data",       default="data/games.npz", help="Input .npz")
    ap.add_argument("--out",        default="data/model.pt",  help="Output model path")
    ap.add_argument("--epochs",     type=int,   default=100)
    ap.add_argument("--lr",         type=float, default=3e-4)
    ap.add_argument("--batch",      type=int,   default=1024)
    ap.add_argument("--val-frac",   type=float, default=0.1)
    ap.add_argument("--patience",   type=int,   default=15)
    args = ap.parse_args()

    train(args.data, args.out, args.epochs, args.lr, args.batch, args.val_frac, args.patience)
