"""The star test (Q10): a fresh session reaches operational standing cheaply.

It drives exactly the recipe the L1 skill prompt documents -- no privileged
shortcut, no helper the agent doesn't have.
"""
import json
import pytest

from blackboard.api import Blackboard
from blackboard.artifacts import LocalArtifacts
from blackboard.auth import issue
from blackboard.conventions import RESUME_TOKEN_TARGET, state_uri
from blackboard.store.sqlite import SQLiteStore
from blackboard.tokens import est_tokens

WS = "resumews"


def _mid_run_board(tmp_path):
    """A run 60% through: 40 tasks, 24 done, 12 decisions, a big artifact."""
    store = SQLiteStore(str(tmp_path / "bb.db"))
    api = Blackboard(store, LocalArtifacts(str(tmp_path / "artifacts")), WS)
    _t, planner = issue(store, WS, "planner", ["**"], agent_id="planner-1")
    _t, worker = issue(store, WS, "worker", ["**"], agent_id="worker-7")

    api.update_state(planner, state_uri(WS), digest=(
        "Audit 40 modules for unauthenticated HTTP handlers. Phase: execute (24/40 done). "
        "Invariant: every finding cites file:line. Open: module 31 has a generated file."),
        body={
            "goal": "Audit 40 modules for unauthenticated HTTP handlers and report findings",
            "constraints": ["every finding must cite file:line",
                            "do not modify source", "auth values: none|jwt|session|mtls"],
            "phase": "execute",
            "progress": {"tasks_total": 40, "done": 24},
            "open_questions": ["module 31 imports a generated file that was unavailable"],
            "success_criteria": ["all 40 modules reported", "zero unsourced findings"],
        })

    for i in range(40):
        api.update_state(planner, f"bb://{WS}/tasks.audit/task_spec/t{i:02d}",
                         digest=f"audit module {i} for unauthenticated handlers",
                         body={"objective": f"list handlers + auth in module {i}",
                               "inputs": [f"bb://{WS}/domain.code/artifact_ref/mod{i:02d}"],
                               "acceptance": ["file:line for every handler"],
                               "budget_tokens": 12000})
    for i in range(24):
        api.update_state(worker, f"bb://{WS}/tasks.audit/result/t{i:02d}",
                         digest=f"module {i}: 6 handlers, 4 jwt, 1 session, 1 NONE (admin)",
                         body={"handlers": [{"path": f"/api/m{i}/x{j}", "auth": "jwt",
                                             "file": f"src/m{i}.go", "line": 40 + j}
                                            for j in range(6)]},
                         sources=[{"claim": "handler list", "source": f"src/m{i}.go"}])
    for i in range(12):
        api.update_state(planner, f"bb://{WS}/run/decision/d{i:02d}",
                         digest=f"Decision {i}: treat generated files as out of scope "
                                f"because they are rebuilt from audited sources.",
                         body={"decision": f"d{i}", "rationale": "generated code is derived",
                               "alternatives_rejected": ["audit generated output too"]})
    # a big artifact: the kind of thing that used to sit in a context window
    api.update_state(worker, f"bb://{WS}/domain.code/artifact_ref/mod00",
                     digest="module 0 source dump, 40 KB",
                     body={"src": "x" * 40000})
    return store, api


def test_fresh_agent_resumes_within_the_token_target(tmp_path, capsys):
    store, api = _mid_run_board(tmp_path)

    # ---- a NEW session: new grant, no memory of anything above -----------
    _t, joiner = issue(store, WS, "planner", ["**"], agent_id="joiner-1")
    spent = 0
    transcript = []

    r1 = api.get_state(joiner, [state_uri(WS)], mode="full", budget_tokens=800)
    r2 = api.list_keys(joiner, topic="tasks.**", mode="table", limit=40)
    r3 = api.list_keys(joiner, kind="decision", order="recency", limit=10,
                       mode="digest", budget_tokens=900)
    for r in (r1, r2, r3):
        blob = json.dumps(r, separators=(",", ":"))
        spent += est_tokens(blob)
        transcript.append(blob)

    joined = "\n".join(transcript)
    print(f"\nresume cost: {spent} tokens (target <{RESUME_TOKEN_TARGET})")

    assert spent < RESUME_TOKEN_TARGET, (
        f"resume cost {spent} tokens exceeds the {RESUME_TOKEN_TARGET} target")

    # ---- and it actually knows what it needs to know ---------------------
    assert "unauthenticated HTTP handlers" in joined, "goal not recovered"
    assert "file:line" in joined, "constraints not recovered"
    assert "module 31" in joined, "open questions not recovered"
    assert joined.count("t0") > 5, "task frontier not recovered"
    assert joined.count("Decision") >= 10, "decisions and their rationale not recovered"

    # ---- and the 40 KB artifact did NOT come along -----------------------
    assert "x" * 200 not in joined, "a large body leaked into the resume path"
    store.close()


