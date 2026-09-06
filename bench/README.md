# Benchmark harness — week 2, not yet built

Arms A/B/C/D and suites 1–4 are specified in `docs/06-benchmarks.md`; the kill
criteria they feed are in `docs/09-value.md`. Nothing here runs yet.

Requires the exact tokenizer: `tokens.require_exact()` refuses to report savings
computed from the heuristic (see `MEASURED.md`).
