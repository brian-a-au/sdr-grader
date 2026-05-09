#!/usr/bin/env bash
# File the remaining SPEC §13 design questions as GitHub issues.
#
# Issues #1 and #2 are already filed. This script files #3, #4, #5.
# Run it once after the auto-mode classifier blocked the agent from
# completing the original task. Idempotency: gh issue create has no
# native dedupe, so don't run twice.

set -euo pipefail

REPO=brian-a-au/sdr-grader
LABEL=design-question

gh issue create --repo "$REPO" --label "$LABEL" \
  --title "Confirm: suppressions surface in methodology with their reasons" \
  --body "$(cat <<'EOF'
From SPEC §13 open question 3.

Today \`.sdr-grader.yaml\` suppressions appear in the rendered report's
methodology \`Skipped rules\` section, grouped by reason
(\`src/sdr_grader/rules/suppression.py::summarize_suppressed\`). Anyone
reading the report sees which rules were muted and why.

Alternatives considered:
- Hide suppressions entirely (cleaner reports, harder to audit).
- Show suppressions only in the JSON output, not the HTML.

Current behavior chosen to keep grades defensible — reviewers notice
that a finding was muted rather than silently absent.

**Decision needed:** confirm this is the right user-facing behavior, or
pick one of the alternatives.
EOF
)"

gh issue create --repo "$REPO" --label "$LABEL" \
  --title "Should the JSON output include the rendered HTML inline?" \
  --body "$(cat <<'EOF'
From SPEC §13 open question 4.

Today \`--json PATH\` writes only the structured Report data; \`--output
PATH\` writes the rendered HTML separately. CI artifacts therefore need
two paths to capture the full output.

Including the HTML inline (e.g. as a base64-encoded \`html\` field on the
JSON) would simplify CI artifact handling at the cost of bloating the
JSON. The HTML is also already an artifact in its own right.

**Decision needed:** keep them separate (current), inline the HTML in
the JSON, or add a flag like \`--json-with-html\` for the inline variant.
EOF
)"

gh issue create --repo "$REPO" --label "$LABEL" \
  --title "Coordinate with cja_auto_sdr on a stable JSON schema version" \
  --body "$(cat <<'EOF'
From SPEC §13 open question 5.

Today the CJA adapter detects shape heuristically — \`metadata.Data View
ID\` is the canonical marker, with fallbacks for \`data_view_id\` and
\`dataViewId\`. The schema isn't versioned; we accept whichever shape
\`cja_auto_sdr\` happens to emit.

If \`cja_auto_sdr\` exposes a stable JSON schema version, this grader
should validate against it (with a clear error when versions disagree)
rather than tolerating shape drift silently. Same for \`aa_auto_sdr\`.

**Decision needed:** open a coordination issue on
\`brian-a-au/cja_auto_sdr\` and \`brian-a-au/aa_auto_sdr\` to agree on a
\`schema_version\` field and the deprecation policy when it changes.
EOF
)"

echo "Filed 3 design-question issues."
