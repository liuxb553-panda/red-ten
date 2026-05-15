"""
BullishResearcher — loads offensive tactical rules, favors aggressive play.
"""
from __future__ import annotations

from rules_base import StrategyRule, RuleRegistry
from brain import PersonalityConfig
from researcher_base import ResearcherBase


class BullishResearcher(ResearcherBase):
    """Aggressive researcher: loads offensive rules to favor scoring and speed."""

    def _load_rules(
        self,
        config: PersonalityConfig,
        registry: RuleRegistry,
    ) -> list[StrategyRule]:
        return registry.get_enabled(config.rules, categories=["offensive"])
