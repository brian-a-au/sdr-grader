"""Regenerate examples/templated-report.html from the canonical demo fixture.

Usage:
    uv run python scripts/generate_examples.py

The output is the renderer's golden file — `tests/test_renderer.py` asserts
byte-equivalence against it. Re-run after any deliberate change to the template,
CSS, demo fixture, or renderer logic, and review the diff before committing.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tests"))

from fixtures.demo_report import build_demo_report  # noqa: E402
from sdr_grader.render import render  # noqa: E402


def main() -> int:
    out = render(build_demo_report())
    output_path = REPO_ROOT / "examples" / "templated-report.html"
    output_path.write_text(out, encoding="utf-8")
    print(f"Wrote {output_path.relative_to(REPO_ROOT)} ({len(out):,} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
