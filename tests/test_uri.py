import pytest
from blackboard.errors import InvalidURI
from blackboard.uri import glob_match, parse, artifact_uri, parse_artifact


def test_roundtrip():
    u = parse("bb://ws/domain.automotive/fact/brake-assy")
    assert (u.workspace, u.topic, u.kind, u.id, u.version) == \
           ("ws", "domain.automotive", "fact", "brake-assy", None)
    assert str(u) == "bb://ws/domain.automotive/fact/brake-assy"
    assert u.path == "domain.automotive/fact/brake-assy"


def test_versioned():
    u = parse("bb://ws/t/fact/x@7")
    assert u.version == 7
    assert u.base() == "bb://ws/t/fact/x"
    assert str(u) == "bb://ws/t/fact/x@7"


@pytest.mark.parametrize("bad", [
    "ws/t/k/i", "bb://ws/t/k", "bb://ws/t/k/i/extra", "bb:/ws/t/k/i",
    "bb://ws/t/k/i@x", "bb://ws//k/i", "bb://ws/t/k/i j", "", "bb://../t/k/i",
])
def test_rejects_malformed(bad):
    with pytest.raises(InvalidURI):
        parse(bad)


def test_artifact_uri():
    h = "a" * 64
    assert parse_artifact(artifact_uri(h)) == h
    with pytest.raises(InvalidURI):
        parse_artifact("bb-artifact://sha256/short")


# --------------------------------------------------------------- topic globs
# Isolation is load-bearing (Delta10 / Q15). The negative cases are the point.

@pytest.mark.parametrize("pat,path,expected", [
    ("**",                       "domain.automotive/fact/x",  True),
    ("domain.automotive/**",     "domain.automotive/fact/x",  True),
    ("domain.automotive/**",     "domain.automotive",         True),
    ("domain.automotive/**",     "domain.armaments/fact/x",   False),
    ("domain.automotive/**",     "domain.automotive2/fact/x", False),
    ("domain.autom*/**",         "domain.automotive/fact/x",  True),
    ("domain.autom*/**",         "domain.armaments/fact/x",   False),
    ("*/fact/*",                 "domain.automotive/fact/x",  True),
    ("*/fact/*",                 "a/b/fact/x",                False),   # * must not cross /
    ("tasks.car/**",             "tasks.car/task_spec/t1",    True),
    ("tasks.car/**",             "tasks.carbine/task_spec/t", False),
    ("tasks.**",                 "tasks.car/task_spec/t1",    True),
    ("tasks.**",                 "tasksXcar/task_spec/t1",    False),
    ("domain.armaments/**",      "domain.automotive/fact/x",  False),
])
def test_glob(pat, path, expected):
    assert glob_match(pat, path) is expected
