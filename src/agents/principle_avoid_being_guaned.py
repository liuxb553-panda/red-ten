"""
AvoidBeingGuanedPrinciple — 生存原则 (danger_response type).

Activated when the opponent team has at least one finisher but our team
has none. We are in danger of being shut out — must get at least one
teammate out ASAP, play safe, and avoid exposing identity.
"""
from __future__ import annotations
from typing import Optional
from shared_analysis import SharedAnalysis, StrategicContext
from principle_base import StrategicPrinciple


class AvoidBeingGuanedPrinciple(StrategicPrinciple):
    """Survival principle: prevent our team from being shut out.

    Activation: my team has 0 finishers, opponent team has >= 1 finisher.
    """

    name = "avoid_being_guaned"
    description = "被关风险时强化清空和安全，弱化争分"
    category = "danger_response"

    def assess(self, analysis: SharedAnalysis) -> Optional[StrategicContext]:
        our_finished = analysis.red_finished_count
        opp_finished = analysis.opp_finished_count

        if our_finished == 0 and opp_finished >= 1:
            return StrategicContext(
                primary_goal="avoid_being_guaned",
                goal_urgency=min(1.0, (6 - analysis.our_min_remaining) / 6),
                rule_weight_modifiers={
                    "speed_first":      +0.8,   # must get someone out ASAP
                    "safe_play":        +0.6,   # don't give opponents more points
                    "intercept":        +0.4,   # bomb opponents to stop their finishers
                    "score_rush":       -0.2,   # survival first, scoring secondary
                    "identity_protect": +0.3,   # don't expose identity and draw fire
                    "delay_bomb":       -0.4,   # use bombs now — can't afford to save
                },
                reasoning="生存模式：对手已有人出完，我方必须尽快出完一人破关，炸弹用于拦截而非保留",
            )
        return None
