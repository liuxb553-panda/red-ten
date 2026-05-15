"""
BearishResearcher — loads defensive, teamwork, and timing rules, favors safe play.
"""
from __future__ import annotations

from rules_base import StrategyRule, RuleRegistry
from brain import PersonalityConfig
from researcher_base import ResearcherBase


class BearishResearcher(ResearcherBase):
    """Conservative researcher: loads defensive/teamwork/timing rules."""

    def _load_rules(
        self,
        config: PersonalityConfig,
        registry: RuleRegistry,
    ) -> list[StrategyRule]:
        return registry.get_enabled(
            config.rules,
            categories=["defensive", "teamwork", "timing"],
        )
