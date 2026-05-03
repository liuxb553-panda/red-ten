"""
Usage: python3 src/debug_inspect.py <ROOM_CODE> <FLAG_ID>

Finds a debug flag in debug_logs/<ROOM>.jsonl and prints:
  - the your_turn context immediately before the flag (legal moves + hand)
  - the 5 events leading up to it for trick context
"""
import json
import sys
import os

LOGS_DIR = os.path.join(os.path.dirname(__file__), "..", "debug_logs")

RANK_ORDER = {"3":3,"4":4,"5":5,"6":6,"7":7,"8":8,"9":9,"10":10,
              "J":11,"Q":12,"K":13,"A":14,"2":15,"小王":16,"大王":17}


def load_jsonl(room: str) -> list[dict]:
    path = os.path.join(LOGS_DIR, f"{room.upper()}.jsonl")
    if not os.path.exists(path):
        sys.exit(f"No log file for room {room.upper()} at {path}")
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def fmt_card(c: dict) -> str:
    if c.get("bj"): return "大王"
    if c.get("sj"): return "小王"
    suit_sym = {"HEARTS": "♥", "DIAMONDS": "♦", "CLUBS": "♣", "SPADES": "♠"}.get(c["s"], "")
    star = "★" if c.get("rt") else ""
    return f"{c['rl']}{suit_sym}{star}"


def fmt_move(m: dict) -> str:
    if m is None: return "—"
    if m.get("pass"): return "pass"
    cards = " ".join(fmt_card(c) for c in m["cards"])
    return f"{cards}  [{m['desc']}]{'  BOMB' if m.get('bomb') else ''}"


def fmt_hand(cards: list[dict]) -> str:
    ranked = sorted(cards, key=lambda c: (RANK_ORDER.get(c["rl"], 0), c["s"]))
    return "  ".join(fmt_card(c) for c in ranked)


def fmt_event(ev: dict) -> str:
    kind = ev["kind"]
    p = ev.get("player")
    prefix = f"P{p}" if p is not None else "  "
    if kind == "your_turn":
        return f"  [{prefix} your_turn]  {len(ev.get('legal_moves', []))} legal moves"
    if kind in ("lead", "action"):
        m = ev.get("move") or {}
        desc = m.get("desc", "") if not m.get("pass") else "pass"
        bomb = "  BOMB" if m.get("bomb") else ""
        cards = " ".join(fmt_card(c) for c in m.get("cards", []))
        return f"  [{prefix} {kind}]  {cards}  [{desc}]{bomb}"
    if kind == "trick_end":
        snap = ev.get("snap", {})
        pts = ev.get("pts", 0)
        return f"  [trick_end]  winner=P{ev.get('winner')}  +{pts}pts"
    if kind == "hand_start":
        snap = ev.get("snap", {})
        return f"  [hand_start]  hand={snap.get('hn','?')}  first=P{p}"
    if kind == "flag":
        return f"  *** FLAG {ev['id']} @ {ev['timestamp']} ***"
    return f"  [{kind}]"


def main():
    if len(sys.argv) != 3:
        sys.exit("Usage: python3 src/debug_inspect.py <ROOM_CODE> <FLAG_ID>")

    room, flag_id = sys.argv[1].upper(), sys.argv[2].lower()
    lines = load_jsonl(room)

    # Find the flag
    flag_idx = next((i for i, ev in enumerate(lines) if ev.get("id") == flag_id), None)
    if flag_idx is None:
        sys.exit(f"Flag '{flag_id}' not found in debug_logs/{room}.jsonl")

    print(f"\n{'='*60}")
    print(f"  Room: {room}   Flag: {flag_id}   (line {flag_idx} in JSONL)")
    print(f"{'='*60}\n")

    # Print up to 5 events before the flag for trick context
    context_start = max(0, flag_idx - 6)
    context = lines[context_start:flag_idx + 1]

    print("── Context ──────────────────────────────────────────────────")
    for i, ev in enumerate(context):
        abs_i = context_start + i
        marker = " <-- FLAG" if ev.get("id") == flag_id else ""
        print(f"  [{abs_i:3d}] {fmt_event(ev)}{marker}")

    # Find the your_turn immediately before the flag (scan back)
    your_turn = next(
        (lines[i] for i in range(flag_idx - 1, -1, -1) if lines[i]["kind"] == "your_turn"),
        None
    )

    if your_turn:
        player = your_turn["player"]
        legal = your_turn.get("legal_moves", [])

        # Find snapshot: last regular event before the your_turn
        yt_idx = next(i for i, ev in enumerate(lines) if ev is your_turn)
        snap = next(
            (lines[i]["snap"] for i in range(yt_idx - 1, -1, -1) if "snap" in lines[i]),
            None
        )

        print(f"\n── P{player} legal moves ({len(legal)}) ─────────────────────────────")
        for m in legal:
            print(f"  [{m['idx']:2d}] {fmt_move(m)}")

        if snap:
            hand = snap["hands"][player]
            trick_plays = snap.get("tp", [])
            trick_scores = snap.get("ts", [])
            cumul = snap.get("cs", [])
            ids = snap.get("ids", [None]*6)
            fin = snap.get("fin", [False]*6)
            hand_n = snap.get("hn", "?")
            trick_n = snap.get("tn", "?")

            print(f"\n── P{player} hand  (hand {hand_n}, trick {trick_n}) ──────────────────────")
            print(f"  {fmt_hand(hand)}  ({len(hand)} cards)")

            print(f"\n── Current trick ────────────────────────────────────────────")
            if trick_plays:
                for p_idx, move in trick_plays:
                    print(f"  P{p_idx}: {fmt_move(move)}")
            else:
                print("  (empty — you are leading)")

            print(f"\n── Scores ───────────────────────────────────────────────────")
            for p in range(6):
                team = f"[{ids[p]}]" if ids[p] else "[?]"
                done = " DONE" if fin[p] else ""
                you = " ← you" if p == player else ""
                print(f"  P{p} {team:12s}  hand={trick_scores[p]:4d}  total={cumul[p]:4d}{done}{you}")
    else:
        print("\n  (no your_turn entry found before this flag)")

    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()
