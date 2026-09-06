"""Concurrency is the part that must be right. Tests written before the fixes.

Delta1: CAS replaces locks, so the invariant is "no silent lost update" under
real cross-connection contention, not "an agent remembered to unlock".
"""
import threading
import pytest
from blackboard.api import Blackboard
from blackboard.artifacts import LocalArtifacts
from blackboard.auth import issue
from blackboard.errors import VersionConflict
from blackboard.store.sqlite import SQLiteStore

U = "bb://testws/domain.automotive/fact/contended"


def _fresh(tmp_path, n_agents):
    store = SQLiteStore(str(tmp_path / "bb.db"))
    arts = LocalArtifacts(str(tmp_path / "artifacts"))
    api = Blackboard(store, arts, "testws")
    grants = [issue(store, "testws", "planner", ["**"], agent_id=f"a{i}")[1]
              for i in range(n_agents)]
    return api, store, grants


def test_concurrent_cas_yields_exactly_one_winner(tmp_path):
    api, store, grants = _fresh(tmp_path, 8)
    api.update_state(grants[0], U, body={"v": 0}, digest="seed")
    assert store.get(U).version == 1

    results, errors = [], []
    barrier = threading.Barrier(8)

    def writer(g, i):
        barrier.wait()
        try:
            results.append(api.update_state(g, U, body={"v": i}, digest=f"w{i}",
                                            expect_version=1))
        except VersionConflict as e:
            errors.append(e)

    ts = [threading.Thread(target=writer, args=(g, i)) for i, g in enumerate(grants)]
    [t.start() for t in ts]
    [t.join() for t in ts]

    assert len(results) == 1, f"{len(results)} writers won a CAS race; lost updates are possible"
    assert len(errors) == 7
    assert all(e.detail["current_version"] == 2 for e in errors), \
        "a 409 must carry the CURRENT version so the loser can re-read and merge"
    assert store.get(U).version == 2


def test_unconditional_writes_never_lose_a_version(tmp_path):
    """No expect_version: last-writer-wins is allowed, but every write must be recorded."""
    api, store, grants = _fresh(tmp_path, 6)
    api.update_state(grants[0], U, body={"v": 0}, digest="seed")
    barrier = threading.Barrier(6)

    def writer(g, i):
        barrier.wait()
        for k in range(5):
            api.update_state(g, U, body={"agent": i, "k": k}, digest=f"a{i}k{k}")

    ts = [threading.Thread(target=writer, args=(g, i)) for i, g in enumerate(grants)]
    [t.start() for t in ts]
    [t.join() for t in ts]

    e = store.get(U)
    assert e.version == 31, f"expected 1 seed + 30 writes, got version {e.version}"
    assert len(store.history(U)) == 30, "every superseded version must be in append-only history"


def test_readers_are_not_blocked_by_writers(tmp_path):
    """WAL: many readers concurrent with one writer, no torn reads."""
    api, store, grants = _fresh(tmp_path, 2)
    api.update_state(grants[0], U, body={"v": 0}, digest="seed")
    stop = threading.Event()
    per_reader, failures = {}, []

    def reader(rid):
        mine = per_reader[rid] = []
        while not stop.is_set():
            try:
                item = api.get_state(grants[1], [U], mode="full")["items"][0]
                # A read must be internally consistent: the version and the body
                # it returns come from the same committed state, never a mix.
                mine.append((item["version"], item["content"]))
            except Exception as ex:            # noqa: BLE001
                failures.append(ex)

    rs = [threading.Thread(target=reader, args=(i,)) for i in range(6)]
    [r.start() for r in rs]
    for i in range(60):
        api.update_state(grants[0], U, body={"v": i, "pad": "x" * 500}, digest=f"v{i}")
    stop.set()
    [r.join(timeout=5) for r in rs]

    assert not failures, f"readers failed during writes: {failures[:3]}"
    total = sum(len(v) for v in per_reader.values())
    assert total > 0, "readers were starved entirely"
    for rid, obs in per_reader.items():
        # Monotonic PER READER. A global ordering across threads is meaningless.
        versions = [v for v, _ in obs]
        assert versions == sorted(versions), f"reader {rid} saw versions go backwards"
        for v, content in obs:
            if v >= 2:                       # v1 is the seed, which has no "v" field
                assert f'"v":{v - 2}' in content, "torn read: version and body disagree"


def test_cas_against_missing_entry_is_a_conflict(tmp_path):
    api, _store, grants = _fresh(tmp_path, 1)
    with pytest.raises(VersionConflict) as ei:
        api.update_state(grants[0], U, body={"v": 1}, digest="d", expect_version=3)
    assert ei.value.detail["current_version"] is None


def test_concurrent_identical_artifact_writes_converge(tmp_path):
    """Content addressing must survive two agents writing the same blob at once."""
    api, _store, grants = _fresh(tmp_path, 6)
    big = {"blob": "q" * 20000}
    out, barrier = [], threading.Barrier(6)

    def w(g, i):
        barrier.wait()
        out.append(api.update_state(
            g, f"bb://testws/domain.automotive/fact/blob{i}", body=big, digest="d"))

    ts = [threading.Thread(target=w, args=(g, i)) for i, g in enumerate(grants)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len({o["artifact_uri"] for o in out}) == 1, "identical content must dedup to one artifact"
    body = api.get_state(grants[0], ["bb://testws/domain.automotive/fact/blob0"],
                         mode="full", budget_tokens=8000)["items"][0]
    assert "q" * 100 in body["content"]
