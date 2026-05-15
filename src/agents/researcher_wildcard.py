"""
WildcardResearcher — loads all rules but adds random perturbation for unpredictability.
"""
from __future__ import annotations
import random
from collections import defaultdict
from typing import Optional

from moves import Move, CardType
from shared_analysis import SharedAnalysis, StrategicContext, ResearcherOpinion
from rules_base import StrategyRule, RuleRegistry
from brain import PersonalityConfig
from researcher_base import ResearcherBase


class WildcardResearcher(ResearcherBase):
    """Unpredictable researcher: loads all rules, adds noise to scores.

    After computing normal rule-based scores, adds random perturbation and
    picks from top-3 scoring moves weighted by score. Produces intentionally
    surprising choices that are hard for opponents to model.
    """

    def _load_rules(
        self,
        config: PersonalityConfig,
        registry: RuleRegistry,
    ) -> list[StrategyRule]:
        return registry.get_enabled(config.rules)

    def evaluate(
        self,
        analysis: SharedAnalysis,
        legal_moves: list[Move],
        context: Optional[StrategicContext] = None,
    ) -> ResearcherOpinion:
        """Evaluate with random perturbation for wildcard behavior."""
        if not legal_moves:
            return ResearcherOpinion(
                researcher_name="Wildcard",
                preferred_category=CardType.PASS,
                reasoning="no legal moves",
                confidence=0.0,
            )

        move_scores: dict[int, float] = defaultdict(float)
        move_map: dict[int, Move] = {}

        for i, move in enumerate(legal_moves):
            move_map[i] = move
            for rule in self.rules:
                w = self._effective_weight(rule, context)
                if w == 0.0:
                    continue
                move_scores[i] += rule.score(move, analysis) * w
            # Add random perturbation
            move_scores[i] += random.uniform(-0.15, 0.15)

        best_idx = max(move_scores, key=lambda k: move_scores[k])
        best_move = move_map[best_idx]

        # Pick from top-3 weighted by score
        ranked = sorted(move_scores.items(), key=lambda x: -x[1])
        top3 = ranked[:3]
        # Weight by softmax-like scaling
        min_s = min(s for _, s in top3)
        shifted = [s - min_s + 0.1 for _, s in top3]
        total = sum(shifted)
        r = random.random() * total
        accum = 0.0
        chosen_idx = top3[0][0]
        for (idx, _), w in zip(top3, shifted):
            accum += w
            if r <= accum:
                chosen_idx = idx
                break

        chosen_move = move_map[chosen_idx]

        # Aggregate scores by CardType
        type_scores: dict[CardType, float] = defaultdict(float)
        for i, s in move_scores.items():
            type_scores[move_map[i].type] += s

        must_avoid: list[CardType] = [t for t, s in type_scores.items() if s < -0.3 and t != CardType.PASS]

        return ResearcherOpinion(
            researcher_name="Wildcard",
            preferred_category=chosen_move.type,
            must_avoid=must_avoid,
            reasoning=f"Wildcard→{chosen_move.label()} noise=±0.15 top3_pick",
            confidence=0.3,
        )
