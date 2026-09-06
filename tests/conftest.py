import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import pytest
from blackboard.api import Blackboard
from blackboard.artifacts import LocalArtifacts
from blackboard.auth import issue
from blackboard.store.sqlite import SQLiteStore

WS = "testws"


@pytest.fixture
def bb(tmp_path):
    store = SQLiteStore(str(tmp_path / "bb.db"))
    arts = LocalArtifacts(str(tmp_path / "artifacts"))
    yield Blackboard(store, arts, WS), store
    store.close()


@pytest.fixture
def planner(bb):
    _, store = bb
    _tok, g = issue(store, WS, "planner", ["**"], agent_id="planner-1")
    return g


@pytest.fixture
def car_worker(bb):
    _, store = bb
    _tok, g = issue(store, WS, "worker",
                    ["domain.automotive/**", "tasks.car/**"], agent_id="worker-car")
    return g
