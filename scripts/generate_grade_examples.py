"""Render the canonical grade examples from the messy and clean fixtures.

Produces one HTML per (platform, fixture) pair so the examples/ directory
shows deterministic grades of representative synthetic CJA and AA snapshots.
The demo_report fixture used by examples/templated-report.html is a
separate contract — it tests the renderer in isolation against
fabricated content.

Re-run after deliberate rule, fixture, or rubric changes; review the
diff before committing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from sdr_grader.adapters.aa import adapt as adapt_aa  # noqa: E402
from sdr_grader.adapters.cja import adapt as adapt_cja  # noqa: E402
from sdr_grader.core.grader import grade  # noqa: E402
from sdr_grader.render import Report, cap_component_items, render  # noqa: E402
from sdr_grader.rules.rubric import Rubric, load_rubric  # noqa: E402

STRICT_PACK = REPO_ROOT / "src" / "sdr_grader" / "rules" / "packs" / "strict"
FIXTURES = REPO_ROOT / "tests" / "fixtures"
EXAMPLES = REPO_ROOT / "examples"

ADAPTERS = {"cja": adapt_cja, "aa": adapt_aa}


def _normalize_generated_html(html: str) -> str:
    """Keep checked-in examples free of template-only trailing whitespace."""
    return "\n".join(line.rstrip() for line in html.splitlines()) + "\n"


def render_fixture(
    platform: str,
    snapshot_path: Path,
    output_path: Path,
    *,
    rubric: Rubric,
) -> Report:
    """Grade one fixture, write its HTML, and return the semantic report."""
    snap = json.loads(snapshot_path.read_text(encoding="utf-8"))
    impl = ADAPTERS[platform](snap, source=str(snapshot_path.relative_to(REPO_ROOT)))
    report = grade(impl, rubric)
    html = _normalize_generated_html(render(cap_component_items(report)))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return report


def generate_all(output_dir: Path) -> dict[tuple[str, str], Report]:
    """Generate all canonical fixture reports below ``output_dir``."""
    reports = {}
    rubric = load_rubric(STRICT_PACK)
    for platform in ("cja", "aa"):
        for kind in ("clean", "messy"):
            reports[(platform, kind)] = render_fixture(
                platform,
                FIXTURES / f"{platform}_snapshot_{kind}.json",
                output_dir / f"grade-{platform}-{kind}.html",
                rubric=rubric,
            )
    return reports


def main() -> int:
    reports = generate_all(EXAMPLES)
    for (platform, kind), report in reports.items():
        output_path = EXAMPLES / f"grade-{platform}-{kind}.html"
        print(
            f"Wrote {output_path.relative_to(REPO_ROOT)}: "
            f"grade {report.grade} ({report.overall_pct}%), "
            f"{len(report.findings)} findings"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
