# v1.3.0 correctness compatibility contract

`cases.json` contains 65 deterministic CLI cases. `expectations.json` records full
v1.2.9 and candidate structured outcomes and exact JSON-pointer before/after deltas.
The reviewed baseline is tag `v1.2.9`, peeled commit
`9687fcc66622d454cc121cd49daa319c0c01a939`. Only `tool_version` is normalized.
Do not regenerate expectations as part of verification: edits require review of
both the baseline outcome and the intended correction. Errors preserve the exact
contextual diagnostic, exit, and absence of HTML/JSON success reports.

There are 37 changed and 28 unchanged outcomes. Eight public clean/messy fixture
cases span AA/CJA and strict/pragmatic with no deltas. Synthetic cases cover both
governance flags (boolean false, textual false, invalid objects), enabled settings,
time-decay descriptions and controls, conflicting duplicate segment rows in both
orders/platforms, offset-based latest/at/trend selection, and isolated custom
GOV-002/GOV-006 timestamp formats plus an invalid consumed custom boolean override.
Pragmatic does not consume the document-presence signal because GOV-003 is absent;
its unchanged outcome is intentional. Candidate errors comprise 16 invalid-input
cases and one rubric-error case.

The verifier independently fetches and checks the pinned baseline, installs both
revisions into isolated locked environments, checks installed import origins,
grades the same inputs, and compares every outcome against these records. It runs
every case twice and requires byte-identical HTML/JSON for each version. Trend
cases check the CLI gate and complete point reports/timestamps/sources through a
structured API probe, since the trend CLI does not support JSON output. Successful
single reports preserve every schema/category/finding/score field. The original
v1.2.2 gate runs separately with its original narrow allowances.

Initial fixture preparation used Python 3.12 from the repository environment,
with the exact archived baseline source and candidate source selected explicitly
in separate subprocesses outside the checkout. This is preparation evidence only;
the authoritative gate is `python scripts/verify_release_compatibility.py --uv uv`
using uv 0.11.16, locked independent installed environments, and both immutable
baseline checks. Historical audit and release evidence is not modified.
