"""
Multi-agent brain and personality framework.

MultiAgentBrain orchestrates the 5-phase decision pipeline:
  Phase 1:   Analysts populate SharedAnalysis
  Phase 1.5: StrategyDirector assesses global situation
  Phase 2:   Researchers produce opinions via tactical rules
  Phase 3:   Debate (gated by personality.debate_rounds)
  Phase 4:   LeadAgent fuses baseline + opinion scores
  Phase 5:   Validator sanity-checks legality

Phases 1-4 implemented. Phases 1-3 complete, Phase 4 (LeadAgent) active.
"""
from __future__ import annotations
import os
import random
from abc import ABC
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

import torch
import torch.nn as nn

from moves import Move, CardType
from state import GameState
from hand import Player
from identity import IdentityTracker
from shared_analysis import SharedAnalysis, StrategicContext, ResearcherOpinion
from rules_base import StrategyRule, RuleRegistry


# ── Agent mode ────────────────────────────────────────────────────────────────

class AgentMode(Enum):
    """Dual-path execution: rule-based (default) or LLM-driven (future)."""
    RULE_BASED = auto()
    LLM_BASED = auto()


class BaseAgent(ABC):
    """Abstract base for any agent in the pipeline (analyst, researcher, lead, validator)."""
    mode: AgentMode = AgentMode.RULE_BASED

    def __init__(self, name: str = "") -> None:
        self.name = name


# ── Personality config ─────────────────────────────────────────────────────────

@dataclass
class PersonalityConfig:
    """Defines a complete play personality.

    Specifies which analysts and researchers are active, how their opinions
    are weighted, debate depth, and per-rule weight overrides.

    `rules` maps rule name -> overridden weight:
      - None  = use the rule's built-in default_weight
      - 0.0   = disable the rule entirely
      - float = override the rule's weight
    """
    name: str = "default"
    active_analysts: list[str] = field(default_factory=lambda:
        ["hand", "position", "team", "opponent", "risk"])
    active_researchers: list[str] = field(default_factory=lambda:
        ["bullish", "bearish"])
    debate_rounds: int = 0
    w_base: float = 0.5
    w_opinion: float = 0.5
    w_team: float = 0.0
    w_random: float = 0.0
    researcher_weights: dict[str, float] = field(default_factory=dict)
    analyst_weights: dict[str, float] = field(default_factory=dict)
    rules: dict[str, Optional[float]] = field(default_factory=dict)
    principle_intensities: dict[str, float] = field(default_factory=dict)
    # ^ Maps principle name -> response multiplier. 1.0 = standard, 0 = disabled.


DEFAULT_PERSONALITY = PersonalityConfig(
    name="default",
    active_analysts=["hand", "position", "team", "opponent", "risk"],
    active_researchers=["bullish", "bearish"],
    debate_rounds=0,
    w_base=0.5,
    w_opinion=0.5,
    w_team=0.0,
    w_random=0.0,
    researcher_weights={"bullish": 0.5, "bearish": 0.5},
    analyst_weights={"hand": 1.0, "position": 1.0, "team": 1.0, "opponent": 1.0, "risk": 1.0},
    rules={},
    principle_intensities={"guan_ren": 1.0, "avoid_being_guaned": 1.0},
)


# ── Multi-agent brain ─────────────────────────────────────────────────────────

