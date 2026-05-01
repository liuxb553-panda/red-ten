"""
Tier 3 — ML Player.

Uses a learned MLP to replace the hand-crafted evaluate() function from
SearchPlayer. Identical outer loop: determinized 1-step lookahead with
sample_world + simulate_trick + prune_candidates; only the scoring function
changes.

Model file: data/model.pt  (created by train_model.py)
"""
from __future__ import annotations
import os
import random
from typing import Optional

import numpy as np
import torch
import torch.nn as nn

from cards import Card
from moves import Move
from state import GameState
from hand import Player
from identity import IdentityTracker
from features import extract_features, N_FEATURES
from search_player import sample_world, simulate_trick, prune_candidates

_DEFAULT_MODEL = os.path.join(os.path.dirname(__file__), "..", "data", "model.pt")


# ── MLP architecture ──────────────────────────────────────────────────────────

class RedTenMLP(nn.Module):
    def __init__(self, hidden: tuple[int, ...] = (128, 64, 32)):
        super().__init__()
        layers: list[nn.Module] = []
        in_dim = N_FEATURES
        for h in hidden:
            layers += [nn.Linear(in_dim, h), nn.ReLU()]
            in_dim = h
        layers.append(nn.Linear(in_dim, 1))
        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x).squeeze(-1)


def load_model(path: str = _DEFAULT_MODEL) -> RedTenMLP:
    model = RedTenMLP()
    model.load_state_dict(torch.load(path, map_location="cpu", weights_only=True))
    model.eval()
    return model


def save_model(model: RedTenMLP, path: str = _DEFAULT_MODEL):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    torch.save(model.state_dict(), path)


# ── ML Player ─────────────────────────────────────────────────────────────────

class MLPlayer(Player):
    """
    Tier 3: determinized 1-step lookahead with learned evaluation.

    Replaces the hand-crafted evaluate() from SearchPlayer with a trained MLP.
    Retains the non-scoring-trick pass shortcut from SearchPlayer (domain
    knowledge the 1-ply search can't learn from features alone).
    """

    def __init__(self, player_id: int, model_path: str = _DEFAULT_MODEL,
                 n_samples: int = 12, epsilon: float = 0.0,
                 device: Optional[str] = None):
        super().__init__(player_id)
        self.tracker  = IdentityTracker()
        self.n_samples = n_samples
        self.epsilon   = epsilon    # ε-greedy exploration rate (0 = greedy)

        if device is None:
            # CPU is faster than MPS/CUDA for this tiny model — the per-call
            # data-transfer overhead on accelerators outweighs the compute gain
            # at batch sizes ≤ ~200.  Use accelerator only when explicitly requested.
            device = "cpu"
        self.device = torch.device(device)

        self.model = load_model(model_path).to(self.device)

    def choose_action(self, state: GameState, legal_moves: list[Move]) -> Move:
        self.tracker.sync_from_state(state)

        if not legal_moves:
            raise RuntimeError(f"P{self.id}: no legal moves")

        non_pass = [m for m in legal_moves if not m.is_pass()]
        if not non_pass:
            return Move.pass_move()
        if len(non_pass) == 1 and non_pass[0] == legal_moves[0]:
            return non_pass[0]

        # ε-greedy exploration
        if self.epsilon > 0 and random.random() < self.epsilon:
            return random.choice(legal_moves)

        # Non-scoring trick shortcut (same as SearchPlayer)
        current_winner = self._trick_winner(state)
        trick_pts = sum(c.score_value() for _, m in state.current_trick for c in m.cards)
        is_following = bool(state.current_trick)
        # Pass only when a known teammate is winning — don't auto-pass on unknown identity.
        if is_following and trick_pts == 0 and len(state.hands[self.id]) > 4:
            if (current_winner is not None and current_winner != self.id
                    and self.tracker.is_likely_teammate(self.id, current_winner, 0.65)):
                return Move.pass_move()

        if (current_winner is not None and current_winner != self.id
                and self.tracker.is_likely_teammate(self.id, current_winner, 0.6)):
            return Move.pass_move()

        # Batch all (n_samples × k_candidates) feature vectors into one MLP call.
        candidates = prune_candidates(legal_moves)
        k = len(candidates)
        p_red = self.tracker.p_red
        feat_rows: list[np.ndarray] = []

        for _ in range(self.n_samples):
            world = sample_world(state, self.id)
            for cand in candidates:
                h, s = simulate_trick(state, world, self.id, cand)
                feat_rows.append(extract_features(state, h, self.id, s, p_red))

        X = torch.from_numpy(np.stack(feat_rows)).to(self.device)
        with torch.no_grad():
            raw = self.model(X).cpu().numpy()   # shape: (n_samples * k,)

        raw = raw.reshape(self.n_samples, k)
        scores = raw.mean(axis=0)               # shape: (k,)
        return candidates[int(scores.argmax())]

    def _trick_winner(self, state: GameState) -> Optional[int]:
        for player, m in reversed(state.current_trick):
            if not m.is_pass():
                return player
        return None
