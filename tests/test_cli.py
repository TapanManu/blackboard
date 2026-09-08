import json
import pytest
from blackboard import config
from blackboard.cli import main


@pytest.fixture(autouse=True)
def home(monkeypatch, tmp_path):
    monkeypatch.setenv(config.ROOT_ENV, str(tmp_path / "home"))


def test_init_grant_status_export_roundtrip(capsys, tmp_path):
    assert main(["-w", "acme", "init"]) == 0
    assert "acme" in capsys.readouterr().out

    assert main(["-w", "acme", "grant", "--role", "worker",
                 "--topics", "tasks.car/**", "--quiet"]) == 0
    token = capsys.readouterr().out.strip()
    assert token.startswith("bbt_")

    # write something through the API using that token
    from blackboard.auth import resolve
    api, store = config.open_workspace("acme")
    g = resolve(store, token)
    api.update_state(g, "bb://acme/tasks.car/result/t1", body={"ok": True}, digest="t1 done")

    assert main(["-w", "acme", "status"]) == 0
    out = capsys.readouterr().out
    assert "entries        1" in out and "board_health" in out

    out_file = tmp_path / "run.jsonl"
    assert main(["-w", "acme", "export", "--out", str(out_file)]) == 0
    capsys.readouterr()
    rec = json.loads(out_file.read_text().splitlines()[0])
    assert rec["uri"] == "bb://acme/tasks.car/result/t1" and rec["body"] == {"ok": True}

    assert main(["-w", "acme2", "import", str(out_file)]) == 0
    capsys.readouterr()
    api2, _ = config.open_workspace("acme2")
    assert api2.health()["entries"] == 1


def test_destroy_requires_confirmation(capsys):
    main(["-w", "gone", "init"]); capsys.readouterr()
    assert main(["-w", "gone", "destroy"]) == 1
    assert "--yes" in capsys.readouterr().out
    assert main(["-w", "gone", "destroy", "--yes"]) == 0
    capsys.readouterr()
    assert not config.db_path("gone").exists()


def test_revoke_kills_a_token(capsys):
    main(["-w", "rev", "init"]); capsys.readouterr()
    main(["-w", "rev", "grant", "--role", "worker", "--quiet"])
    token = capsys.readouterr().out.strip()
    from blackboard.auth import resolve, token_hash
    from blackboard.errors import Forbidden
    _api, store = config.open_workspace("rev")
    assert resolve(store, token)
    assert main(["-w", "rev", "revoke", token_hash(token)]) == 0
    capsys.readouterr()
    _api2, store2 = config.open_workspace("rev")
    with pytest.raises(Forbidden):
        resolve(store2, token)


def test_vacuum_reports_unreferenced_artifacts(capsys):
    main(["-w", "vac", "init"]); capsys.readouterr()
    api, store = config.open_workspace("vac")
    from blackboard.auth import issue
    _t, g = issue(store, "vac", "planner", ["**"], agent_id="p")
    api.update_state(g, "bb://vac/t/fact/a", body={"b": "z" * 20000}, digest="d")
    api.update_state(g, "bb://vac/t/fact/a", body={"b": "y" * 20000}, digest="d")
    store.close()
    assert main(["-w", "vac", "vacuum"]) == 0
    out = capsys.readouterr().out
    assert "1 referenced" in out and "1 unreferenced" in out


def test_events_log_is_readable(capsys):
    main(["-w", "ev", "init"]); capsys.readouterr()
    api, store = config.open_workspace("ev")
    from blackboard.auth import issue
    _t, g = issue(store, "ev", "planner", ["**"], agent_id="p")
    api.update_state(g, "bb://ev/t/fact/a", body={"v": 1}, digest="d")
    api.update_state(g, "bb://ev/t/fact/b", body={"v": 2}, digest="d")
    api.link_state(g, "bb://ev/t/fact/a", "cites", ["bb://ev/t/fact/b"])
    store.close()
    assert main(["-w", "ev", "events"]) == 0
    out = capsys.readouterr().out
    assert out.count("put") == 2 and "link" in out and "cursor 3" in out


def test_events_respect_topic_scope():
    api, store = config.open_workspace("evs")
    from blackboard.auth import issue
    _t, p = issue(store, "evs", "planner", ["**"], agent_id="p")
    _t, w = issue(store, "evs", "worker", ["tasks.car/**"], agent_id="w")
    api.update_state(p, "bb://evs/tasks.car/result/a", body={}, digest="d")
    api.update_state(p, "bb://evs/domain.armaments/fact/b", body={}, digest="d")
    seen = [e["uri"] for e in api.events(w)["events"]]
    assert seen == ["bb://evs/tasks.car/result/a"]


def test_ephemeral_persists_nothing(capsys):
    assert main(["-w", "ghost", "--ephemeral", "status"]) == 0
    capsys.readouterr()
    assert not config.db_path("ghost").exists()


def test_vacuum_keeps_artifacts_another_workspace_references(capsys):
    """Artifacts are shared across workspaces; each workspace is its own database."""
    from blackboard.auth import issue
    main(["-w", "vac_a", "init"]); main(["-w", "vac_b", "init"]); capsys.readouterr()

    api_b, store_b = config.open_workspace("vac_b")
    _t, gb = issue(store_b, "vac_b", "planner", ["**"], agent_id="p")
    api_b.update_state(gb, "bb://vac_b/t/fact/big", body={"b": "z" * 20000}, digest="d")
    store_b.close()

    # vac_a references nothing; the blob it must not touch belongs to vac_b.
    assert main(["-w", "vac_a", "vacuum", "--yes"]) == 0
    assert "1 referenced, 0 unreferenced" in capsys.readouterr().out

    api_b, store_b = config.open_workspace("vac_b")
    _t, gb = issue(store_b, "vac_b", "planner", ["**"], agent_id="p2")
    got = api_b.get_state(gb, ["bb://vac_b/t/fact/big"], mode="full",
                          budget_tokens=8000)["items"][0]
    assert "z" * 100 in got["content"]
    store_b.close()
