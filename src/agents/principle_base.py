"""
Strategic principle infrastructure — Phase 1.5 in the pipeline.

Strategic principles assess the global game situation and produce tactical
rule weight modifiers. They don't score individual moves — they do meta-control:
adjusting which tactical rules are favored based on the overall game state.

StrategyDirector runs all active principles and merges their weight modifiers.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional
from shared_analysis import SharedAnalysis, StrategicContext


class StrategicPrinciple(ABC):
    """Abstract base for a strategic principle.

    Each principle evaluates the global game situation and, when activated,
    returns a StrategicContext with rule weight modifiers. Returns None
    when the principle's activation conditions are not met.
    """
    name: str = ""              # "guan_ren", "avoid_being_guaned"
    description: str = ""       # human-readable, for debugging
    category: str = ""          # "goal" | "danger_response" | "phase_transition"

    @abstractmethod
    def assess(self, analysis: SharedAnalysis) -> Optional[StrategicContext]:
        """Evaluate global situation. Returns None if principle is not active."""
        ...


class StrategyDirector:
    """Runs all strategic principles and merges their weight modifiers.

    Multiple principles can be active simultaneously. Their rule weight
    modifiers are summed additively and clamped to [0, 3.0]. Each principle's
    contribution is scaled by its personality-configured intensity.
    """

    def __init__(
        self,
        principles: list[StrategicPrinciple],
        intensities: dict[str, float],
    ) -> None:
        self.principles = principles
        self.intensities = intensities

    def assess(self, analysis: SharedAnalysis) -> Optional[StrategicContext]:
        """Run all principles, merge results.

        Returns a merged StrategicContext, or None if no principles activated.
        """
        merged_modifiers: dict[str, float] = {}
        goals: list[str] = []
        urgency = 0.0
        reasoning_parts: list[str] = []

        for principle in self.principles:
            intensity = self.intensities.get(principle.name, 1.0)
            if intensity == 0.0:
                continue
            ctx = principle.assess(analysis)
            if ctx is None:
                continue
            goals.append(ctx.primary_goal)
            urgency = max(urgency, ctx.goal_urgency * intensity)
            for rule, modifier in ctx.rule_weight_modifiers.items():
                merged_modifiers[rule] = (
                    merged_modifiers.get(rule, 0.0) + modifier * intensity
                )
            reasoning_parts.append(ctx.reasoning)

        if not goals:
            return None

        # Modifiers are kept as-is (can be negative) — the final effective
        # weight (default_weight + Σ modifiers) is clamped to [0, 3.0] when
        # applied by researchers in Phase 4.

        return StrategicContext(
            primary_goal="+".join(goals),
            rule_weight_modifiers=merged_modifiers,
            goal_urgency=min(1.0, urgency),
            reasoning="; ".join(reasoning_parts),
        )
