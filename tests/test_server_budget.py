"""Delta8: the tool surface is a per-turn tax, so it is CI-budgeted."""
import json
from blackboard.server import TOOLS, dispatch
from blackboard.tokens import est_tokens

BUDGET = 600


def test_five_tools_only():
    names = [t["name"] for t in TOOLS]
    assert names == ["get_state", "update_state", "list_keys", "search_keys", "link_state"]
    assert len(TOOLS) == 5, "L0 is five tools; claim/complete/watch/contest are L2/L3"


def test_tool_schema_fits_the_token_budget():
    blob = json.dumps(TOOLS, separators=(",", ":"))
    n = est_tokens(blob)
    print(f"\ntool schema: {n} est tokens (budget {BUDGET})")
    assert n <= BUDGET, (
        f"tool surface is {n} tokens, over the {BUDGET} budget. This is re-sent on EVERY "
        f"turn of EVERY agent; shrink a description rather than raising the budget.")


def test_descriptions_are_one_line():
    for t in TOOLS:
        assert "\n" not in t["description"]
        assert len(t["description"]) <= 110, f"{t['name']} description is too long"


def test_no_lock_tools_exist():
    """Delta1: locks require a liveness guarantee LLM sessions do not have."""
    names = {t["name"] for t in TOOLS}
    for banned in ("acquire_lock", "release_lock", "claim_task", "watch_events", "contest_state"):
        assert banned not in names


def test_dispatch_covers_every_tool(bb, planner):
    api, _ = bb
    U = "bb://testws/domain.automotive/fact/x"
    assert dispatch(api, planner, "update_state",
                    {"uri": U, "body": {"a": 1}, "digest": "d"})["version"] == 1
    assert dispatch(api, planner, "get_state", {"uris": [U]})["items"][0]["uri"] == U
    assert "items" in dispatch(api, planner, "list_keys", {"topic": "**"})
    assert "items" in dispatch(api, planner, "search_keys", {"q": "d"})
    D = "bb://testws/domain.automotive/decision/y"
    dispatch(api, planner, "update_state", {"uri": D, "body": {}, "digest": "d"})
    assert dispatch(api, planner, "link_state",
                    {"src": D, "rel": "derived_from", "dst": [U]})["linked"] == 1


def test_errors_are_typed_and_serializable(bb, planner):
    api, _ = bb
    from blackboard.errors import BlackboardError
    try:
        dispatch(api, planner, "update_state", {"uri": "bb://testws/t/fact/x", "body": {}})
    except BlackboardError as ex:
        d = ex.to_dict()
        assert d["error"] == "DIGEST_REQUIRED" and json.dumps(d)
    else:
        raise AssertionError("missing digest must raise")
