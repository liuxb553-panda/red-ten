from __future__ import annotations
from moves import Move
from state import HandResult, TerminalKind, Team
from cards import Card


class GameLogger:
    def __init__(self, verbose: bool = True):
        self.verbose = verbose

    def _p(self, msg: str):
        if self.verbose:
            print(msg)

    def log_session_start(self, num_hands: int):
        self._p("══════════════════════════════════════════")
        self._p(f"  SESSION START — {num_hands} hands")
        self._p("══════════════════════════════════════════")

    def log_hand_header(self, hand_num: int, first_player: int, reason: str = ""):
        self._p("══════════════════════════════════════════")
        note = f"  ({reason})" if reason else ""
        self._p(f"  HAND {hand_num}  |  P{first_player} goes first{note}")
        self._p("══════════════════════════════════════════")

    def log_deal(self, hands: list[list[Card]]):
        self._p(f"Dealt: {len(hands[0])} cards each, 0 remaining.")
        for i, hand in enumerate(hands):
            rt = sum(1 for c in hand if c.is_red_ten())
            marker = " ♥" * rt if rt else ""
            self._p(f"  P{i}: {len(hand)} cards{marker}")

    def log_trick_header(self, trick_num: int):
        self._p(f"\n── Trick {trick_num} ──────────────────────────────")

    def log_trick_lead(self, player: int, move: Move):
        self._p(f"P{player} leads : {move}")

    def log_action(self, player: int, move: Move, beats_player: int | None = None):
        if move.is_pass():
            self._p(f"P{player}       : pass")
        else:
            arrow = f"  ← beats P{beats_player}" if beats_player is not None else ""
            self._p(f"P{player}       : {move}{arrow}")

    def log_trick_end(self, winner: int, scoring_cards: list[Card], points: int):
        if scoring_cards:
            sc_str = " ".join(str(c) for c in scoring_cards)
            self._p(f"→ P{winner} wins. Scoring: {sc_str} = +{points} pts → P{winner}")
        else:
            self._p(f"→ P{winner} wins. Scoring: none.")

    def log_player_finished(self, player: int, position: int):
        label = {1: "1st — 大贡", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th", 6: "6th — 末贡"}.get(position, f"{position}th")
        self._p(f"  P{player} finishes! ({label})")

    def log_identity_reveal(self, player: int):
        self._p(f"  ★ identity revealed: P{player} = Red Team")

    def log_gui_zhu(self, finished_player: int, new_leader: int, case: int):
        case_desc = "all red tens public → teammate inherits" if case == 1 else "hidden red tens remain → next player in order"
        self._p(f"  归主: {case_desc} → P{new_leader} inherits lead.")

    def log_mo_gong(self, players: list[int]):
        pl = ", ".join(f"P{p}" for p in players)
        self._p(f"  末贡: {pl}")

    def log_guan_ren(self, winner_team: Team):
        self._p(f"  ★★ 关人！ {winner_team.value} team shut out the other team!")

    def log_san_hong_shi(self, player: int):
        self._p(f"  ★★★ 3红十！ P{player} solo shut out all 5 others!")

    def log_hand_summary(self, result: "HandResult", cumulative: list[int]):
        self._p("\n══════════════════════════════════════════")
        self._p("  HAND RESULT")
        self._p("══════════════════════════════════════════")
        finish_str = " ".join(f"P{p}" for p in result.finish_order)
        self._p(f"Finish order : {finish_str}")
        red_pl  = " ".join(f"P{p}" for p in result.red_team)
        nred_pl = " ".join(f"P{p}" for p in result.non_red_team)
        self._p(f"Team Red     : {red_pl}")
        self._p(f"Team Non-Red : {nred_pl}")
        if result.da_gong is not None:
            dg_team = "Red" if result.da_gong in result.red_team else "Non-Red"
            self._p(f"\n大贡: P{result.da_gong} ({dg_team})")
        if result.mo_gong:
            mg_str = ", ".join(f"P{p}" for p in result.mo_gong)
            mg_teams = set("Red" if p in result.red_team else "Non-Red" for p in result.mo_gong)
            adj = "same team, no ±60 adjustment" if result.da_gong_mo_gong_same_team else "opposing teams, ±60 applied"
            self._p(f"末贡: {mg_str} ({', '.join(mg_teams)}) — {adj}")
        self._p(f"\nTerminal: {result.terminal.name}")
        if result.terminal == TerminalKind.NORMAL:
            self._p(f"Trick points : Red {result.base_scores[Team.RED]} | Non-Red {result.base_scores[Team.NON_RED]}")
        self._p(f"Final scores : Red {result.final_team_scores[Team.RED]} | Non-Red {result.final_team_scores[Team.NON_RED]}")
        player_scores = "  ".join(f"P{p}={result.final_scores[p]}" for p in range(6))
        self._p(f"Each player  : {player_scores}")
        self._p(f"\n── Cumulative ───────────────────────────")
        cum = "  ".join(f"P{p}: {cumulative[p]}" for p in range(6))
        self._p(cum)
        self._p("══════════════════════════════════════════\n")
