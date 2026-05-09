"""Render the canonical grade examples from the messy and clean fixtures.

Per SPEC §8 Phase 1: examples/grade-clean.html + examples/grade-messy.html
showcase what users actually see when they run the full pipeline. The
demo_report fixture used by examples/templated-report.html is a separate
contract — it tests the renderer in isolation against fabricated content.

Re-run after deliberate rule, fixture, or rubric changes; review the diff
before committing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from sdr_grader.adapters.cja import adapt as adapt_cja  # noqa: E402
from sdr_grader.core.grader import grade  # noqa: E402
from sdr_grader.render import render  # noqa: E402
from sdr_grader.rules.rubric import load_rubric  # noqa: E402

STRICT_PACK = REPO_ROOT / "src" / "sdr_grader" / "rules" / "packs" / "strict"
FIXTURES = REPO_ROOT / "tests" / "fixtures"
EXAMPLES = REPO_ROOT / "examples"


def render_fixture(snapshot_path: Path, output_path: Path) -> None:
    snap = json.loads(snapshot_path.read_text(encoding="utf-8"))
    impl = adapt_cja(snap, source=str(snapshot_path.relative_to(REPO_ROOT)))
    rubric = load_rubric(STRICT_PACK)
    report = grade(impl, rubric)
    html = render(report)
    output_path.write_text(html, encoding="utf-8")
    print(
        f"Wrote {output_path.relative_to(REPO_ROOT)}: "
        f"grade {report.grade} ({report.overall_pct}%), "
        f"{len(report.findings)} findings"
    )


def main() -> int:
    EXAMPLES.mkdir(parents=True, exist_ok=True)
    render_fixture(FIXTURES / "cja_snapshot_clean.json", EXAMPLES / "grade-clean.html")
    render_fixture(FIXTURES / "cja_snapshot_messy.json", EXAMPLES / "grade-messy.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
