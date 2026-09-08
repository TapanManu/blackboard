"""One policy for tests that need an optional extra.

The core package installs with no dependencies at all (R4), so a local `pytest`
without the extras is a legitimate run and skipping is the honest outcome. CI is
where it must be an error: a suite that skips its transport tests and computes
its savings from the ±26% heuristic reports green for coverage it never ran.

`BLACKBOARD_REQUIRE_EXTRAS=1` -- set by the workflow -- turns every such skip
into a failure.
"""
from __future__ import annotations

import importlib
import os

import pytest


def _missing(what: str, why: str):
    if os.environ.get("BLACKBOARD_REQUIRE_EXTRAS"):
        pytest.fail(f"{what} is not installed and BLACKBOARD_REQUIRE_EXTRAS is set: {why}. "
                    f"Install it:  uv pip install -e '.[dev]'", pytrace=False)
    pytest.skip(f"{what} not installed ({why}); install the dev extra to run this",
                allow_module_level=True)


def require_module(name: str, why: str):
    """Import an optional dependency, or skip/fail per policy."""
    try:
        return importlib.import_module(name)
    except ImportError:
        _missing(name, why)


def require_exact_tokenizer():
    """Guard a test that reports a token saving as a number."""
    from blackboard.tokens import is_exact
    if not is_exact():
        _missing("tiktoken", "the heuristic is +/-26% and biased unevenly across text "
                             "shapes, so a saving computed from it is not a measurement")
