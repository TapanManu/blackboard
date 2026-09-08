"""Topic isolation must be enforced by the daemon, never by the prompt (Delta10 / Q15)."""
import pytest
from blackboard.auth import issue, token_hash
from blackboard.errors import Forbidden

CAR = "bb://testws/domain.automotive/fact/brake-assy"
GUN = "bb://testws/domain.armaments/fact/barrel-lot"


def test_worker_cannot_read_across_topics(bb, planner, car_worker):
    api, _ = bb
    api.update_state(planner, CAR, body={"a": 1}, digest="car fact")
    api.update_state(planner, GUN, body={"a": 1}, digest="gun fact")

    assert api.get_state(car_worker, [CAR])["items"][0]["uri"] == CAR
    with pytest.raises(Forbidden) as ei:
        api.get_state(car_worker, [GUN])
    assert "topic outside grant" in str(ei.value)


def test_denial_does_not_leak_existence(bb, car_worker):
    """A denied read on a nonexistent key must look identical to a denied read on a real one."""
    api, _ = bb
    with pytest.raises(Forbidden):
        api.get_state(car_worker, ["bb://testws/domain.armaments/fact/does-not-exist"])


def test_worker_cannot_write_across_topics(bb, car_worker):
    api, _ = bb
    with pytest.raises(Forbidden):
        api.update_state(car_worker, GUN, body={"a": 1}, digest="d")


def test_list_keys_hard_filters_out_of_scope_rows(bb, planner, car_worker):
    api, _ = bb
    api.update_state(planner, CAR, body={"a": 1}, digest="car")
    api.update_state(planner, GUN, body={"a": 1}, digest="gun")
    uris = [i["uri"] for i in api.list_keys(car_worker, topic="**")["items"]]
    assert uris == [CAR], "out-of-scope entries must never be listed"


def test_search_hard_filters_out_of_scope_rows(bb, planner, car_worker):
    api, _ = bb
    api.update_state(planner, CAR, body={"a": 1}, digest="tungsten component")
    api.update_state(planner, GUN, body={"a": 1}, digest="tungsten component")
    hits = api.search_keys(car_worker, "tungsten")
    assert [h["uri"] for h in hits["items"]] == [CAR]


def test_capability_is_required_not_just_topic(bb):
    api, store = bb
    _t, reader = issue(store, "testws", "reader", ["**"], agent_id="ro")
    with pytest.raises(Forbidden):
        api.update_state(reader, CAR, body={"a": 1}, digest="d")


def test_expired_token_is_rejected(bb):
    from blackboard.auth import resolve
    _api, store = bb
    tok, _g = issue(store, "testws", "worker", ["**"], ttl_s=-1)
    with pytest.raises(Forbidden):
        resolve(store, tok)


def test_unknown_token_is_rejected(bb):
    from blackboard.auth import resolve
    _api, store = bb
    with pytest.raises(Forbidden):
        resolve(store, "bbt_not_a_real_token")


def test_wrong_workspace_is_rejected(bb, planner):
    api, _ = bb
    with pytest.raises(Forbidden):
        api.get_state(planner, ["bb://otherws/domain.automotive/fact/x"])


def test_server_resolves_the_grant_per_call_not_at_startup(tmp_path, monkeypatch):
    """A revoked or expired token must stop working on a server already running."""
    from blackboard.server import _grant_for
    from blackboard.store.sqlite import SQLiteStore

    store = SQLiteStore(str(tmp_path / "bb.db"))
    token, _g = issue(store, "ws", "planner", ["**"], agent_id="p")
    monkeypatch.setenv("BLACKBOARD_TOKEN", token)

    grant_of = _grant_for(store, "ws")       # startup
    assert grant_of().agent_id == "p"
    store.delete_grant(token_hash(token))
    with pytest.raises(Forbidden):
        grant_of()                            # next tool call, same process
    store.close()
