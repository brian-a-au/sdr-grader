"""Run validated counterexamples without changing the repository.
Run from the reviewed checkout: .venv/bin/python docs/audits/2026-09-07-reproductions/reproduce.py
Artifacts go to /tmp. Printed scores describe the audited implementation,
not regression expectations; see report.md for expected behavior.
"""

import runpy
from pathlib import Path

for name in (
    "adapters_repro.py",
    "scoring_repro.py",
    "rules_repro.py",
    "offset_trend_repro.py",
    "governance_dates_repro.py",
):
    print("\n### " + name, flush=True)
    runpy.run_path(str(Path(__file__).parent / name), run_name="__main__")
