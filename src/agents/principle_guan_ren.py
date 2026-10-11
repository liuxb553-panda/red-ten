"""
GuanRenPrinciple — 关人原则 (goal type).

Activated when our team has at least one finisher but the opponent team
has none. The shutout window is open — we should intercept opponents,
grab scoring cards, and prevent any opponent from finishing.

Puts the opponent's remaining scoring cards at risk of transfer to us.
"""
from __future__ import annotations
from typing import Optional
from shared_analysis import SharedAnalysis, StrategicContext
from principle_base import StrategicPrinciple


class GuanRenPrinciple(StrategicPrinciple):
    """Shutout principle: don't let any opponent finish.

    Activation: my team has >= 1 finisher, opponent team has 0 finishers.
    """

    name = "guan_ren"
    description = "关人窗口打开时强化拦截和抢分，弱化自我清空"
    category = "goal"

    def assess(self, analysis: SharedAnalysis) -> Optional[StrategicContext]:
        opp_finished = analysis.opp_finished_count
        our_finished = analysis.red_finished_count

        if opp_finished == 0 and our_finished >= 1:
            return StrategicContext(
                primary_goal="guan_ren",
                goal_urgency=min(1.0, (6 - analysis.opp_min_remaining) / 6),
                rule_weight_modifiers={
                    "score_rush":    +0.5,   # grab points — shutout transfers all remaining
                    "intercept":     +0.4,   # block opponents from finishing
                    "speed_first":   -0.6,   # getting myself out fast is not the goal
                    "safe_play":     -0.4,   # accept some risk to achieve the shutout
                    "friendly_fire": +0.3,   # even more critical not to bomb teammates
                    "delay_bomb":    -0.5,   # use bombs now, don't save
                },
                reasoning="关人窗口打开：红方已有人出完，非红方无人出完",
            )
        return None
