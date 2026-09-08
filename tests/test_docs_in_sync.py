"""The practices exist in two places on purpose; this stops them from drifting.

`skills/blackboard/SKILL.md` is loaded by an agent every session and says what to
do. `docs/11-using-it-well.md` is read by a person and says why each rule pays.
Both quote the same measured figures, and a figure corrected in one file and not
the other is worse than no figure at all -- it makes two documents disagree while
both look authoritative.
"""
from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "blackboard" / "SKILL.md"
DOC = ROOT / "docs" / "11-using-it-well.md"

# figure -> every file that states it. Add a row when a new number is published.
SHARED_FIGURES = {
    "34%": (SKILL, DOC),                                    # rows vs objects, on write
    "44.6%": (DOC, ROOT / "MEASURED.md", ROOT / "README.md"),   # TSV vs JSON, on read
    "2,679": (ROOT / "MEASURED.md", ROOT / "README.md"),    # flat resume cost
}

# Every practice in the doc must be actionable from the skill alone, because the
# agent never reads the doc. The token is the call or phrase that carries it.
PRACTICES = ["append", "digest_from", "columns", "select", "lines",
             "search_keys", "source_path", "budget_tokens"]


@pytest.mark.parametrize("figure,files", sorted(SHARED_FIGURES.items()))
def test_published_figures_agree_everywhere_they_appear(figure, files):
    missing = [str(f.relative_to(ROOT)) for f in files if figure not in f.read_text()]
    assert not missing, (f"{figure} is quoted in {len(files)} files but missing from "
                         f"{missing}; correct it in every one or in none")


@pytest.mark.parametrize("token", PRACTICES)
def test_every_practice_is_reachable_from_the_skill(token):
    assert token in SKILL.read_text(), (
        f"{token!r} is a documented practice an agent cannot follow: it appears in "
        f"the doc but not in the skill, and the agent only ever loads the skill")


def test_the_two_documents_point_at_each_other():
    assert "11-using-it-well.md" in SKILL.read_text()
    assert "skills/blackboard/SKILL.md" in DOC.read_text()
