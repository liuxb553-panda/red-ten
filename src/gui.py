"""
Red Ten Poker — pygame GUI.

Keyboard / buttons:
  Space / ▶⏸  — play / pause
  ← ▶ Next ◀ Back  — step one event
  ↑↓ / 🐢🐇       — speed
  R / ⏮ Restart
  Q / Esc           — quit
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import pygame
from typing import Optional

from cards import Card, Suit, Rank
from moves import Move
from state import Team
from gui_renderer import GUIRenderer, GameEvent, GameSnapshot
from session import GameSession
from rule_player import RuleBasedPlayer


# ── Colours (never change) ────────────────────────────────────────────────────
C_BG           = (22,  90,  35)
C_TABLE        = (16,  70,  26)
C_CARD_FACE    = (255, 252, 238)
C_RED_SUIT     = (195,  10,  10)
C_BLACK_SUIT   = (18,   18,  18)
C_RED_TEN_BG   = (255, 210,   0)
C_RED_TEN_FG   = (140,  45,   0)
C_JOKER_S_BG   = (205, 150, 235)
C_JOKER_B_BG   = (115,  55, 195)
C_JOKER_FG     = (255, 255, 255)
C_PANEL        = (12,   44,  20)
C_PANEL_LINE   = (45,  110,  55)
C_TEXT         = (225, 228, 215)
C_TEXT_DIM     = (130, 145, 120)
C_HIGHLIGHT    = (255, 228,  45)
C_WINNER_GLOW  = (255, 175,   0)
C_RED_TEAM     = (220,  72,  72)
C_NON_TEAM     = (88,  155, 220)
C_UNKNOWN      = (150, 150, 150)
C_CTRL_BG      = (12,   36,  18)
C_BTN          = (40,   95,  52)
C_BTN_HOVER    = (60,  135,  72)
C_BTN_ACTIVE   = (88,  190, 100)
C_BTN_BORDER   = (70,  150,  80)
C_FINISHED     = (75,  200,  75)
C_STAR         = (255, 228,  45)

SPEED_LEVELS  = [2500, 1500, 900, 500, 250, 120, 60]
SPEED_DEFAULT = 3

SUIT_SYM = {Suit.CLUBS: "♣", Suit.DIAMONDS: "♦", Suit.HEARTS: "♥", Suit.SPADES: "♠"}
RANK_LBL = {
    Rank.THREE: "3", Rank.FOUR: "4", Rank.FIVE: "5", Rank.SIX: "6",
    Rank.SEVEN: "7", Rank.EIGHT: "8", Rank.NINE: "9", Rank.TEN: "10",
    Rank.JACK: "J", Rank.QUEEN: "Q", Rank.KING: "K", Rank.ACE: "A",
    Rank.TWO: "2", Rank.SMALL_JOKER: "小王", Rank.BIG_JOKER: "大王",
}


# ── Dynamic layout ────────────────────────────────────────────────────────────
class Layout:
    """All size/position constants derived from current window dimensions."""

    def __init__(self, w: int, h: int):
        self.W       = w
        self.H       = h
        self.PANEL_W = max(260, w // 5)
        self.TABLE_W = w - self.PANEL_W
        self.CTRL_H  = max(72, h // 12)

        # Cards scale with window width, capped for readability
        self.CARD_W  = max(36, min(68, w // 27))
        self.CARD_H  = int(self.CARD_W * 1.44)
        self.OVERLAP = max(8, self.CARD_W // 4)

        tw = self.TABLE_W
        ch = self.CTRL_H
        cw, ch2 = self.CARD_W, self.CARD_H

        # Seat centres, counter-clockwise from P0 (bottom)
        self.SEAT = [
            (tw // 2,               h - ch - int(ch2 * 0.65)),   # P0 bottom
            (int(tw * 0.115),       h - ch - int(ch2 * 1.50)),   # P1 lower-left
            (int(tw * 0.075),       int(h * 0.33)),               # P2 left
            (tw // 2,               int(ch2 * 0.65)),             # P3 top
            (int(tw * 0.925),       int(h * 0.33)),               # P4 right
            (int(tw * 0.885),       h - ch - int(ch2 * 1.50)),   # P5 lower-right
        ]

        self.TRICK_CX = tw // 2
        self.TRICK_CY = (h - ch) // 2 - int(h * 0.02)

        # Trick card offsets scale with window
        sx = min(w / 1800, h / 1050)
        self.TRICK_OFF = [
            (0,                int(115 * sx)),   # P0
            (int(-125 * sx),   int( 78 * sx)),   # P1
            (int(-150 * sx),   int(-15 * sx)),   # P2
            (0,                int(-115 * sx)),  # P3
            (int( 150 * sx),   int(-15 * sx)),   # P4
            (int( 125 * sx),   int( 78 * sx)),   # P5
        ]

        self.BTN_W = max(95, w // 17)
        self.BTN_H = max(42, self.CTRL_H - 24)


# ── Font helper ───────────────────────────────────────────────────────────────
def load_fonts(layout: Layout) -> dict:
    candidates = ["Arial Unicode MS", "PingFang SC", "STHeiti", "Heiti SC", None]

    def best(size, bold=False):
        for name in candidates:
            f = pygame.font.SysFont(name, size, bold=bold)
            if f.render("大", True, (0, 0, 0)).get_width() > 4:
                return f
        return pygame.font.SysFont(None, size, bold=bold)

    cw = layout.CARD_W
    return {
        "xl":  best(max(24, cw - 2),  bold=True),
        "lg":  best(max(18, cw - 8),  bold=True),
        "md":  best(max(15, cw - 12)),
        "sm":  best(max(13, cw - 14)),
        "xs":  best(max(11, cw - 18)),
        "xxs": best(max(10, cw - 20)),
    }


# ── Card drawing ──────────────────────────────────────────────────────────────
def card_colors(card: Card):
    if card.is_red_ten():   return C_RED_TEN_BG, C_RED_TEN_FG
    if card.is_big_joker(): return C_JOKER_B_BG, C_JOKER_FG
    if card.is_small_joker():return C_JOKER_S_BG, C_JOKER_FG
    fg = C_RED_SUIT if card.suit in (Suit.HEARTS, Suit.DIAMONDS) else C_BLACK_SUIT
    return C_CARD_FACE, fg


def draw_card(surf, card: Card, x, y, fonts, layout: Layout, highlight=False):
    cw, ch = layout.CARD_W, layout.CARD_H
    bg, fg = card_colors(card)
    rect = pygame.Rect(x, y, cw, ch)
    pygame.draw.rect(surf, bg, rect, border_radius=4)
    border = C_HIGHLIGHT if highlight else (90, 90, 70)
    pygame.draw.rect(surf, border, rect, 3 if highlight else 1, border_radius=4)

    if card.is_big_joker() or card.is_small_joker():
        t = fonts["xs"].render(RANK_LBL[card.rank], True, fg)
        surf.blit(t, (x + cw // 2 - t.get_width() // 2, y + ch // 2 - t.get_height() // 2))
    else:
        rt = fonts["sm"].render(RANK_LBL[card.rank], True, fg)
        rs = fonts["xs"].render(SUIT_SYM.get(card.suit, ""), True, fg)
        surf.blit(rt, (x + 3, y + 2))
        surf.blit(rs, (x + 3, y + 2 + rt.get_height()))
        if card.is_red_ten():
            star = fonts["xs"].render("★", True, C_RED_TEN_FG)
            surf.blit(star, (x + cw - star.get_width() - 2, y + ch - star.get_height() - 2))


def draw_fan(surf, cards: list, cx, cy, fonts, layout: Layout,
             highlight_set=None, max_w=None):
    if not cards:
        return
    highlight_set = highlight_set or set()
    cw, ch = layout.CARD_W, layout.CARD_H
    max_w  = max_w or layout.TABLE_W - 20
    n  = len(cards)
    ov = min(layout.OVERLAP, max(4, (max_w - cw) // max(1, n - 1)))
    tw = cw + (n - 1) * ov
    sx = cx - tw // 2
    sy = cy - ch // 2
    for i, card in enumerate(cards):
        draw_card(surf, card, sx + i * ov, sy, fonts, layout,
                  highlight=card in highlight_set)


# ── Clickable button ──────────────────────────────────────────────────────────
class Button:
    def __init__(self, rect: pygame.Rect, label: str, key: str):
        self.rect  = rect
        self.label = label
        self.key   = key
        self._hover = False

    def update(self, mouse_pos):
        self._hover = self.rect.collidepoint(mouse_pos)

    def draw(self, surf, fonts, active=False):
        col = C_BTN_ACTIVE if active else (C_BTN_HOVER if self._hover else C_BTN)
        pygame.draw.rect(surf, col, self.rect, border_radius=7)
        pygame.draw.rect(surf, C_BTN_BORDER, self.rect, 2, border_radius=7)
        t = fonts["md"].render(self.label, True, C_TEXT)
        surf.blit(t, (self.rect.centerx - t.get_width() // 2,
                      self.rect.centery - t.get_height() // 2))

    def clicked(self, event) -> bool:
        return (event.type == pygame.MOUSEBUTTONDOWN
                and event.button == 1
                and self.rect.collidepoint(event.pos))


def build_buttons(layout: Layout) -> list[Button]:
    bw, bh = layout.BTN_W, layout.BTN_H
    gap    = max(8, layout.W // 160)
    labels = [("⏮  Restart", "restart"), ("◀  Back", "prev"),
              ("▶  Play",   "play"),    ("⏸  Pause", "pause"),
              ("▶  Next",   "next"),    ("🐢 Slower", "slower"),
              ("🐇 Faster", "faster")]
    total  = len(labels) * bw + (len(labels) - 1) * gap
    sx     = layout.TABLE_W // 2 - total // 2
    by     = layout.H - layout.CTRL_H + (layout.CTRL_H - bh) // 2
    return [Button(pygame.Rect(sx + i * (bw + gap), by, bw, bh), lbl, key)
            for i, (lbl, key) in enumerate(labels)]


# ── Player area ───────────────────────────────────────────────────────────────
def draw_player(surf, p: int, snap: GameSnapshot, fonts, layout: Layout, is_leader: bool):
    cx, cy  = layout.SEAT[p]
    hand    = snap.hands[p]
    ident   = snap.identities[p]
    done    = snap.finished[p]
    cw, ch  = layout.CARD_W, layout.CARD_H

    badge_w = min(max(cw + 30, len(hand) * layout.OVERLAP + cw + 24), layout.TABLE_W - 20)
    badge_h = ch + 52
    bx, by  = cx - badge_w // 2, cy - badge_h // 2

    border = (C_HIGHLIGHT if is_leader else
              C_RED_TEAM  if ident == Team.RED else
              C_NON_TEAM  if ident == Team.NON_RED else C_UNKNOWN)
    pygame.draw.rect(surf, (18, 55, 22), (bx, by, badge_w, badge_h), border_radius=8)
    pygame.draw.rect(surf, border, (bx, by, badge_w, badge_h), 3 if is_leader else 2, border_radius=8)

    # Name
    name = f"P{p}"
    if done:
        name += f"  ✓ #{snap.finish_order.index(p) + 1}"
    if   ident == Team.RED:     name += "  ♥ Red"
    elif ident == Team.NON_RED: name += "  ○ Non-Red"
    col = (C_FINISHED if done else
           C_RED_TEAM  if ident == Team.RED else
           C_NON_TEAM  if ident == Team.NON_RED else C_TEXT)
    nl = fonts["sm"].render(name, True, col)
    surf.blit(nl, (bx + 6, by + 4))

    # Score
    sc = fonts["xs"].render(
        f"hand {snap.trick_scores[p]}  total {snap.cumulative_scores[p]}",
        True, C_TEXT_DIM)
    surf.blit(sc, (bx + badge_w - sc.get_width() - 6, by + 4))

    # Card count
    cnt = fonts["xs"].render(f"{len(hand)} cards", True, C_TEXT_DIM)
    surf.blit(cnt, (bx + 6, by + badge_h - cnt.get_height() - 4))

    draw_fan(surf, hand, cx, by + 26 + ch // 2, fonts, layout, max_w=badge_w - 12)


# ── Trick zone ────────────────────────────────────────────────────────────────
def draw_trick_zone(surf, snap: GameSnapshot, fonts, layout: Layout):
    tcx, tcy = layout.TRICK_CX, layout.TRICK_CY
    ew = int(layout.TABLE_W * 0.33)
    eh = int((layout.H - layout.CTRL_H) * 0.36)
    pygame.draw.ellipse(surf, C_TABLE, (tcx - ew // 2, tcy - eh // 2, ew, eh))
    pygame.draw.ellipse(surf, (30, 85, 42), (tcx - ew // 2, tcy - eh // 2, ew, eh), 2)

    if snap.trick_number > 0:
        lbl = fonts["sm"].render(f"Trick {snap.trick_number}", True, C_TEXT_DIM)
        surf.blit(lbl, (tcx - lbl.get_width() // 2, tcy - eh // 2 + 4))

    cw, ch = layout.CARD_W, layout.CARD_H
    for p_idx, move in snap.trick_plays:
        if move.is_pass():
            continue
        ox, oy = layout.TRICK_OFF[p_idx]
        cards  = move.cards
        n      = len(cards)
        ov     = min(10, max(4, (cw * 2) // max(1, n)))
        tw2    = cw + (n - 1) * ov
        sx     = tcx + ox - tw2 // 2
        sy     = tcy + oy - ch // 2
        winner = (snap.trick_winner == p_idx)
        for i, card in enumerate(cards):
            draw_card(surf, card, sx + i * ov, sy, fonts, layout, highlight=winner)
        pl = fonts["xs"].render(f"P{p_idx}", True, C_TEXT_DIM)
        surf.blit(pl, (tcx + ox - pl.get_width() // 2, tcy + oy + ch // 2 + 3))

    if snap.trick_winner is not None:
        ox, oy = layout.TRICK_OFF[snap.trick_winner]
        r = int(min(layout.CARD_W, layout.CARD_H) * 0.65)
        pygame.draw.circle(surf, C_WINNER_GLOW, (tcx + ox, tcy + oy), r, 3)


# ── Score panel ───────────────────────────────────────────────────────────────
def draw_panel(surf, snap: GameSnapshot, fonts, layout: Layout,
               events: list, ev_idx: int):
    px = layout.TABLE_W
    pw = layout.PANEL_W
    pygame.draw.rect(surf, C_PANEL, (px, 0, pw, layout.H))
    pygame.draw.line(surf, C_PANEL_LINE, (px, 0), (px, layout.H), 2)

    y = 14
    t = fonts["lg"].render("Score Board", True, C_TEXT)
    surf.blit(t, (px + pw // 2 - t.get_width() // 2, y));  y += t.get_height() + 8
    pygame.draw.line(surf, C_PANEL_LINE, (px + 8, y), (px + pw - 8, y));  y += 8

    hdr = fonts["xs"].render("      Hand   Total", True, C_TEXT_DIM)
    surf.blit(hdr, (px + 10, y));  y += hdr.get_height() + 3

    for p in range(6):
        ident = snap.identities[p]
        col   = (C_RED_TEAM  if ident == Team.RED else
                 C_NON_TEAM  if ident == Team.NON_RED else C_TEXT)
        fin   = " ✓" if snap.finished[p] else "  "
        row   = f"P{p}{fin}  {snap.trick_scores[p]:5d}  {snap.cumulative_scores[p]:6d}"
        t = fonts["sm"].render(row, True, col)
        surf.blit(t, (px + 10, y));  y += t.get_height() + 4

    y += 4
    pygame.draw.line(surf, C_PANEL_LINE, (px + 8, y), (px + pw - 8, y));  y += 8

    el = fonts["xxs"].render("Event log", True, C_TEXT_DIM)
    surf.blit(el, (px + 10, y));  y += el.get_height() + 4

    # How many lines fit in the remaining space?
    bottom     = layout.H - layout.CTRL_H - 4
    line_h     = fonts["xxs"].get_height() + 2
    num_visible = max(1, (bottom - y) // line_h)

    # Pin current event at the bottom of the visible window
    start = max(0, ev_idx - num_visible + 1)
    end   = min(start + num_visible, len(events))

    for i in range(start, end):
        col  = C_HIGHLIGHT if i == ev_idx else C_TEXT_DIM
        desc = events[i].description[:38]
        t    = fonts["xxs"].render(desc, True, col)
        surf.blit(t, (px + 6, y))
        y   += line_h


# ── Annotation ────────────────────────────────────────────────────────────────
def draw_annotation(surf, event: GameEvent, fonts, layout: Layout):
    important = event.kind in ("reveal", "guan_ren", "san_hong_shi", "hand_end",
                                "finish", "gui_zhu", "mo_gong", "trick_end")
    if not important:
        return
    col = {"reveal": C_STAR, "guan_ren": C_WINNER_GLOW, "san_hong_shi": C_WINNER_GLOW,
           "hand_end": C_HIGHLIGHT, "finish": C_FINISHED, "gui_zhu": C_NON_TEAM,
           "mo_gong": C_RED_TEAM,
           "trick_end": C_HIGHLIGHT if event.points > 0 else C_TEXT_DIM,
           }.get(event.kind, C_TEXT)
    lbl = fonts["md"].render(event.description, True, col)
    tcx, tcy = layout.TRICK_CX, layout.TRICK_CY
    eh  = int((layout.H - layout.CTRL_H) * 0.36)
    lx  = tcx - lbl.get_width() // 2
    ly  = tcy + eh // 2 + 8
    shd = fonts["md"].render(event.description, True, (0, 0, 0))
    surf.blit(shd, (lx + 1, ly + 1))
    surf.blit(lbl, (lx, ly))


# ── Hand-end overlay ──────────────────────────────────────────────────────────
def draw_hand_end_overlay(surf, event: GameEvent, fonts, layout: Layout):
    if event.kind != "hand_end" or event.result is None:
        return
    result = event.result
    snap   = event.snapshot

    ow = min(560, int(layout.TABLE_W * 0.40))
    oh = min(400, int((layout.H - layout.CTRL_H) * 0.44))
    ox = layout.TABLE_W // 2 - ow // 2
    oy = (layout.H - layout.CTRL_H) // 2 - oh // 2

    pygame.draw.rect(surf, (8, 36, 12), (ox, oy, ow, oh), border_radius=12)
    pygame.draw.rect(surf, C_HIGHLIGHT, (ox, oy, ow, oh), 2, border_radius=12)

    y = oy + 14
    title = fonts["xl"].render(f"Hand {snap.hand_number} Result", True, C_HIGHLIGHT)
    surf.blit(title, (ox + ow // 2 - title.get_width() // 2, y));  y += title.get_height() + 8

    tlbl = {"NORMAL": "Normal", "GUAN_REN": "★★ 关人！",
            "SAN_HONG_SHI": "★★★ 3红十！"}.get(result.terminal.name, result.terminal.name)
    tl = fonts["lg"].render(tlbl, True, C_WINNER_GLOW)
    surf.blit(tl, (ox + ow // 2 - tl.get_width() // 2, y));  y += tl.get_height() + 10

    for team, col in ((Team.RED, C_RED_TEAM), (Team.NON_RED, C_NON_TEAM)):
        label = "Red Team" if team == Team.RED else "Non-Red Team"
        score = result.final_team_scores[team]
        t = fonts["md"].render(f"{label}:  {score} pts", True, col)
        surf.blit(t, (ox + 20, y));  y += t.get_height() + 5

    y += 4
    for p in range(6):
        team = Team.RED if p in result.red_team else Team.NON_RED
        col  = C_RED_TEAM if team == Team.RED else C_NON_TEAM
        pos  = snap.finish_order.index(p) + 1 if p in snap.finish_order else "?"
        dg   = " 大贡" if p == result.da_gong else ""
        mg   = " 末贡" if p in result.mo_gong else ""
        row  = f"  P{p}  #{pos}{dg}{mg}   {result.final_scores[p]} pts"
        t    = fonts["sm"].render(row, True, col)
        surf.blit(t, (ox + 20, y));  y += t.get_height() + 3

    cont = fonts["xs"].render("Press Space or → to continue", True, C_TEXT_DIM)
    surf.blit(cont, (ox + ow // 2 - cont.get_width() // 2, oy + oh - cont.get_height() - 8))


# ── Controls bar ─────────────────────────────────────────────────────────────
def draw_controls(surf, buttons: list[Button], playing: bool, speed_idx: int,
                  ev_idx: int, total: int, fonts, layout: Layout, mouse_pos):
    y = layout.H - layout.CTRL_H
    pygame.draw.rect(surf, C_CTRL_BG, (0, y, layout.W, layout.CTRL_H))
    pygame.draw.line(surf, C_PANEL_LINE, (0, y), (layout.W, y))

    for btn in buttons:
        btn.update(mouse_pos)
        if btn.key == "play"  and playing:      continue
        if btn.key == "pause" and not playing:  continue
        is_active = (btn.key == "pause" and playing)
        btn.draw(surf, fonts, active=is_active)

    ms  = SPEED_LEVELS[speed_idx]
    inf = fonts["xs"].render(
        f"Speed: {ms}ms   Event {ev_idx + 1}/{total}   [Space  ← →  ↑↓  R  Q]",
        True, C_TEXT_DIM)
    surf.blit(inf, (layout.W - inf.get_width() - 14,
                    y + layout.CTRL_H // 2 - inf.get_height() // 2))


# ── Helpers ───────────────────────────────────────────────────────────────────
def current_leader(events: list, ev_idx: int) -> Optional[int]:
    for i in range(ev_idx, -1, -1):
        ev = events[i]
        if ev.kind in ("hand_start", "deal"):
            return None
        if ev.kind == "lead":
            return ev.player
    return None


def record_session(num_hands: int = 3, tier: str = "rule") -> list[GameEvent]:
    from session import make_players
    renderer = GUIRenderer()
    players  = make_players(tier)
    session  = GameSession(players, renderer)
    session.run(num_hands=num_hands)
    return renderer.events


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    import argparse
    ap = argparse.ArgumentParser(description="Red Ten Poker GUI")
    ap.add_argument("hands", nargs="?", type=int, default=3, help="Number of hands")
    ap.add_argument("--tier", default="rule",
                    choices=["rule", "search", "mixed"],
                    help="rule=Tier1, search=Tier2, mixed=Tier1 vs Tier2")
    args = ap.parse_args()

    print(f"Recording game session (tier={args.tier}, hands={args.hands})…")
    events = record_session(args.hands, tier=args.tier)
    print(f"Recorded {len(events)} events. Launching GUI…")

    pygame.init()
    screen = pygame.display.set_mode((1600, 950), pygame.RESIZABLE)
    pygame.display.set_caption("Red Ten Poker  红十")
    clock  = pygame.time.Clock()

    layout  = Layout(*screen.get_size())
    fonts   = load_fonts(layout)
    buttons = build_buttons(layout)

    ev_idx    = 0
    playing   = True
    speed_idx = SPEED_DEFAULT
    last_step = pygame.time.get_ticks()
    paused_at_hand_end = False

    while True:
        now       = pygame.time.get_ticks()
        mouse_pos = pygame.mouse.get_pos()

        for evt in pygame.event.get():
            if evt.type == pygame.QUIT:
                pygame.quit(); sys.exit()

            # Window resize — recompute everything that depends on size
            if evt.type == pygame.VIDEORESIZE:
                screen  = pygame.display.set_mode(evt.size, pygame.RESIZABLE)
                layout  = Layout(*screen.get_size())
                fonts   = load_fonts(layout)
                buttons = build_buttons(layout)

            for btn in buttons:
                if btn.clicked(evt):
                    if btn.key == "restart":
                        ev_idx = 0; playing = False; paused_at_hand_end = False
                    elif btn.key == "prev":
                        ev_idx = max(ev_idx - 1, 0); last_step = now
                    elif btn.key in ("play", "pause"):
                        if paused_at_hand_end:
                            paused_at_hand_end = False
                            ev_idx = min(ev_idx + 1, len(events) - 1)
                            playing = True
                        else:
                            playing = not playing
                        last_step = now
                    elif btn.key == "next":
                        if paused_at_hand_end:
                            paused_at_hand_end = False
                        ev_idx = min(ev_idx + 1, len(events) - 1)
                        last_step = now
                    elif btn.key == "slower":
                        speed_idx = min(speed_idx + 1, len(SPEED_LEVELS) - 1)
                    elif btn.key == "faster":
                        speed_idx = max(speed_idx - 1, 0)

            if evt.type == pygame.KEYDOWN:
                if evt.key in (pygame.K_q, pygame.K_ESCAPE):
                    pygame.quit(); sys.exit()
                elif evt.key == pygame.K_SPACE:
                    if paused_at_hand_end:
                        paused_at_hand_end = False
                        ev_idx = min(ev_idx + 1, len(events) - 1)
                        playing = True
                    else:
                        playing = not playing
                    last_step = now
                elif evt.key == pygame.K_RIGHT:
                    if paused_at_hand_end:
                        paused_at_hand_end = False
                        ev_idx = min(ev_idx + 1, len(events) - 1)
                    else:
                        ev_idx = min(ev_idx + 1, len(events) - 1)
                    last_step = now
                elif evt.key == pygame.K_LEFT:
                    ev_idx = max(ev_idx - 1, 0); last_step = now
                elif evt.key == pygame.K_UP:
                    speed_idx = max(speed_idx - 1, 0)
                elif evt.key == pygame.K_DOWN:
                    speed_idx = min(speed_idx + 1, len(SPEED_LEVELS) - 1)
                elif evt.key == pygame.K_r:
                    ev_idx = 0; playing = False; paused_at_hand_end = False

        # Auto-advance — but never auto-advance past hand_end while result is showing
        delay = SPEED_LEVELS[speed_idx]
        if playing and not paused_at_hand_end and now - last_step >= delay:
            if ev_idx < len(events) - 1:
                # Check BEFORE advancing so we can pause ON the hand_end event
                if events[ev_idx].kind == "hand_end":
                    paused_at_hand_end = True
                    playing = False
                else:
                    ev_idx   += 1
                    last_step = now
                    if events[ev_idx].kind == "hand_end":
                        paused_at_hand_end = True
                        playing = False
            else:
                playing = False

        # Render
        event = events[ev_idx]
        snap  = event.snapshot

        screen.fill(C_BG)
        leader = current_leader(events, ev_idx)
        for p in range(6):
            draw_player(screen, p, snap, fonts, layout, leader == p)
        draw_trick_zone(screen, snap, fonts, layout)
        draw_annotation(screen, event, fonts, layout)
        if event.kind == "hand_end":
            draw_hand_end_overlay(screen, event, fonts, layout)
        draw_panel(screen, snap, fonts, layout, events, ev_idx)
        draw_controls(screen, buttons, playing, speed_idx,
                      ev_idx, len(events), fonts, layout, mouse_pos)

        pygame.display.flip()
        clock.tick(60)


if __name__ == "__main__":
    main()
