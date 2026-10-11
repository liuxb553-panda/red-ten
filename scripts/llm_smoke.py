"""
Play headless hands with LLM seats against rule-based seats and report how the
model behaved: decisions, options per decision, latency, retries, fallbacks.

Needs the model server named in config/llm_models.json to be running.

Usage:
    python scripts/llm_smoke.py                       # 1 hand, seat 0 is the LLM
    python scripts/llm_smoke.py --seats 0 3 --hands 2
    python scripts/llm_smoke.py --model gemma4-e4b --seed 5 --verbose
"""
from __future__ import annotations
import argparse
import os
import random
import statistics
import sys
import time

_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
sys.path.insert(0, _SRC)
sys.path.insert(0, os.path.join(_SRC, "agents"))

from hand import Hand                      # noqa: E402
from logger import GameLogger              # noqa: E402
from rule_player import RuleBasedPlayer    # noqa: E402
from llm_client import get_model           # noqa: E402
from llm_player import LLMPlayer           # noqa: E402


class _TimedLLMPlayer(LLMPlayer):
    """Records per-decision latency and option counts."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.samples: list[tuple[float, int]] = []

    def _log(self, view, options, replies, choice, move, latency, error):
        self.samples.append((latency, len(options)))
        super()._log(view, options, replies, choice, move, latency, error)
        if self.verbose:
            tag = "FALLBACK" if choice is None else f"#{choice}"
            last = replies[-1].strip().replace("\n", " ")[:70] if replies else error
            print(f"  P{self.id} {len(options):3d} options {latency:5.1f}s {tag:8s} "
                  f"→ {move}   | {last}")

    verbose = False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None, help="name in config/llm_models.json")
    ap.add_argument("--seats", type=int, nargs="+", default=[0], help="LLM seats (0-5)")
    ap.add_argument("--hands", type=int, default=1)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    cfg = get_model(args.model)
    print(f"model={cfg.name}  url={cfg.base_url}  LLM seats={args.seats}  "
          f"hands={args.hands}  seed={args.seed}")

    _TimedLLMPlayer.verbose = args.verbose
    llm_seats: list[_TimedLLMPlayer] = []
    players: list = []
    for i in range(6):
        if i in args.seats:
            p = _TimedLLMPlayer(i, cfg)
            llm_seats.append(p)
            players.append(p)
        else:
            players.append(RuleBasedPlayer(i))

    t0 = time.time()
    for h in range(args.hands):
        random.seed(args.seed + h)
        hand = Hand(players, random.randint(0, 5), GameLogger(verbose=False))
        hand.deal()
        result = hand.play()
        red = [f"P{p}" for p in result.red_team]
        print(f"hand {h + 1}: {result.terminal.name}  red={red}  "
              f"finish={result.finish_order}  scores={result.final_scores}")
    elapsed = time.time() - t0

    lat = [s[0] for p in llm_seats for s in p.samples]
    opts = [s[1] for p in llm_seats for s in p.samples]
    total = {k: sum(p.stats[k] for p in llm_seats)
             for k in ("decisions", "model_calls", "retries", "fallbacks")}
    print(f"\ndecisions={total['decisions']}  model_calls={total['model_calls']}  "
          f"retries={total['retries']}  fallbacks={total['fallbacks']}")
    if lat:
        print(f"options per decision: median={statistics.median(opts):.0f}  max={max(opts)}")
        print(f"latency per decision: median={statistics.median(lat):.1f}s  "
              f"max={max(lat):.1f}s  total={sum(lat):.0f}s of {elapsed:.0f}s")


if __name__ == "__main__":
    main()
