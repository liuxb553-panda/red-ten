"""
Multiplayer room management.

SeatController  — one per seat; routes choose_action() to AI or a connected
                  human WebSocket.  The game loop runs in a background thread
                  and calls choose_action() synchronously; human moves cross
                  the thread boundary via a thread-safe queue.

LiveRenderer    — subclasses GUIRenderer to broadcast every game event to all
                  connected clients as it happens, in addition to recording
                  the event list for post-game replay.

GameRoom        — holds 6 seats, the game thread, and the broadcast machinery.

RoomManager     — creates and looks up rooms by code.
"""
from __future__ import annotations
import asyncio
import datetime
import json
import os
import queue
import random
import string
import sys as _sys
import threading
import time
import traceback as _tb
from typing import Optional, TYPE_CHECKING

from hand import Player
from state import GameState
from moves import Move
from gui_renderer import GUIRenderer, GameEvent
from serializers import ser_event, ser_event_pov, ser_move, ser_card

if TYPE_CHECKING:
    from fastapi import WebSocket

LOGS_DIR = os.path.join(os.path.dirname(__file__), "..", "debug_logs")


class SeatController(Player):
    """
    Wraps an AI player.  When a human WebSocket is attached the seat switches
    to human mode: choose_action() sends 'your_turn' to the client and blocks
    until the client replies with a move index or disconnects.
    """

    def __init__(self, seat_id: int, ai_player: Player):
        super().__init__(seat_id)
        self.ai_player = ai_player
        self._ws: Optional["WebSocket"] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._move_queue: queue.Queue[Optional[int]] = queue.Queue()
        self._lock = threading.Lock()
        self._room: Optional["GameRoom"] = None

    # ── connection management ─────────────────────────────────────────────────

    @property
    def is_human(self) -> bool:
        with self._lock:
            return self._ws is not None

    def attach(self, ws: "WebSocket", loop: asyncio.AbstractEventLoop) -> None:
        with self._lock:
            self._ws = ws
            self._loop = loop

    def detach(self) -> None:
        with self._lock:
            self._ws = None
            self._loop = None
        # Wake up any blocked choose_action() so it can fall back to AI.
        self._move_queue.put_nowait(None)

    def send(self, data: dict) -> None:
        """Schedule a send on the event loop from any thread."""
        with self._lock:
            ws, loop = self._ws, self._loop
        if ws and loop:
            asyncio.run_coroutine_threadsafe(ws.send_json(data), loop)

    def submit_move(self, move_idx: int) -> None:
        """Called by the WebSocket handler when the human picks a move."""
        self._move_queue.put_nowait(move_idx)

    # ── Player interface ──────────────────────────────────────────────────────

    def choose_action(self, state: GameState, legal_moves: list[Move]) -> Move:
        if not self.is_human:
            time.sleep(random.uniform(1.0, 3.0))
            return self.ai_player.choose_action(state, legal_moves)

        # Log the legal-moves set for debugging before asking the human.
        if self._room and self._room._renderer:
            self._room._renderer.log_debug_turn(
                self.id, [{**ser_move(m), "idx": i} for i, m in enumerate(legal_moves)]
            )

        # Send legal moves to the human client.
        self.send({
            "type": "your_turn",
            "legal_moves": [
                {"idx": i, "desc": str(m) if not m.is_pass() else "Pass",
                 "is_pass": m.is_pass(), "cards": [ser_card(c) for c in m.cards]}
                for i, m in enumerate(legal_moves)
            ],
        })

        # Block until the human replies, a timeout fires, or they disconnect.
        while True:
            try:
                val = self._move_queue.get(timeout=1.0)
            except queue.Empty:
                if not self.is_human:
                    return self.ai_player.choose_action(state, legal_moves)
                continue

            if val is None:
                # Disconnected sentinel — fall back to AI.
                return self.ai_player.choose_action(state, legal_moves)
            if 0 <= val < len(legal_moves):
                return legal_moves[val]
            # Invalid index — ask again.
            self.send({"type": "error", "msg": "Invalid move — try again."})


class LiveRenderer(GUIRenderer):
    """
    Extends GUIRenderer to broadcast every event to all connected clients
    as it happens, while still building the full event list for replay.
    Also appends every event to a JSONL log file for post-hoc debugging.
    """

    def __init__(self, room: "GameRoom"):
        super().__init__()
        self._room = room
        self._log_path = room._log_path

    def _emit(self, kind: str, desc: str, **kwargs) -> None:
        super()._emit(kind, desc, **kwargs)
        self._room.broadcast_event(self.events[-1])
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(ser_event(self.events[-1]), ensure_ascii=False) + "\n")
        except OSError:
            pass

    def log_debug_turn(self, player: int, serialized_moves: list) -> None:
        """Append a your_turn record to the JSONL log without broadcasting it."""
        record = {
            "kind":        "your_turn",
            "desc":        f"P{player}'s turn — {len(serialized_moves)} legal moves",
            "player":      player,
            "timestamp":   datetime.datetime.now().isoformat(timespec="seconds"),
            "legal_moves": serialized_moves,
        }
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass



class GameRoom:
    """
    Manages a single game: 6 SeatControllers, a background game thread,
    and broadcast helpers.
    """

    def __init__(self, room_code: str, ai_tier: str = "search",
                 n_samples: int = 12):
        self.room_code = room_code
        self.status = "lobby"   # lobby | running | done
        self.seats: list[SeatController] = []
        self._renderer: Optional[LiveRenderer] = None
        self._game_thread: Optional[threading.Thread] = None
        self._continue_event = threading.Event()

        os.makedirs(LOGS_DIR, exist_ok=True)
        self._log_path   = os.path.join(LOGS_DIR, f"{room_code}.jsonl")
        self._flags_path = os.path.join(LOGS_DIR, f"{room_code}_flags.json")

        from session import make_players
        for i, ai in enumerate(make_players(ai_tier, n_samples=n_samples)):
            seat = SeatController(i, ai)
            seat._room = self
            self.seats.append(seat)

    # ── broadcasting ──────────────────────────────────────────────────────────

    def broadcast(self, data: dict, only_seat: Optional[int] = None) -> None:
        """Send the same data to all (or one) connected human seat(s)."""
        for i, seat in enumerate(self.seats):
            if only_seat is not None and i != only_seat:
                continue
            seat.send(data)

    def broadcast_event(self, event: "GameEvent") -> None:
        """Send personalized game event — each seat sees only their own hand."""
        for i, seat in enumerate(self.seats):
            if seat.is_human:
                seat.send({"type": "game_event", "event": ser_event_pov(event, i)})

    def room_state_msg(self, pov_seat: int) -> dict:
        return {
            "type": "room_state",
            "room_code": self.room_code,
            "pov_seat": pov_seat,
            "seats": [
                {"seat": i, "mode": "human" if s.is_human else "ai",
                 "you": i == pov_seat}
                for i, s in enumerate(self.seats)
            ],
            "status": self.status,
        }

    # ── game lifecycle ────────────────────────────────────────────────────────

    def add_flag(self, note: str | None = None) -> dict:
        """Write a flag record into the JSONL log and the flags index."""
        import secrets
        flag_id = secrets.token_hex(4)
        ts = datetime.datetime.now().isoformat(timespec="seconds")
        record = {"kind": "flag", "id": flag_id, "timestamp": ts, "note": note}
        if self._renderer:
            try:
                with open(self._renderer._log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            except OSError:
                pass
        try:
            flags = json.loads(open(self._flags_path, encoding="utf-8").read()) \
                if os.path.exists(self._flags_path) else []
        except (OSError, json.JSONDecodeError):
            flags = []
        flags.append(record)
        with open(self._flags_path, "w", encoding="utf-8") as f:
            json.dump(flags, f, ensure_ascii=False, indent=2)
        return {
            "log_file":   os.path.basename(self._renderer._log_path if self._renderer else self._log_path),
            "flags_file": os.path.basename(self._flags_path),
            "flag_id":    flag_id,
            "flag_count": len(flags),
        }

    def signal_continue(self) -> None:
        """Signal the game thread to continue to the next hand."""
        self._continue_event.set()

    def _wait_for_continue(self, timeout: float = 120.0) -> None:
        """Block until a human signals continue, or timeout fires."""
        self._continue_event.wait(timeout=timeout)
        self._continue_event.clear()

    def start(self, num_hands: int = 3) -> None:
        if self.status != "lobby":
            return
        self.status = "running"
        self._renderer = LiveRenderer(self)
        self._game_thread = threading.Thread(
            target=self._run, args=(num_hands,), daemon=True
        )
        self._game_thread.start()

    def _run(self, num_hands: int) -> None:
        from session import GameSession
        try:
            GameSession(self.seats, self._renderer,
                        continue_cb=self._wait_for_continue).run(num_hands=num_hands)
        except Exception:
            exc = _sys.exc_info()
            try:
                crash = {
                    "room_code":   self.room_code,
                    "log_file":    os.path.basename(self._log_path),
                    "timestamp":   datetime.datetime.now().isoformat(timespec="seconds"),
                    "event_count": len(self._renderer.events) if self._renderer else 0,
                    "exc_type":    exc[0].__name__,
                    "exc_message": str(exc[1]),
                    "traceback":   "".join(_tb.format_exception(*exc)),
                }
                crash_path = os.path.join(LOGS_DIR, f"crash_{self.room_code}.json")
                with open(crash_path, "w", encoding="utf-8") as f:
                    json.dump(crash, f, indent=2, ensure_ascii=False)
            except Exception:
                pass
            raise
        finally:
            self.status = "done"
            replay = [ser_event(e) for e in self._renderer.events]
            self.broadcast({"type": "game_over", "replay": replay})


class RoomManager:
    def __init__(self):
        self._rooms: dict[str, GameRoom] = {}

    def create(self, ai_tier: str = "search") -> GameRoom:
        code = self._fresh_code()
        room = GameRoom(code, ai_tier=ai_tier)
        self._rooms[code] = room
        return room

    def get(self, code: str) -> Optional[GameRoom]:
        return self._rooms.get(code.upper())

    def _fresh_code(self) -> str:
        while True:
            code = "".join(random.choices(string.ascii_uppercase, k=4))
            if code not in self._rooms:
                return code
