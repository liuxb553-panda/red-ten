from __future__ import annotations
import random
import time
from typing import Callable
from hand import Hand, Player, RandomPlayer
from rule_player import RuleBasedPlayer
from logger import GameLogger


class GameSession:
    def __init__(self, players: list[Player], logger: GameLogger,
                 hand_pause: float = 0.0,
                 continue_cb: Callable[[], None] | None = None):
        assert len(players) == 6
        self.players = players
        self.logger = logger
        self.cumulative_scores = [0] * 6
        self.hand_number = 0
        self.hand_pause = hand_pause
        self._continue_cb = continue_cb

    def run(self, num_hands: int):
        self.logger.log_session_start(num_hands)
        first_player = random.randint(0, 5)
        reason = "random start"

        for i in range(num_hands):
            self.hand_number += 1
            self.logger.log_hand_header(self.hand_number, first_player, reason)
            hand = Hand(self.players, first_player, self.logger)
            hand.deal()
            result = hand.play()
            for p in range(6):
                self.cumulative_scores[p] += result.final_scores[p]
            self.logger.log_hand_summary(result, self.cumulative_scores)

            if i < num_hands - 1:
                if self._continue_cb:
                    self._continue_cb()
                elif self.hand_pause > 0:
                    time.sleep(self.hand_pause)

            if result.da_gong is not None:
                first_player = result.da_gong
                reason = "大贡 last hand"
            else:
                first_player = random.randint(0, 5)
                reason = "random"


# ── Player tier helpers ───────────────────────────────────────────────────────

def make_players(tier: str, n_samples: int = 12,
                 model_path: str | None = None) -> list[Player]:
    """
    tier="rule"      → 6× RuleBasedPlayer  (Tier 1)
    tier="search"    → 6× SearchPlayer     (Tier 2)
    tier="ml"        → 6× MLPlayer         (Tier 3)
    tier="mixed"     → 3× SearchPlayer vs 3× RuleBasedPlayer  (P0/2/4 vs P1/3/5)
    tier="ml-vs-rule"→ 3× MLPlayer    vs 3× RuleBasedPlayer  (P0/2/4 vs P1/3/5)
    tier="ml-vs-search"→ 3× MLPlayer  vs 3× SearchPlayer     (P0/2/4 vs P1/3/5)
    tier="multi-agent" → 6× MultiAgentPlayer (default personality)
    tier="multi-agent-vs-rule" → 3× MultiAgentPlayer vs 3× RuleBasedPlayer (P0/2/4 vs P1/3/5)
    tier="multi-agent-mlp" → 6× MultiAgentPlayer + MLP value network baseline
    tier="multi-agent-mlp-vs-rule" → 3× MultiAgentPlayer(MLP) vs 3× RuleBasedPlayer (P0/2/4 vs P1/3/5)
    tier="personalities" → 1 of each personality (激进/保守/均衡/诡诈/配合/自私)
    tier="llm"       → 6× LLMPlayer using the default model in config/llm_models.json
    tier="llm:<name>"→ 6× LLMPlayer using the named model
    """
    from search_player import SearchPlayer

    if tier == "llm" or tier.startswith("llm:"):
        return [_llm(i, tier.partition(":")[2] or None) for i in range(6)]

    def _ml(i):
        from ml_player import MLPlayer
        kw = {"model_path": model_path} if model_path else {}
        return MLPlayer(i, n_samples=n_samples, **kw)

    if tier == "rule":
        return [RuleBasedPlayer(i) for i in range(6)]
    if tier == "search":
        return [SearchPlayer(i, n_samples=n_samples) for i in range(6)]
    if tier == "ml":
        return [_ml(i) for i in range(6)]
    if tier == "mixed":
        return [SearchPlayer(i, n_samples=n_samples) if i % 2 == 0
                else RuleBasedPlayer(i) for i in range(6)]
    if tier == "ml-vs-rule":
        return [_ml(i) if i % 2 == 0 else RuleBasedPlayer(i) for i in range(6)]
    if tier == "ml-vs-search":
        return [_ml(i) if i % 2 == 0 else SearchPlayer(i, n_samples=n_samples)
                for i in range(6)]
    if tier == "multi-agent":
        from brain import MultiAgentPlayer, DEFAULT_PERSONALITY
        return [MultiAgentPlayer(i, DEFAULT_PERSONALITY) for i in range(6)]
    if tier == "multi-agent-vs-rule":
        from brain import MultiAgentPlayer, DEFAULT_PERSONALITY
        return [MultiAgentPlayer(i, DEFAULT_PERSONALITY) if i % 2 == 0
                else RuleBasedPlayer(i) for i in range(6)]
    if tier == "multi-agent-mlp":
        from brain import MultiAgentPlayer, DEFAULT_PERSONALITY
        mp = model_path if model_path else "data/model.pt"
        return [MultiAgentPlayer(i, DEFAULT_PERSONALITY, model_path=mp)
                for i in range(6)]
    if tier == "multi-agent-mlp-vs-rule":
        from brain import MultiAgentPlayer, DEFAULT_PERSONALITY
        mp = model_path if model_path else "data/model.pt"
        return [MultiAgentPlayer(i, DEFAULT_PERSONALITY, model_path=mp)
                if i % 2 == 0 else RuleBasedPlayer(i) for i in range(6)]
    if tier == "personalities":
        from brain import MultiAgentPlayer
        from personalities import (
            AGGRESSIVE, CONSERVATIVE, BALANCED, TRICKY, COOPERATIVE, SELFISH,
        )
        configs = [AGGRESSIVE, CONSERVATIVE, BALANCED, TRICKY, COOPERATIVE, SELFISH]
        return [MultiAgentPlayer(i, configs[i]) for i in range(6)]
    raise ValueError(
        f"Unknown tier '{tier}'. "
        "Use 'rule', 'search', 'ml', 'mixed', 'ml-vs-rule', 'ml-vs-search', "
        "'multi-agent', 'multi-agent-vs-rule', "
        "'multi-agent-mlp', 'multi-agent-mlp-vs-rule', 'personalities', "
        "'llm', or 'llm:<model>'."
    )