def test_resume_is_flat_in_the_work_that_preceded_it(tmp_path):
    """The point of Q5: cost per step does not grow with history."""
    store, api = _mid_run_board(tmp_path)
    _t, g = issue(store, WS, "planner", ["**"], agent_id="j2")

    def resume_cost():
        rs = [api.get_state(g, [state_uri(WS)], mode="full", budget_tokens=800),
              api.list_keys(g, topic="tasks.**", mode="table", limit=40),
              api.list_keys(g, kind="decision", order="recency", limit=10,
                            mode="digest", budget_tokens=900)]
        return sum(est_tokens(json.dumps(r, separators=(",", ":"))) for r in rs)

    before = resume_cost()
    # simulate a great deal more work happening
    for i in range(120):
        api.update_state(g, f"bb://{WS}/tasks.audit/result/extra{i:03d}",
                         digest=f"extra result {i} with a reasonably long digest line",
                         body={"rows": [{"i": j, "pad": "p" * 200} for j in range(50)]})
    after = resume_cost()

    print(f"\nresume before={before} after 120 more entries={after}")
    assert after < RESUME_TOKEN_TARGET, "resume cost grew past target as the board grew"
    assert after <= before * 1.35, (
        f"resume cost grew {after/before:.2f}x with history; it must be roughly flat")
    store.close()


def test_savings_grow_as_the_board_holds_more_content(tmp_path):
    """What is actually invariant.

    A ratio of resume-cost to full-board-cost is a property of the FIXTURE, not
    the system: a board of tiny entries has little to save. The real claim is
    that resume cost stays flat while a full read grows without bound -- so the
    saving is a function of how much work the board holds.
    """
    store, api = _mid_run_board(tmp_path)
    _t, g = issue(store, WS, "planner", ["**"], agent_id="j3")

    def costs():
        rows = store.query(WS, "**", None, None, "created", 100000)
        full = sum(e.est_tokens for e in rows)
        rs = [api.get_state(g, [state_uri(WS)], mode="full", budget_tokens=800),
              api.list_keys(g, topic="tasks.**", mode="table", limit=40),
              api.list_keys(g, kind="decision", order="recency", limit=10,
                            mode="digest", budget_tokens=900)]
        resume = sum(est_tokens(json.dumps(r, separators=(",", ":"))) for r in rs)
        return full, resume

    trace = [costs()]
    for batch in range(4):
        for i in range(15):
            api.update_state(g, f"bb://{WS}/tasks.audit/result/bulk{batch}{i:02d}",
                             digest=f"bulk result {batch}-{i}: 200 rows of handler data",
                             body={"rows": [{"i": j, "path": f"/api/x{j}",
                                             "note": "n" * 120} for j in range(200)]})
        trace.append(costs())

    print("\n  full_board  resume  resume/full")
    for full, resume in trace:
        print(f"  {full:>10}  {resume:>6}  {resume/full:>10.1%}")

    ratios = [r / f for f, r in trace]
    assert all(b < a for a, b in zip(ratios, ratios[1:])), \
        "resume/full must fall monotonically as the board accumulates content"
    assert ratios[-1] < ratios[0] / 5, \
        f"savings barely improved: {ratios[0]:.1%} -> {ratios[-1]:.1%}"

    resumes = [r for _f, r in trace]
    assert max(resumes) < RESUME_TOKEN_TARGET, "resume cost breached the target"
    assert max(resumes) <= min(resumes) * 1.35, \
        f"resume cost is not flat: {min(resumes)} -> {max(resumes)}"
    store.close()
