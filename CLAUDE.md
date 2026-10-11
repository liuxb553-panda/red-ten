# Red Ten Poker — Claude Code Notes

See @AGENTS.md for working rules.

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

## Testing (P0+P1 done, P2 deferred)

- **pytest** ✅ — `pyproject.toml` with `pythonpath = ["src"]`, 15 tests passing
- **hypothesis** ✅ — `tests/test_moves_properties.py` with 8 invariant tests
- **mypy** ✅ — `mypy.ini` configured, zero type errors
- **Stop hook** ✅ — auto-runs `python -m pytest tests/ -q` before each turn ends
- **CI** ⬜ — GitHub Actions (deferred)

Run verification:
```bash
python -m pytest tests/ -v --tb=short
mypy src/
```