# ── Per-seat config (used by BattleConfig / AI self-play) ──────────────────────

AVAILABLE_TIERS = [
    {"value": "rule",       "label": "Rule-Based (Tier 1)", "has_personality": False},
    {"value": "search",     "label": "Search AI (Tier 2)",  "has_personality": False},
    {"value": "ml",         "label": "ML AI (Tier 3)",      "has_personality": False},
    {"value": "multi-agent","label": "Multi-Agent AI",      "has_personality": True},
    {"value": "llm",        "label": "LLM AI (本地大模型)",  "has_personality": False,
     "has_model": True},
]

AVAILABLE_PERSONALITIES = [
    {"value": "aggressive",   "label": "激进型 Aggressive"},
    {"value": "conservative", "label": "保守型 Conservative"},
    {"value": "balanced",     "label": "均衡型 Balanced"},
    {"value": "tricky",       "label": "诡诈型 Tricky"},
    {"value": "cooperative",  "label": "配合型 Cooperative"},
    {"value": "selfish",      "label": "自私型 Selfish"},
]


def _llm(player_id: int, model: str | None) -> Player:
    """An LLM seat using the named model (None = the configured default)."""
    from llm_client import get_model
    from llm_player import LLMPlayer
    return LLMPlayer(player_id, get_model(model))


def _resolve_personality(name: str | None):
    """Map a personality slug to its PersonalityConfig."""
    from brain import DEFAULT_PERSONALITY
    from personalities import (
        AGGRESSIVE, CONSERVATIVE, BALANCED, TRICKY, COOPERATIVE, SELFISH,
    )
    mapping = {
        "aggressive": AGGRESSIVE, "conservative": CONSERVATIVE,
        "balanced": BALANCED,     "tricky": TRICKY,
        "cooperative": COOPERATIVE, "selfish": SELFISH,
    }
    return mapping.get(name, DEFAULT_PERSONALITY) if name else DEFAULT_PERSONALITY


def make_players_from_config(config) -> list[Player]:
    """Create 6 players from a per-seat BattleConfig."""
    from search_player import SearchPlayer

    players: list[Player] = []
    for i, seat_cfg in enumerate(config.seats):
        tier = seat_cfg.tier
        if tier == "rule":
            players.append(RuleBasedPlayer(i))
        elif tier == "search":
            players.append(SearchPlayer(i, n_samples=12))
        elif tier == "ml":
            from ml_player import MLPlayer
            players.append(MLPlayer(i, n_samples=12))
        elif tier == "multi-agent":
            from brain import MultiAgentPlayer
            players.append(MultiAgentPlayer(i, _resolve_personality(seat_cfg.personality)))
        elif tier == "llm":
            players.append(_llm(i, seat_cfg.model))
        else:
            players.append(SearchPlayer(i, n_samples=12))
    assert len(players) == 6
    return players


def main():
    import sys
    tier = sys.argv[1] if len(sys.argv) > 1 else "rule"
    logger = GameLogger(verbose=True)
    players = make_players(tier)
    session = GameSession(players, logger)
    session.run(num_hands=3)


if __name__ == "__main__":
    main()
