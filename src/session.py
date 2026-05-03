from __future__ import annotations
import random
import time
from hand import Hand, Player, RandomPlayer
from rule_player import RuleBasedPlayer
from logger import GameLogger


class GameSession:
    def __init__(self, players: list[Player], logger: GameLogger,
                 hand_pause: float = 0.0,
                 continue_cb: callable = None):
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
    """
    from search_player import SearchPlayer

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
    raise ValueError(
        f"Unknown tier '{tier}'. "
        "Use 'rule', 'search', 'ml', 'mixed', 'ml-vs-rule', or 'ml-vs-search'."
    )


def main():
    import sys
    tier = sys.argv[1] if len(sys.argv) > 1 else "rule"
    logger = GameLogger(verbose=True)
    players = make_players(tier)
    session = GameSession(players, logger)
    session.run(num_hands=3)


if __name__ == "__main__":
    main()
