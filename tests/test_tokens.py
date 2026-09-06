"""The estimator drives BOTH budgets and metrics, so its error is a tested property."""
import json
import pytest
from blackboard import tokens
from blackboard.render import to_tsv

tiktoken = pytest.importorskip("tiktoken")
ENC = tiktoken.get_encoding("cl100k_base")


def _corpus():
    rows = [{"handler": f"/api/v{i}/resource", "method": "GET", "auth": "jwt",
             "file": f"src/api/mod{i}.go", "line": 100 + i} for i in range(40)]
    return {
        "records_json": json.dumps(rows, separators=(",", ":")),
        "records_tsv": to_tsv(rows),
        "prose": "A brake assembly specification covering pad wear tolerances and "
                 "the torque sequence for caliper bolts on the 2024 platform.",
        "uris": "\n".join(f"bb://ws/domain.automotive/fact/item-{i}@{i%5}" for i in range(60)),
        "nested": json.dumps({"a": {"b": {"c": [{"d": i, "e": "x" * 20} for i in range(30)]}}},
                             separators=(",", ":")),
        "code": open("src/blackboard/api.py").read()[:6000],
    }


def test_exact_backend_is_used_when_available():
    assert tokens.is_exact(), "tiktoken is installed, so est_tokens must be exact"
    assert tokens.est_tokens("hello world") == len(ENC.encode("hello world"))


def test_heuristic_stays_within_its_documented_bound():
    worst = 0.0
    for name, text in _corpus().items():
        true = len(ENC.encode(text))
        est = tokens._heuristic(text)
        err = (est - true) / true
        worst = max(worst, abs(err))
        print(f"{name:<14} est={est:<6} true={true:<6} err={err:+.1%}")
    assert worst <= tokens.HEURISTIC_MAX_ERROR + 0.02, (
        f"heuristic drifted to {worst:.1%}; update the fitted constants or the "
        f"documented bound in tokens.py -- do not silently widen this assertion")


def test_heuristic_is_biased_high_so_budgets_underfill():
    """Over-estimating truncates early; under-estimating overflows a context window."""
    unders = [n for n, t in _corpus().items()
              if tokens._heuristic(t) < len(ENC.encode(t)) * 0.95]
    assert not unders, f"heuristic under-counts {unders}; budgets could overflow"


def test_require_exact_guards_the_benchmark(monkeypatch):
    monkeypatch.setattr(tokens, "_backend", "heuristic")
    monkeypatch.setattr(tokens, "_encoder", None)
    with pytest.raises(RuntimeError, match="exact tokenizer"):
        tokens.require_exact("benchmark")
