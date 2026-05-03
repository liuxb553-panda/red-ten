# Red Ten Poker — Claude Code Notes

## Debug flag inspection

When Henry gives you a flag reference like:
> "room NKKK, flag 0a59be0b, check debug_logs/NKKK.jsonl"

Run this immediately — do not manually read the JSONL file:

```bash
python3 src/debug_inspect.py NKKK 0a59be0b
```

This prints the legal moves, the human player's current hand, the current trick state, and surrounding event context all in one shot. Use the output to answer the question.

## Project layout

- `src/` — Python backend (FastAPI server, game engine, AI players)
- `web/` — Frontend HTML/JS (index.html = replay viewer, play.html = multiplayer)
- `debug_logs/` — Per-room JSONL game logs + flag files (written at runtime)
- `docs/` — Design docs including `debug_snapshot_tool.md`
- `data/` — ML model checkpoints and self-play training data
- `tests/` — Integration and legal-move tests

## Running the server

```bash
python src/web_server.py   # http://localhost:5173
```
