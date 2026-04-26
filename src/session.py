from __future__ import annotations
import random
from hand import Hand, Player, RandomPlayer
from rule_player import RuleBasedPlayer
from logger import GameLogger


class GameSession:
    def __init__(self, players: list[Player], logger: GameLogger):
        assert len(players) == 6
        self.players = players
        self.logger = logger
        self.cumulative_scores = [0] * 6
        self.hand_number = 0

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

            if result.da_gong is not None:
                first_player = result.da_gong
                reason = "大贡 last hand"
            else:
                first_player = random.randint(0, 5)
                reason = "random"


def main():
    logger = GameLogger(verbose=True)
    players = [RuleBasedPlayer(i) for i in range(6)]
    session = GameSession(players, logger)
    session.run(num_hands=3)


if __name__ == "__main__":
    main()
