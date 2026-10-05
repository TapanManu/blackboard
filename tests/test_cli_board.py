import io
import json
import subprocess

import pytest
from blackboard import config, hooks
from blackboard.cli import main
from blackboard.hooks import compact_uri


@pytest.fixture(autouse=True)
def home(monkeypatch, tmp_path):
    monkeypatch.setenv(config.ROOT_ENV, str(tmp_path / "home"))


def _json_lines(capsys):
    return [json.loads(line) for line in capsys.readouterr().out.splitlines() if line]


def _body(item):
    inner = item["content"].split("\n", 1)[1].rsplit("\n", 1)[0]
    return json.loads(inner)


def _run_hook(monkeypatch, event, payload):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    return main(["-w", "ws", "hook", event])


def test_put_then_get_returns_the_digest(capsys):
    assert main(["-w", "ws", "put", "bb://ws/run/decision/d1",
                 "--body", '{"why": "derived"}', "--digest", "skip generated files"]) == 0
    capsys.readouterr()
    assert main(["-w", "ws", "get", "bb://ws/run/decision/d1"]) == 0
    assert "skip generated files" in capsys.readouterr().out


def test_put_reads_the_body_from_stdin(capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO('{"rows": [1, 2]}'))
    assert main(["-w", "ws", "put", "bb://ws/run/fact/f1",
                 "--body-file", "-", "--digest", "two rows"]) == 0
    capsys.readouterr()
    main(["-w", "ws", "get", "bb://ws/run/fact/f1", "--mode", "full"])
    [out] = _json_lines(capsys)
    assert _body(out["items"][0]) == {"rows": [1, 2]}


def test_cli_writes_do_not_accumulate_grants(capsys):
    for i in range(3):
        main(["-w", "ws", "put", f"bb://ws/run/fact/f{i}", "--digest", "d"])
    capsys.readouterr()
    _api, store = config.open_workspace("ws")
    assert store.list_grants("ws") == []


@pytest.mark.parametrize("query", ["sedai-core", "SED-123?", "bb://ws/run"])
def test_search_finds_punctuated_terms(capsys, query):
    main(["-w", "ws", "put", "bb://ws/run/fact/f1",
          "--digest", "sedai-core SED-123? fix lives at bb://ws/run"])
    capsys.readouterr()
    assert main(["-w", "ws", "search", query]) == 0
    [out] = _json_lines(capsys)
    assert [i["uri"] for i in out["items"]] == ["bb://ws/run/fact/f1"]


def test_search_with_only_whitespace_returns_nothing(capsys):
    main(["-w", "ws", "put", "bb://ws/run/fact/f1", "--digest", "anything"])
    capsys.readouterr()
    main(["-w", "ws", "search", "   "])
    [out] = _json_lines(capsys)
    assert out["items"] == []


def test_resume_prints_one_result_per_recipe_step(capsys):
    main(["-w", "ws", "put", "bb://ws/run/state/current",
          "--body", '{"goal": "audit handlers"}', "--digest", "goal: audit handlers"])
    main(["-w", "ws", "put", "bb://ws/run/decision/d1", "--digest", "Decision: skip generated"])
    capsys.readouterr()
    assert main(["-w", "ws", "resume"]) == 0
    out = capsys.readouterr().out
    assert len(out.splitlines()) == 3
    assert "audit handlers" in out and "Decision: skip generated" in out


def test_pre_then_post_compact_keeps_git_state_and_summary(capsys, monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "feature-x"], cwd=repo, check=True)
    (repo / "a.txt").write_text("x")

    assert _run_hook(monkeypatch, "pre-compact",
                     {"session_id": "s1", "cwd": str(repo), "trigger": "auto"}) == 0
    assert _run_hook(monkeypatch, "post-compact",
                     {"session_id": "s1", "compact_summary": "Fixing the search bug."}) == 0
    assert capsys.readouterr().out == ""

    main(["-w", "ws", "get", compact_uri("ws", "s1"), "--mode", "full"])
    [out] = _json_lines(capsys)
    item = out["items"][0]
    body = _body(item)
    assert item["digest"] == "Fixing the search bug."
    assert body["git"]["branch"] == "feature-x"
    assert body["git"]["uncommitted"] == ["?? a.txt"]
    assert body["compact_summaries"] == ["Fixing the search bug."]


def test_post_compact_without_a_checkpoint_still_records_the_summary(capsys, monkeypatch):
    _run_hook(monkeypatch, "post-compact", {"session_id": "s2", "compact_summary": "Summary."})
    main(["-w", "ws", "get", compact_uri("ws", "s2")])
    assert "Summary." in capsys.readouterr().out


def test_hook_never_fails_the_compaction(capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    assert main(["-w", "ws", "hook", "pre-compact"]) == 0
    def broken(*_args):
        raise RuntimeError("disk full")
    monkeypatch.setitem(hooks.HANDLERS, "pre-compact", broken)
    assert _run_hook(monkeypatch, "pre-compact", {"session_id": "s3"}) == 0
    assert "disk full" in capsys.readouterr().err
