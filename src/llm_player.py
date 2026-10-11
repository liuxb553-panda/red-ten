"""
LLM seat — a local language model picks the play.

The model is shown every distinct legal play as a numbered list plus a text
view of the table (see llm_view.py) and answers with a number. The reply is
validated; a bad reply gets one retry, then the turn falls back to
RuleBasedPlayer so a slow or broken model can never stall a game.

Rules and strategy text come from the files named in the model's config
(skills/*.zh.md), so play can be tuned without touching code.
"""
from __future__ import annotations
import datetime
import json
import os
import re
import time
from typing import Callable, Optional

from moves import Move
from state import GameState
from hand import Player
from rule_player import RuleBasedPlayer
from llm_client import LLMError, ModelConfig, chat_completion
from llm_view import build_options, build_view

_REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DEFAULT_LOG_DIR = os.path.join(_REPO, "debug_logs", "llm")

_OUTPUT_RULE = (
    "每次轮到你时，程序会列出所有合法的出牌并编号，你只能从中选一个。\n"
    '只输出一行 JSON：{"move": 编号, "reason": "不超过20字的理由"}。不要输出别的内容。'
)

_THINK_RE = re.compile(r"<think>.*?</think>", re.S)
_MOVE_RE = re.compile(r'"move"\s*:\s*"?\s*(-?\d+)')
_REASON_RE = re.compile(r'"reason"\s*:\s*"([^"]*)"')

_prompt_cache: dict[tuple[str, str], str] = {}


def parse_choice(reply: str, n_options: int) -> Optional[int]:
    """Extract the 1-based option number from a model reply, or None."""
    text = _THINK_RE.sub("", reply or "")
    if "<think>" in text:                      # unterminated thinking block
        text = text.split("<think>")[0]
    m = _MOVE_RE.search(text)
    if m:
        n = int(m.group(1))
    else:
        if '"reason"' in text:
            return None
        nums = set(re.findall(r"-?\d+", text))
        if len(nums) != 1:
            return None
        n = int(nums.pop())
    return n if 1 <= n <= n_options else None


def system_prompt(cfg: ModelConfig) -> str:
    """Rules + strategy + output format. Identical for every seat using the
    same model, so the server can cache it as a shared prefix."""
    key = (cfg.rules_file, cfg.skill_file)
    if key not in _prompt_cache:
        parts = []
        for rel in key:
            path = rel if os.path.isabs(rel) else os.path.join(_REPO, rel)
            with open(path, encoding="utf-8") as f:
                parts.append(f.read().strip())
        parts.append(_OUTPUT_RULE)
        _prompt_cache[key] = "\n\n".join(parts)
    return _prompt_cache[key]


class LLMPlayer(Player):
    """A seat played by a language model behind an OpenAI-compatible API."""

    # SeatController adds an artificial "thinking" pause for AI seats;
    # a model call is slow enough already.
    has_own_latency = True

    def __init__(self, player_id: int, config: ModelConfig,
                 chat: Optional[Callable[[list[dict]], str]] = None,
                 fallback: Optional[Player] = None,
                 log_dir: Optional[str] = None):
        super().__init__(player_id)
        self.config = config
        self._chat = chat or (lambda messages: chat_completion(config, messages))
        self._fallback = fallback or RuleBasedPlayer(player_id)
        self._log_dir = log_dir or DEFAULT_LOG_DIR
        self.stats = {"decisions": 0, "model_calls": 0, "retries": 0,
                      "fallbacks": 0, "latency_s": 0.0}

    def choose_action(self, state: GameState, legal_moves: list[Move]) -> Move:
        if not legal_moves:
            raise RuntimeError(f"P{self.id}: no legal moves")
        if len(legal_moves) == 1:
            return legal_moves[0]

        options = build_options(legal_moves)
        if len(options) == 1:
            return options[0].move

        view = build_view(state, self.id, options)
        messages = [{"role": "system", "content": system_prompt(self.config)},
                    {"role": "user", "content": view}]

        self.stats["decisions"] += 1
        replies: list[str] = []
        choice: Optional[int] = None
        error = ""
        t0 = time.time()
        try:
            for attempt in range(2):
                self.stats["model_calls"] += 1
                reply = self._chat(messages)
                replies.append(reply)
                choice = parse_choice(reply, len(options))
                if choice is not None:
                    break
                if attempt == 0:
                    self.stats["retries"] += 1
                    messages = messages + [
                        {"role": "assistant", "content": reply},
                        {"role": "user", "content":
                            f'回答无效。请只输出 {{"move": 编号}}，编号必须在 1 到 {len(options)} 之间。'},
                    ]
        except LLMError as e:
            error = str(e)
        latency = time.time() - t0
        self.stats["latency_s"] += latency

        if choice is not None:
            move = options[choice - 1].move
        else:
            self.stats["fallbacks"] += 1
            move = self._fallback.choose_action(state, legal_moves)
            if move not in legal_moves:
                move = legal_moves[0]

        self._log(view, options, replies, choice, move, latency, error)
        return move

    def _log(self, view, options, replies, choice, move, latency, error) -> None:
        reason = ""
        if replies:
            m = _REASON_RE.search(replies[-1])
            reason = m.group(1) if m else ""
        record = {
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "seat": self.id,
            "model": self.config.name,
            "n_options": len(options),
            "choice": choice,
            "move": str(move),
            "reason": reason,
            "fallback": choice is None,
            "error": error,
            "latency_ms": round(latency * 1000),
            "replies": replies,
            "view": view,
        }
        try:
            os.makedirs(self._log_dir, exist_ok=True)
            path = os.path.join(self._log_dir, f"{datetime.date.today().isoformat()}.jsonl")
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass
