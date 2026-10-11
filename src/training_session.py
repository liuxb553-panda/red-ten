"""
Training session manager — runs train_selfplay.run() in a background thread
with real-time progress callbacks streamed over a WebSocket.
"""
from __future__ import annotations
import asyncio
import os
import queue
import secrets
import sys
import threading
import time
import traceback
from typing import Optional

sys.path.insert(0, os.path.dirname(__file__))


class TrainingSession:
    def __init__(self, session_id: str, config: dict):
        self.id = session_id
        self.config = config
        self.active = True
        self._ws: Optional[any] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._send_queue = queue.Queue()
        self._flush_task: Optional[asyncio.Task] = None
        self._abort_flag = threading.Event()
        self._start_time = 0.0

    # ── WebSocket ──────────────────────────────────────────────────────────

    def attach_ws(self, ws, loop: asyncio.AbstractEventLoop):
        self._ws = ws
        self._loop = loop
        self._start_flush_task()

    def detach_ws(self):
        self._ws = None
        self._loop = None
        if self._flush_task:
            self._flush_task.cancel()
            self._flush_task = None

    def _start_flush_task(self):
        """Drain the send queue onto the WebSocket on the event loop."""
        async def _flush():
            while self._ws:
                # Drain all pending messages
                while self._ws:
                    try:
                        msg = self._send_queue.get_nowait()
                    except queue.Empty:
                        break
                    try:
                        if self._ws:
                            await self._ws.send_json(msg)
                    except Exception:
                        # WebSocket disconnected — stop flushing
                        return
                await asyncio.sleep(0.15)

        if self._loop:
            self._flush_task = self._loop.create_task(_flush())

    def _enqueue(self, msg: dict):
        self._send_queue.put(msg)

    def _send_direct(self, msg: dict):
        """Send a message directly via the event loop, bypassing the queue.
        Used for final messages (train_complete, train_aborted) that must
        go through even if the flush task is winding down."""
        ws, loop = self._ws, self._loop
        if ws and loop:
            asyncio.run_coroutine_threadsafe(ws.send_json(msg), loop)

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def start(self):
        self._start_time = time.time()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def abort(self):
        self.active = False
        self._abort_flag.set()

    # ── Runner ─────────────────────────────────────────────────────────────

    def _progress_cb(self, phase: str, info: dict):
        """Progress callback passed to train_selfplay.run()."""
        if phase == "collecting":
            self._enqueue({
                "type": "train_progress",
                "phase": "collecting",
                "hand": info.get("hand", 0),
                "total_hands": info.get("total_hands", 0),
            })
        elif phase == "training":
            self._enqueue({
                "type": "train_progress",
                "phase": "mlp_training",
                "epoch": info.get("epoch", 0),
                "epochs": info.get("epochs", 0),
                "train_loss": info.get("train_loss", 0),
                "val_loss": info.get("val_loss", 0),
            })
        elif phase == "benchmark_before":
            self._enqueue({
                "type": "train_phase",
                "phase": "benchmark_before",
            })
        elif phase == "benchmark":
            self._enqueue({
                "type": "benchmark_progress",
                "done": info.get("done", 0),
                "total": info.get("total", 0),
            })
        elif phase == "benchmark_after":
            self._enqueue({
                "type": "benchmark_result",
                "stage": "after",
                "wins": info.get("wins", 0),
                "losses": info.get("losses", 0),
                "ties": info.get("ties", 0),
                "win_pct": info.get("win_pct", 0),
            })

    def _run(self):
        try:
            from train_selfplay import run

            hands = self.config.get("hands", 100)
            reps = self.config.get("reps", 30)
            epsilon = self.config.get("epsilon", 0.2)
            opponent = self.config.get("opponent", "search")
            no_benchmark = self.config.get("no_benchmark", False)

            total_games = hands * reps

            # Create session directory for replay data
            ts = time.strftime("%Y%m%d_%H%M%S")
            session_dir = os.path.join("data", "training", f"session_{ts}")
            os.makedirs(os.path.join(session_dir, "hands"), exist_ok=True)

            # Save a copy of the starting model
            import shutil
            start_model = os.path.join("data", "model.pt")
            if os.path.exists(start_model):
                shutil.copy(start_model, os.path.join(session_dir, "model_before.pt"))

            self._enqueue({
                "type": "train_phase",
                "phase": "starting",
            })

            run(
                rounds=1,
                games_per_round=total_games,
                workers=min(4, os.cpu_count() or 4),
                keep=1,
                eps_start=epsilon,
                eps_end=epsilon,
                epochs=30,
                lr=3e-4,
                bench_n=0 if no_benchmark else 20,
                bench_seed=77,
                start_model=start_model,
                start_round=1,
                data_dir="data",
                label_mode="advantage",
                opponent=opponent,
                progress_cb=self._progress_cb,
                session_dir=session_dir,
            )

            # Save session metadata
            meta = {
                "hands": hands, "reps": reps, "epsilon": epsilon,
                "opponent": opponent, "elapsed_s": round(time.time() - self._start_time),
                "session_dir": session_dir,
            }
            import json as _json
            with open(os.path.join(session_dir, "meta.json"), "w") as f:
                _json.dump(meta, f, indent=2)

            elapsed = time.time() - self._start_time
            if self.active:
                self._send_direct({
                    "type": "train_complete",
                    "elapsed_s": round(elapsed),
                    "session_dir": session_dir,
                })

        except Exception:
            if self.active:
                self._send_direct({
                    "type": "error",
                    "msg": traceback.format_exc(),
                })
        finally:
            self.active = False


# ── Session manager ──────────────────────────────────────────────────────

class TrainingSessionManager:
    def __init__(self):
        self._sessions: dict[str, TrainingSession] = {}

    def create(self, config: dict) -> TrainingSession:
        sid = secrets.token_hex(6)
        session = TrainingSession(sid, config)
        self._sessions[sid] = session
        return session

    def get(self, sid: str) -> Optional[TrainingSession]:
        return self._sessions.get(sid)