class MultiAgentBrain:
    """Internal entry point for multi-agent decision making.

    Called from MultiAgentPlayer.choose_action(). Orchestrates the full
    5-phase pipeline.

    When model_path is provided the LeadAgent uses an MLP value network
    instead of the heuristic baseline.  With epsilon > 0 the brain
    occasionally picks random moves (ε-greedy exploration for training).
    """

    def __init__(self, player_id: int, personality: PersonalityConfig,
                 model_path: Optional[str] = None,
                 epsilon: float = 0.0,
                 device: str = "cpu") -> None:
        self.player_id = player_id
        self.personality = personality
        self.rule_registry = RuleRegistry()
        self._register_all_rules()
        self.tracker = IdentityTracker()

        self.model: Optional[nn.Module] = None
        if model_path and os.path.exists(model_path):
            from ml_player import load_model
            self.model = load_model(model_path).to(torch.device(device))
        self.mlp_samples = 12
        self.epsilon = epsilon
        self._device = device

    def _register_all_rules(self) -> None:
        """Register all 9 tactical rules into the registry."""
        from rule_intercept import InterceptRule
        from rule_friendly_fire import FriendlyFireRule
        from rule_last_act import LastActRule
        from rule_safe_play import SafePlayRule
        from rule_identity_protect import IdentityProtectRule
        from rule_help_teammate import HelpTeammateRule
        from rule_delay_bomb import DelayBombRule
        from rule_score_rush import ScoreRushRule
        from rule_speed_first import SpeedFirstRule

        for cls in [
            InterceptRule, FriendlyFireRule, LastActRule, SafePlayRule,
            IdentityProtectRule, HelpTeammateRule, DelayBombRule,
            ScoreRushRule, SpeedFirstRule,
        ]:
            self.rule_registry.register(cls)  # type: ignore[type-abstract]

    # ── Public API ──────────────────────────────────────────────────────────

    def decide(self, state: GameState, legal_moves: list[Move]) -> Move:
        """Run the full 5-phase pipeline and return a chosen Move."""

        # ε-greedy exploration (for self-play training data collection)
        if self.epsilon > 0 and random.random() < self.epsilon:
            return random.choice(legal_moves)

        analysis = self._run_analysis(state, legal_moves)

        context = self._assess_strategy(analysis)
        analysis.strategic_context = context

        opinions = self._get_researcher_opinions(analysis, legal_moves)

        final_opinions = self._run_debate(opinions, analysis)

        move = self._fuse_decision(state, legal_moves, analysis, final_opinions)

        return self._validate(move, legal_moves)

    # ── Pipeline phases (all stubs) ─────────────────────────────────────────

    def _run_analysis(self, state: GameState, legal_moves: list[Move]) -> SharedAnalysis:
        """Phase 1: Run all 5 analysts, populate SharedAnalysis.

        The first 4 analysts have no cross-dependencies and could run in
        parallel. RiskAnalyst reads their output and runs serially after.
        """
        analysis = SharedAnalysis()
        self.tracker.sync_from_state(state)
        pid = self.player_id

        from analyst_hand import HandAnalyst
        from analyst_position import PositionAnalyst
        from analyst_team import TeamAnalyst
        from analyst_opponent import OpponentAnalyst
        from analyst_risk import RiskAnalyst

        HandAnalyst(pid, f"P{pid}-hand").analyze(
            state, legal_moves, self.tracker, analysis)
        PositionAnalyst(pid, f"P{pid}-pos").analyze(
            state, legal_moves, self.tracker, analysis)
        TeamAnalyst(pid, f"P{pid}-team").analyze(
            state, legal_moves, self.tracker, analysis)
        OpponentAnalyst(pid, f"P{pid}-opp").analyze(
            state, legal_moves, self.tracker, analysis)

        # RiskAnalyst reads the first 4 results, runs serially
        RiskAnalyst(pid, f"P{pid}-risk").analyze(
            state, legal_moves, self.tracker, analysis)

        return analysis

    def _assess_strategy(self, analysis: SharedAnalysis) -> Optional[StrategicContext]:
        """Phase 1.5: StrategyDirector evaluates global situation.

        Runs all strategic principles. Each principle checks activation
        conditions; active principles' weight modifiers are merged additively.
        """
        from principle_base import StrategyDirector
        from principle_guan_ren import GuanRenPrinciple
        from principle_avoid_being_guaned import AvoidBeingGuanedPrinciple

        principles = [GuanRenPrinciple(), AvoidBeingGuanedPrinciple()]
        director = StrategyDirector(principles, self.personality.principle_intensities)
        return director.assess(analysis)

    def _get_researcher_opinions(
        self, analysis: SharedAnalysis, legal_moves: list[Move],
    ) -> list[ResearcherOpinion]:
        """Phase 2: Researchers produce opinions based on tactical rules.

        Each active researcher loads its assigned rule subset from the registry,
        scores all legal moves, and returns a directional ResearcherOpinion.
        Strategic context modifiers from Phase 1.5 are applied to rule weights.
        """
        from researcher_base import ResearcherBase
        from researcher_bullish import BullishResearcher
        from researcher_bearish import BearishResearcher
        from researcher_wildcard import WildcardResearcher

        researcher_map: dict[str, type[ResearcherBase]] = {
            "bullish": BullishResearcher,
            "bearish": BearishResearcher,
            "wildcard": WildcardResearcher,
        }
        context = analysis.strategic_context
        opinions: list[ResearcherOpinion] = []

        for res_name in self.personality.active_researchers:
            cls = researcher_map.get(res_name)
            if cls is None:
                continue
            researcher = cls(res_name, self.personality, self.rule_registry)
            opinion = researcher.evaluate(analysis, legal_moves, context)
            opinions.append(opinion)

        return opinions

    def _run_debate(
        self, opinions: list[ResearcherOpinion], analysis: SharedAnalysis,
    ) -> list[ResearcherOpinion]:
        """Phase 3: Researchers debate and revise opinions over N rounds.

        Each round, researchers see opposing opinions and adjust confidence.
        If preferred categories conflict, confidence is reduced.
        """
        rounds = self.personality.debate_rounds
        if rounds <= 0 or len(opinions) < 2:
            return opinions

        for _ in range(rounds):
            categories = {o.researcher_name: o.preferred_category for o in opinions}
            for opinion in opinions:
                conflicts = 0
                for name, cat in categories.items():
                    if name != opinion.researcher_name and cat != opinion.preferred_category:
                        conflicts += 1
                if conflicts > 0:
                    # Reduce confidence for each conflicting opinion
                    opinion.confidence *= 0.8 ** conflicts
                    # Add debate note to reasoning
                    opinion.reasoning += f" [debate:{conflicts} conflicts, conf={opinion.confidence:.2f}]"

        return opinions

    def _fuse_decision(
        self,
        state: GameState,
        legal_moves: list[Move],
        analysis: SharedAnalysis,
        opinions: list[ResearcherOpinion],
    ) -> Move:
        """Phase 4: LeadAgent combines baseline AI score with researcher opinions.

        Uses the personality-configured fusion formula:
          final = w_base * baseline + w_opinion * sum(researcher_scores * confidence)
        """
        from lead_agent import LeadAgent
        lead = LeadAgent(
            "lead",
            model=self.model,
            n_mlp_samples=self.mlp_samples,
            p_red=self.tracker.p_red,
            player_id=self.player_id,
            device=self._device,
        )
        return lead.choose(state, legal_moves, analysis, opinions, self.personality)

    def _validate(self, move: Move, legal_moves: list[Move]) -> Move:
        """Phase 5: Validate that the chosen move is legal.

        If the move is not in legal_moves, falls back to the first legal move
        or PASS. This is a safety net — real pipeline stages should never
        produce an illegal move, but this catches bugs and LLM hallucinations.
        """
        if move not in legal_moves:
            if legal_moves:
                return legal_moves[0]
            return Move.pass_move()
        return move


# ── Player integration ────────────────────────────────────────────────────────

class MultiAgentPlayer(Player):
    """Player subclass that delegates to MultiAgentBrain for decision making.

    Usage:
        player = MultiAgentPlayer(0, AGGRESSIVE_CONFIG)
        move = player.choose_action(state, legal_moves)

        # With MLP baseline + exploration (self-play training):
        player = MultiAgentPlayer(0, AGGRESSIVE_CONFIG,
                                   model_path="data/model.pt", epsilon=0.3)
    """

    def __init__(self, player_id: int, personality: PersonalityConfig,
                 model_path: Optional[str] = None,
                 epsilon: float = 0.0,
                 device: str = "cpu") -> None:
        super().__init__(player_id)
        self.personality = personality
        self.brain = MultiAgentBrain(player_id, personality,
                                     model_path=model_path,
                                     epsilon=epsilon,
                                     device=device)

    def choose_action(self, state: GameState, legal_moves: list[Move]) -> Move:
        return self.brain.decide(state, legal_moves)
