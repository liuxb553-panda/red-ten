# Debug Snapshot Tool

## Purpose

When a bug is spotted during a live game, this tool lets Henry flag the moment, then hand a log file reference to Claude Code for analysis.

## How to use

1. During a game in `/play`, click the **🚩 Flag** button (top-left corner)
2. A toast appears and the reference is copied to clipboard:
   ```
   Flag a3f2b9c1 inserted — copied to clipboard
   ```
3. Paste the clipboard text to Claude Code (or any AI assistant):
   ```
   room ABCD, flag a3f2b9c1, check debug_logs/ABCD.jsonl
   ```
4. The assistant runs the inspect script to pull up full context:
   ```bash
   python3 src/debug_inspect.py ABCD a3f2b9c1
   ```

`debug_inspect.py` prints: legal moves at that moment, the human player's hand, the current trick state, and the 5 preceding events — everything needed to diagnose the issue in one command.

## Files produced

| File | Contents |
|---|---|
| `debug_logs/{ROOM}.jsonl` | One JSON object per line — every game event as it happened |
| `debug_logs/{ROOM}_flags.json` | List of `{id, timestamp, note}` flag records (same hash embedded in JSONL) |
| `debug_logs/crash_{ROOM}.json` | Auto-written on server exception; includes traceback |

The `.jsonl` file is written continuously as the game runs — it's always up to date, even mid-hand.

## JSONL event format

Regular game events (lead, action, trick_end, hand_end, etc.) use the standard `ser_event()` format:

```json
{"kind": "lead", "desc": "P2 leads: pair of Kings", "player": 2, "pts": 0,
 "move": {"cards": [...], "pass": false, "bomb": false, "desc": "pair of Kings"},
 "beats": null, "winner": null, "result": null,
 "snap": {"hands": [[...], ...], "ts": [...], "cs": [...], "ids": [...], ...}}
```

`your_turn` entries (written only for human seats, not broadcast) include the full legal moves list:

```json
{"kind": "your_turn", "desc": "P0's turn — 8 legal moves", "player": 0,
 "timestamp": "2026-05-02T10:30:15",
 "legal_moves": [{"cards": [...], "pass": false, "bomb": false, "desc": "pair of Kings", "idx": 0}, ...]}
```

## What Claude can diagnose from the log

| Symptom | Where to look |
|---|---|
| "Can't play valid cards" | `your_turn` event before the problem — check `legal_moves` list and `snap.hands` |
| Wrong trick winner | `trick_end` event + preceding `lead`/`action` events |
| Score calculation wrong | `hand_end` `result` field vs trick score accumulation in `snap.ts` |
| Wrong team assignment | `reveal` events, `snap.ids` progression |
| Server crash | `crash_{ROOM}.json` traceback + events before it in `.jsonl` |

## API endpoint

```
POST /api/debug-flag/{room_code}?note=optional+description
```

Returns `{"log_file": "ABCD.jsonl", "flags_file": "ABCD_flags.json", "event_idx": 47, "flag_count": 1}`.

## Implementation

- `src/room_manager.py` — `LiveRenderer._emit()` appends to `.jsonl`; `LiveRenderer.log_debug_turn()` appends `your_turn` records; `GameRoom.add_flag()` writes flag markers; crash capture in `GameRoom._run()`
- `src/web_server.py` — `POST /api/debug-flag/{code}` route
- `web/play.html` — 🚩 Flag button + toast UI
