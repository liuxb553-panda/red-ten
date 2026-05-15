"""
ResearcherBase — abstract base for researcher agents.

Researchers load a subset of tactical rules, score all legal moves through them,
and produce a directional ResearcherOpinion. Strategic context modifiers from
Phase 1.5 are applied to rule weights at evaluation time.
"""
from __future__ import annotations
from abc import abstractmethod
from collections import defaultdict
from typing import Optional

from moves import Move, CardType
from shared_analysis import SharedAnalysis, StrategicContext, ResearcherOpinion
from rules_base import StrategyRule, RuleRegistry
from brain import BaseAgent, PersonalityConfig


class ResearcherBase(BaseAgent):
    """Abstract researcher that loads rules and scores legal moves.

    Subclasses override _load_rules() to define which rule categories they
    load from the registry.
    """

    def __init__(
        self,
        name: str,
        config: PersonalityConfig,
        registry: RuleRegistry,
    ) -> None:
        super().__init__(name)
        self.config = config
        self.rules = self._load_rules(config, registry)

    @abstractmethod
    def _load_rules(
        self, config: PersonalityConfig, registry: RuleRegistry,
    ) -> list[StrategyRule]:
        """Load the subset of rules this researcher is responsible for."""
        ...

    def evaluate(
        self,
        analysis: SharedAnalysis,
        legal_moves: list[Move],
        context: Optional[StrategicContext] = None,
    ) -> ResearcherOpinion:
        """Score all legal moves through assigned rules, return opinion."""
        if not legal_moves:
            return ResearcherOpinion(
                researcher_name=self.name,
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

        if not move_scores:
            return ResearcherOpinion(
                researcher_name=self.name,
                preferred_category=CardType.PASS,
                reasoning="no rules active",
                confidence=0.0,
            )

        best_idx = max(move_scores, key=lambda k: move_scores[k])
        best_move = move_map[best_idx]
        best_score = move_scores[best_idx]
        worst_score = min(move_scores.values())

        # Aggregate scores by CardType for must_avoid detection
        type_scores: dict[CardType, float] = defaultdict(float)
        for i, s in move_scores.items():
            type_scores[move_map[i].type] += s

        must_avoid: list[CardType] = [t for t, s in type_scores.items() if s < -0.3 and t != CardType.PASS]

        # Confidence from score spread
        spread = best_score - worst_score
        confidence = max(0.1, min(0.95, spread / (abs(best_score) + 0.5)))

        # Build reasoning: top 3 contributing rules for the best move
        rule_contributions: list[tuple[str, float]] = []
        for rule in self.rules:
            w = self._effective_weight(rule, context)
            if w == 0.0:
                continue
            s = rule.score(best_move, analysis) * w
            if abs(s) > 0.01:
                rule_contributions.append((rule.name, s))
        rule_contributions.sort(key=lambda x: -abs(x[1]))
        top_rules = rule_contributions[:3]
        reasoning_parts = [f"{name}:{contrib:+.2f}" for name, contrib in top_rules]
        reasoning = f"{self.name}→{best_move.label()} " + " ".join(reasoning_parts)

        return ResearcherOpinion(
            researcher_name=self.name,
            preferred_category=best_move.type,
            must_avoid=must_avoid,
            reasoning=reasoning,
            confidence=confidence,
            move_scores={move_map[i]: s for i, s in move_scores.items()},
        )

    def _effective_weight(
        self,
        rule: StrategyRule,
        context: Optional[StrategicContext],
    ) -> float:
        """Compute effective rule weight: personality override + strategic modifier."""
        w = rule.default_weight
        if context is not None:
            modifier = context.rule_weight_modifiers.get(rule.name, 0.0)
            w += modifier
        return max(0.0, min(3.0, w))
