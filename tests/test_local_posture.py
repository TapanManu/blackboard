"""R8: strictly local. The board must never open a network connection."""
import os
import socket
import stat
import pytest
from pathlib import Path

from blackboard import config
from blackboard.api import Blackboard
from blackboard.artifacts import LocalArtifacts
from blackboard.auth import issue
from blackboard.store.sqlite import SQLiteStore


@pytest.fixture
def guarded(monkeypatch, tmp_path):
    """Any attempt to reach the network fails the test loudly."""
    calls = []

    def boom(*a, **k):
        calls.append(a)
        raise AssertionError(f"network access attempted: {a}")

    monkeypatch.setattr(socket.socket, "connect", boom)
    monkeypatch.setattr(socket.socket, "connect_ex", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.setenv(config.ROOT_ENV, str(tmp_path / "home"))
    return calls


def test_full_workflow_makes_no_network_calls(guarded, tmp_path):
    api, store = config.open_workspace("egresstest")
    _t, g = issue(store, "egresstest", "planner", ["**"], agent_id="p")
    U = "bb://egresstest/domain.automotive/fact/x"

    api.update_state(g, U, body={"a": 1}, digest="d")
    api.update_state(g, U, body={"blob": "z" * 20000}, digest="big", expect_version=1)
    api.get_state(g, [U], mode="full", budget_tokens=8000)
    api.list_keys(g, topic="**", mode="table")
    api.search_keys(g, "big")
    api.link_state(g, U, "cites", [U])
    api.health()
    api.export_jsonl(str(tmp_path / "out.jsonl"))
    store.close()
    assert guarded == []


def test_file_modes_are_private(guarded, tmp_path):
    api, store = config.open_workspace("modes")
    _t, g = issue(store, "modes", "planner", ["**"], agent_id="p")
    api.update_state(g, "bb://modes/t/fact/x", body={"blob": "z" * 20000}, digest="d")
    store.close()

    home = config.home()
    assert stat.S_IMODE(home.stat().st_mode) == 0o700
    assert stat.S_IMODE(config.artifacts_path().stat().st_mode) == 0o700
    assert stat.S_IMODE(config.db_path("modes").stat().st_mode) == 0o600
    for f in config.artifacts_path().rglob("*"):
        if f.is_file():
            assert stat.S_IMODE(f.stat().st_mode) == 0o600, f"{f} is not 0600"


def test_no_tmp_files_left_behind(guarded, tmp_path):
    api, store = config.open_workspace("tmpcheck")
    _t, g = issue(store, "tmpcheck", "planner", ["**"], agent_id="p")
    for i in range(5):
        api.update_state(g, f"bb://tmpcheck/t/fact/x{i}",
                         body={"blob": "z" * 20000}, digest="d")
    store.close()
    leftovers = [p for p in config.artifacts_path().rglob("*.tmp")]
    assert leftovers == [], f"temp files leaked: {leftovers}"
