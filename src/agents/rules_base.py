"""
Tactical rule infrastructure for the multi-agent AI system.

StrategyRule is the atomic unit of play-scoring knowledge — one rule, one concern.
RuleRegistry maps rule names to classes and filters by personality config.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional

from moves import Move
from shared_analysis import SharedAnalysis


class StrategyRule(ABC):
    """Abstract base for a tactical play-scoring rule.

    Each rule scores candidate moves on [-1, 1] based on a single concern.
    Rules are stateless and independent — they don't know about each other.
    Competition happens naturally when a researcher aggregates their scores.

    Subclasses set `name`, `description`, `category`, and `default_weight`
    as class attributes, then implement `score()`.
    """
    name: str = ""
    description: str = ""
    category: str = ""          # "offensive" | "defensive" | "teamwork" | "timing"
    default_weight: float = 1.0

    @abstractmethod
    def score(self, move: Move, analysis: SharedAnalysis) -> float:
        """Score a candidate move. +1 = strongly prefer, -1 = strongly avoid, 0 = neutral."""
        ...

    @property
    def effective_weight(self) -> float:
        """Weight used during scoring. Overridden by personality config at runtime."""
        return self.default_weight


class RuleRegistry:
    """Holds all known StrategyRule subclasses, keyed by `name`.

    Usage:
        registry = RuleRegistry()
        registry.register(InterceptRule)
        rules = registry.get_enabled(config.rules, categories=["offensive"])
    """

    def __init__(self) -> None:
        self._rule_classes: dict[str, type[StrategyRule]] = {}

    def register(self, rule_cls: type[StrategyRule]) -> None:
        """Register a rule class. Uses a throwaway instance to read `name`."""
        inst = rule_cls()
        self._rule_classes[inst.name] = rule_cls

    def get_enabled(
        self,
        config_rules: dict[str, Optional[float]],
        categories: list[str] | None = None,
        include: list[str] | None = None,
    ) -> list[StrategyRule]:
        """Return instantiated rules filtered by personality config.

        A rule is included when:
          1. Its name is NOT explicitly set to 0 in config_rules, AND
          2. Either its name is in `include`, OR its category is in `categories`.

        When both `categories` and `include` are None, all registered rules
        are returned (except those explicitly disabled).

        Weights from config_rules override the rule's default_weight.
        """
        result: list[StrategyRule] = []
        for name, cls in self._rule_classes.items():
            weight = config_rules.get(name)
            if weight is not None and weight == 0.0:
                continue
            inst = cls()
            if weight is not None:
                inst.default_weight = weight
            if include and name in include:
                result.append(inst)
            elif categories and inst.category in categories:
                result.append(inst)
            elif include is None and categories is None:
                result.append(inst)
        return result
