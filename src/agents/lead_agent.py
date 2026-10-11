"""
LeadAgent — Phase 4 decision fusion.

Combines a baseline score (heuristic or MLP value network) with researcher
opinions using the personality-configured fusion formula.
"""
from __future__ import annotations
import random
from typing import Optional

import numpy as np
import torch
import torch.nn as nn

from moves import Move, CardType
from state import GameState
from shared_analysis import SharedAnalysis, ResearcherOpinion
from brain import BaseAgent, PersonalityConfig


class LeadAgent(BaseAgent):
    """Decision manager: fuses baseline scores with researcher opinions.

    When an MLP model is provided, baseline scores come from a learned value
    network (determinized 1-step lookahead).  Otherwise a fast heuristic is used.
    """

    def __init__(self, name: str = "lead",
                 model: Optional[nn.Module] = None, n_mlp_samples: int = 12,
                 p_red: Optional[list[float]] = None, player_id: int = 0,
                 device: str = "cpu") -> None:
        super().__init__(name)
        self.model = model
        self.n_mlp_samples = n_mlp_samples
        self.p_red = p_red
        self.player_id = player_id
        self.device = torch.device(device)

    def choose(
        self,
        state: GameState,
        legal_moves: list[Move],
        analysis: SharedAnalysis,
        opinions: list[ResearcherOpinion],
        personality: PersonalityConfig,
    ) -> Move:
        if not legal_moves:
            return Move.pass_move()
        if len(legal_moves) == 1:
            return legal_moves[0]

        # 1. Baseline scores — MLP if available, else heuristic
        if self.model is not None:
            baseline_scores = self._mlp_baseline_scores(state, legal_moves)
        else:
            baseline_scores = {
                move: self._heuristic_baseline(move, analysis) for move in legal_moves
            }

        # 2. Aggregate researcher opinion scores per move
        opinion_scores: dict[Move, float] = {}
        for move in legal_moves:
            opinion_scores[move] = 0.0
        for opinion in opinions:
            conf = opinion.confidence
            for move, s in opinion.move_scores.items():
                if move in opinion_scores:
                    opinion_scores[move] += s * conf

        # 3. Fusion formula
        w_base = personality.w_base
        w_opinion = personality.w_opinion
        w_random = personality.w_random

        if analysis.strategic_context is not None:
            urgency = analysis.strategic_context.goal_urgency
            shift = 0.15 * urgency * w_base
            w_base -= shift
            w_opinion += shift

        final_scores: dict[Move, float] = {}
        for move in legal_moves:
            base = baseline_scores.get(move, 0.0)
            opinion_sum = opinion_scores.get(move, 0.0)
            noise = w_random * random.random() if w_random > 0 else 0.0
            final_scores[move] = w_base * base + w_opinion * opinion_sum + noise

        best_move = max(final_scores, key=lambda m: final_scores[m])
        return best_move

    # ── Heuristic baseline ─────────────────────────────────────────────────

    def _heuristic_baseline(self, move: Move, analysis: SharedAnalysis) -> float:
        """Heuristic baseline score in [0, 1].

        Scores based on move type, card count, rank, and scoring value.
        Designed to produce sensible ordering: bomb > combo > single > pass.
        """
        if move.is_pass():
            return 0.05

        t = move.type
        n = len(move.cards)
        tricks = max(1, analysis.estimated_tricks_to_finish)
        scoring_bonus = 0.01 * sum(c.score_value() for c in move.cards)

        rank_bonus = 0.0
        if t in (CardType.SINGLE, CardType.PAIR, CardType.TRIPLE):
            rank_bonus = 0.02 * (move.rank / 18.0)

        type_base: dict[CardType, float] = {
            CardType.BOMB:           0.85,
            CardType.TRIPLE_PAIR:    0.70,
            CardType.CONSEC_TRIPLES: 0.75,
            CardType.STRAIGHT:       0.55,
            CardType.CONSEC_PAIRS:   0.50,
            CardType.TRIPLE:         0.45,
            CardType.PAIR:           0.25,
            CardType.SINGLE:         0.10,
        }

        base = type_base.get(t, 0.10)

        if n > 1 and t != CardType.BOMB:
            efficiency = n / tricks
            base += 0.03 * min(1.0, efficiency)

        if t == CardType.BOMB:
            base += 0.05 * (n / tricks)

        return min(1.0, base + rank_bonus + scoring_bonus)

    # ── MLP baseline ───────────────────────────────────────────────────────

    def _mlp_baseline_scores(self, state: GameState,
                             legal_moves: list[Move]) -> dict[Move, float]:
        """Compute MLP-based baseline scores via determinized 1-step lookahead.

        Reuses MLPlayer's pipeline: sample_world → simulate_trick →
        extract_features → MLP forward pass.  Scores are min-max normalised
        to [0, 1] so the fusion formula works identically on both paths.
        """
        from search_player import sample_world, simulate_trick, prune_candidates
        from features import extract_features

        candidates = prune_candidates(legal_moves)
        k = len(candidates)
        feat_rows: list[np.ndarray] = []

        for _ in range(self.n_mlp_samples):
            world = sample_world(state, self.player_id)
            for cand in candidates:
                h, s = simulate_trick(state, world, self.player_id, cand)
                feat_rows.append(extract_features(state, h, self.player_id, s,
                                                  self.p_red))

        X = torch.from_numpy(np.stack(feat_rows)).to(self.device)
        with torch.no_grad():
            assert self.model is not None  # only called when MLP is configured
            raw = self.model(X).cpu().numpy()

        raw = raw.reshape(self.n_mlp_samples, k)
        raw_mean = raw.mean(axis=0)

        s_min, s_max = raw_mean.min(), raw_mean.max()
        if s_max > s_min + 1e-8:
            scores = (raw_mean - s_min) / (s_max - s_min)
        else:
            scores = np.full(k, 0.5)

        result: dict[Move, float] = {}
        for i, cand in enumerate(candidates):
            result[cand] = float(scores[i])
        for m in legal_moves:
            if m not in result:
                result[m] = 0.0
        return result
