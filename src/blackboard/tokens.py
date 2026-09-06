"""Token estimation.

ONE estimator, used for both budget enforcement and reported metrics. Two would
let the server truncate on one scale and the benchmark report on another, which
silently invalidates every savings number.

Two backends:

  exact      -- a real BPE tokenizer (tiktoken, cl100k_base) when importable.
                Install with the `bench` extra. REQUIRED for benchmark runs.
  heuristic  -- stdlib-only fallback, so the core has no runtime dependency (R4).

The heuristic approximates BPE pretokenization (a leading space merges into its
token) and was fitted against cl100k_base on a mixed corpus of dense JSON, TSV,
prose, URIs and source code.

    MEASURED error vs cl100k_base: max +26.2%, mean 11.6%, biased HIGH.

Biased high is the safe direction for budgets: a read under-fills rather than
overflowing the caller's context. It is NOT accurate enough to publish token
savings from -- `bench/` refuses to run without the exact backend.
"""
from __future__ import annotations

import json
import re

# GPT-style pretokenization: a leading space belongs to the following token.
_PRE = re.compile(r" ?[A-Za-z]+| ?[0-9]+| ?[^\sA-Za-z0-9]+|\s+")

# Fitted constants. See docstring for the measured bound.
_ALPHA, _PUNCT, _DIGIT, _SPACE, _MIN = 5.5, 3.2, 3.6, 6.0, 0.85

HEURISTIC_MAX_ERROR = 0.262

_encoder = None
_backend = None


def _load_backend():
    global _encoder, _backend
    if _backend is not None:
        return
    try:
        import tiktoken
        _encoder = tiktoken.get_encoding("cl100k_base")
        _backend = "exact"
    except Exception:                      # noqa: BLE001 - any failure means fallback
        _encoder, _backend = None, "heuristic"


def backend() -> str:
    _load_backend()
    return _backend


def is_exact() -> bool:
    return backend() == "exact"


def _heuristic(text: str) -> int:
    n = 0.0
    for m in _PRE.finditer(text):
        piece = m.group(0)
        core = piece[1:] if piece[:1] == " " else piece
        if not core:
            n += max(_MIN, len(piece) / _SPACE)
            continue
        length, c = len(core), core[0]
        if c.isalpha():
            n += max(_MIN, length / _ALPHA)
        elif c.isdigit():
            n += max(_MIN, length / _DIGIT)
        elif c.isspace():
            n += max(_MIN, len(piece) / _SPACE)
        else:
            n += max(_MIN, length / _PUNCT)
    return max(1, int(round(n)))


def est_tokens(text: str) -> int:
    """Estimated tokens. Deterministic; never 0 for non-empty input."""
    if not text:
        return 0
    _load_backend()
    if _encoder is not None:
        return len(_encoder.encode(text, disallowed_special=()))
    return _heuristic(text)


def est_tokens_obj(obj) -> int:
    return est_tokens(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))


def require_exact(context: str = "this operation") -> None:
    """Benchmarks must not report savings computed from the heuristic."""
    if not is_exact():
        raise RuntimeError(
            f"{context} requires the exact tokenizer; the heuristic is +/-26% and would "
            f"invalidate the numbers. Install it:  uv pip install 'blackboard-mcp[bench]'")
