"""
Tests for how the LLM seat is exposed: tier names, per-seat battle config,
the /api/tiers payload, and the AI "thinking" pause. No model server needed —
constructing an LLMPlayer does not contact the model.
"""
import room_manager
from hand import Player
from llm_player import LLMPlayer
from moves import Move
from room_manager import BattleConfig, SeatConfig, SeatController
from rule_player import RuleBasedPlayer
from session import AVAILABLE_TIERS, make_players, make_players_from_config
from state import GameState


def test_tier_llm_makes_six_llm_seats_with_the_default_model():
    players = make_players("llm")

    assert len(players) == 6
    assert all(isinstance(p, LLMPlayer) for p in players)
    assert [p.id for p in players] == list(range(6))
    assert {p.config.name for p in players} == {"qwen3.5-9b"}


def test_tier_llm_with_a_model_name_uses_that_model():
    players = make_players("llm:gemma4-e4b")

    assert {p.config.name for p in players} == {"gemma4-e4b"}


def test_battle_config_mixes_llm_and_engine_seats():
    seats = [SeatConfig(tier="rule") for _ in range(6)]
    seats[2] = SeatConfig(tier="llm", model="gemma4-e4b")
    seats[4] = SeatConfig(tier="llm")
    players = make_players_from_config(BattleConfig(seats=seats))

    assert isinstance(players[0], RuleBasedPlayer)
    assert isinstance(players[2], LLMPlayer) and players[2].config.name == "gemma4-e4b"
    assert isinstance(players[4], LLMPlayer) and players[4].config.name == "qwen3.5-9b"


def test_llm_tier_is_offered_and_flagged_as_needing_a_model():
    llm = next(t for t in AVAILABLE_TIERS if t["value"] == "llm")

    assert llm.get("has_model") is True
    assert llm["has_personality"] is False


def test_api_tiers_lists_configured_models():
    import web_server

    data = web_server.get_tiers()

    assert any(t["value"] == "llm" for t in data["tiers"])
    assert {m["value"] for m in data["llm_models"]} >= {"qwen3.5-9b", "gemma4-e4b"}
    assert data["llm_default"] == "qwen3.5-9b"


class _Stub(Player):
    def choose_action(self, state, legal_moves):
        return legal_moves[0]


class _SlowStub(_Stub):
    has_own_latency = True


def _sleep_calls(monkeypatch, ai: Player) -> list:
    calls: list = []
    monkeypatch.setattr(room_manager.time, "sleep", lambda s: calls.append(s))
    SeatController(0, ai).choose_action(GameState(), [Move.pass_move()])
    return calls


def test_engine_seats_still_pause_before_playing(monkeypatch):
    assert len(_sleep_calls(monkeypatch, _Stub(0))) == 1


def test_seats_with_their_own_latency_do_not_pause(monkeypatch):
    assert _sleep_calls(monkeypatch, _SlowStub(0)) == []


def test_home_menu_pages_are_served():
    """The home page links to /training and /replay; the per-seat AI and
    model selection lives on /training."""
    import web_server

    paths = {getattr(r, "path", None) for r in web_server.app.routes}
    assert {"/play", "/training", "/replay"} <= paths
