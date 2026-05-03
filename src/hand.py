from __future__ import annotations
import random
from dataclasses import dataclass
from typing import Optional

from cards import Card, Rank, Suit, build_deck
from moves import Move, get_legal_moves
from state import GameState, PlayerStatus, Team, TerminalKind, HandResult
from logger import GameLogger


class Player:
    def __init__(self, player_id: int):
        self.id = player_id

    def choose_action(self, state: GameState, legal_moves: list[Move]) -> Move:
        raise NotImplementedError


class RandomPlayer(Player):
    """Plays a random legal move. Used for testing."""
    def choose_action(self, state: GameState, legal_moves: list[Move]) -> Move:
        return random.choice(legal_moves)


@dataclass
class TrickResult:
    winner: int
    scoring_cards: list[Card]
    points: int
    finished_this_trick: list[int]
    all_others_passed_winners_last: bool


class Hand:
    def __init__(self, players: list[Player], first_player: int, logger: GameLogger):
        self.players = players
        self.logger = logger
        self.state = GameState()
        self.state.trick_leader = first_player
        self._trick_num = 0
        self._next_finish_pos = 1

    def deal(self):
        deck = build_deck()
        random.shuffle(deck)
        for p in range(6):
            self.state.hands[p] = deck[p * 27: (p + 1) * 27]
            self.state.player_statuses[p] = PlayerStatus(cards_remaining=27)
        for p in range(6):
            if any(c.is_red_ten() for c in self.state.hands[p]):
                self.state.player_statuses[p].team = Team.RED
            else:
                self.state.player_statuses[p].team = Team.NON_RED
        self.logger.log_deal(self.state.hands)

    def play(self) -> HandResult:
        leader = self.state.trick_leader
        while not self._is_hand_over():
            trick = self._play_trick(leader)
            terminal = self._check_terminal()
            if terminal is not None:
                self.state.terminal = terminal
                break
            if self._is_hand_over():
                break
            leader = self._resolve_next_leader(trick)
        return self._compute_result()

    def _is_hand_over(self) -> bool:
        return len(self.state.finished_players()) >= 6

    def _play_trick(self, leader: int) -> TrickResult:
        self._trick_num += 1
        self.logger.log_trick_header(self._trick_num)
        self.state.current_trick = []

        current_best: Optional[Move] = None
        current_best_player: int = leader
        all_plays: list[tuple[int, Move]] = []
        finished_this_trick: list[int] = []

        # Leader must play
        lm = get_legal_moves(self.state.hands[leader], None)
        move = self.players[leader].choose_action(self.state, lm)
        self._apply_play(leader, move)
        current_best = move
        current_best_player = leader
        all_plays.append((leader, move))
        self.state.current_trick.append((leader, move))
        self.logger.log_trick_lead(leader, move)
        if self.state.player_statuses[leader].finished:
            finished_this_trick.append(leader)

        # Build a fresh queue after each new lead; drain it to end the trick
        def build_queue(after: int) -> list[int]:
            return [p for p in self.state.turn_order_from(after)
                    if p != after and not self.state.player_statuses[p].finished]

        queue = build_queue(leader)
        last_non_pass_player = leader

        while queue:
            p = queue.pop(0)
            if self.state.player_statuses[p].finished:
                continue

            lm = get_legal_moves(self.state.hands[p], current_best)
            move = self.players[p].choose_action(self.state, lm)
            self.state.current_trick.append((p, move))

            if move.is_pass():
                self.logger.log_action(p, move)
            else:
                prev_best = current_best_player
                current_best = move
                current_best_player = p
                last_non_pass_player = p
                all_plays.append((p, move))
                self.logger.log_action(p, move, beats_player=prev_best)
                self._apply_play(p, move)
                if self.state.player_statuses[p].finished:
                    finished_this_trick.append(p)
                queue = build_queue(p)

        scoring_cards = [c for _, m in all_plays for c in m.cards if c.is_scoring()]
        points = sum(c.score_value() for c in scoring_cards)
        self.state.trick_scores[current_best_player] += points
        self.logger.log_trick_end(current_best_player, scoring_cards, points)

        winner_finished = self.state.player_statuses[current_best_player].finished
        all_passed_after_winner = (
            winner_finished and last_non_pass_player == current_best_player
        )

        return TrickResult(
            winner=current_best_player,
            scoring_cards=scoring_cards,
            points=points,
            finished_this_trick=finished_this_trick,
            all_others_passed_winners_last=all_passed_after_winner,
        )

    def _apply_play(self, player: int, move: Move):
        hand = self.state.hands[player]
        for card in move.cards:
            hand.remove(card)
            self.state.played_cards.append(card)
            if card.is_red_ten():
                self.state.player_statuses[player].red_ten_count += 1
                self.logger.log_identity_reveal(player)
        self.state.player_statuses[player].cards_remaining = len(hand)
        if len(hand) == 0 and not self.state.player_statuses[player].finished:
            self.state.player_statuses[player].finished = True
            pos = self._next_finish_pos
            self._next_finish_pos += 1
            self.state.player_statuses[player].finish_position = pos
            self.state.finish_order.append(player)
            self.logger.log_player_finished(player, pos)
            if self.state.da_gong is None:
                self.state.da_gong = player

    def _resolve_next_leader(self, trick: TrickResult) -> int:
        winner = trick.winner
        if trick.all_others_passed_winners_last:
            return self._apply_gui_zhu(winner)
        return winner

    def _apply_gui_zhu(self, finished_player: int) -> int:
        if self.state.all_red_tens_revealed():
            for p in self.state.turn_order_from(finished_player):
                if p == finished_player:
                    continue
                if (self.state.player_statuses[p].team == self.state.player_statuses[finished_player].team
                        and not self.state.player_statuses[p].finished):
                    self.logger.log_gui_zhu(finished_player, p, case=1)
                    return p
        for p in self.state.turn_order_from(finished_player):
            if p == finished_player:
                continue
            if not self.state.player_statuses[p].finished:
                self.logger.log_gui_zhu(finished_player, p, case=2)
                return p
        raise RuntimeError("No unfinished player found for 归主")

    def _check_terminal(self) -> Optional[TerminalKind]:
        red  = self.state.red_team()
        non  = self.state.non_red_team()
        red_done = all(self.state.player_statuses[p].finished for p in red)
        non_done = all(self.state.player_statuses[p].finished for p in non)

        if red_done:
            still_holding = [p for p in non if not self.state.player_statuses[p].finished]
            if still_holding:
                # Only update + log when mo_gong changes
                if set(still_holding) != set(self.state.mo_gong):
                    self.state.mo_gong = still_holding
                    if not any(self.state.player_statuses[p].finished for p in non):
                        self.logger.log_guan_ren(Team.RED)
                        if len(red) == 1:
                            self.logger.log_san_hong_shi(red[0])
                            return TerminalKind.SAN_HONG_SHI
                        return TerminalKind.GUAN_REN
                    else:
                        self.logger.log_mo_gong(still_holding)
                        return TerminalKind.NORMAL

        if non_done:
            still_holding = [p for p in red if not self.state.player_statuses[p].finished]
            if still_holding:
                if set(still_holding) != set(self.state.mo_gong):
                    self.state.mo_gong = still_holding
                    if not any(self.state.player_statuses[p].finished for p in red):
                        self.logger.log_guan_ren(Team.NON_RED)
                        return TerminalKind.GUAN_REN
                    else:
                        self.logger.log_mo_gong(still_holding)
                        return TerminalKind.NORMAL

        return None

    def _compute_result(self) -> HandResult:
        red  = self.state.red_team()
        non  = self.state.non_red_team()
        terminal = self.state.terminal or TerminalKind.NORMAL

        mg_hands = {p: list(self.state.hands[p]) for p in self.state.mo_gong}

        base = {
            Team.RED:     sum(self.state.trick_scores[p] for p in red),
            Team.NON_RED: sum(self.state.trick_scores[p] for p in non),
        }

        if terminal == TerminalKind.SAN_HONG_SHI:
            solo = red[0]
            final_team = {Team.RED: 3000, Team.NON_RED: 0}
            final = [3000 if p == solo else 0 for p in range(6)]
            return HandResult(terminal=terminal, finish_order=self.state.finish_order,
                              red_team=red, non_red_team=non,
                              da_gong=self.state.da_gong, mo_gong=self.state.mo_gong,
                              mo_gong_hands=mg_hands,
                              da_gong_mo_gong_same_team=True,
                              base_scores=base, final_team_scores=final_team, final_scores=final)

        if terminal == TerminalKind.GUAN_REN:
            winner_team = Team.RED if all(self.state.player_statuses[p].finished for p in red) else Team.NON_RED
            loser_team  = Team.NON_RED if winner_team == Team.RED else Team.RED
            final_team = {winner_team: 1000, loser_team: 0}
            final = [final_team[self.state.player_statuses[p].team] for p in range(6)]
            return HandResult(terminal=terminal, finish_order=self.state.finish_order,
                              red_team=red, non_red_team=non,
                              da_gong=self.state.da_gong, mo_gong=self.state.mo_gong,
                              mo_gong_hands=mg_hands,
                              da_gong_mo_gong_same_team=True,
                              base_scores=base, final_team_scores=final_team, final_scores=final)

        # Transfer scoring cards from unfinished players to opposing team
        for p in range(6):
            if not self.state.player_statuses[p].finished:
                p_team = self.state.player_statuses[p].team
                opp = Team.NON_RED if p_team == Team.RED else Team.RED
                for c in self.state.hands[p]:
                    if c.is_scoring():
                        base[opp] += c.score_value()

        # Normal: ±60 adjustment
        same_team = True
        if self.state.da_gong is not None and self.state.mo_gong:
            dg_team  = self.state.player_statuses[self.state.da_gong].team
            mg_teams = {self.state.player_statuses[p].team for p in self.state.mo_gong}
            if dg_team not in mg_teams:
                same_team = False
                other = Team.NON_RED if dg_team == Team.RED else Team.RED
                base[dg_team] += 60
                base[other]   -= 60

        for t in [Team.RED, Team.NON_RED]:
            other = Team.NON_RED if t == Team.RED else Team.RED
            if base[t] < 0:
                base[t] = 0
                base[other] = 300
            base[t] = min(base[t], 300)

        final_team = {Team.RED: base[Team.RED], Team.NON_RED: base[Team.NON_RED]}
        final = [final_team[self.state.player_statuses[p].team] for p in range(6)]

        return HandResult(terminal=terminal, finish_order=self.state.finish_order,
                          red_team=red, non_red_team=non,
                          da_gong=self.state.da_gong, mo_gong=self.state.mo_gong,
                          mo_gong_hands=mg_hands,
                          da_gong_mo_gong_same_team=same_team,
                          base_scores=base, final_team_scores=final_team, final_scores=final)
