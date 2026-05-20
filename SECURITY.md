# Security and privacy

## Reporting vulnerabilities

If you find a security issue in `sdr-grader` — for example, an adapter
that can be tricked into executing input, a path-traversal bug in the
CLI, or anything else that lets a malicious snapshot affect the host
running the grader — please report it privately.

Open a GitHub Security Advisory at
<https://github.com/brian-a-au/sdr-grader/security/advisories/new>
rather than a public issue. I aim to respond within a week.

## Reporting false positives on private data

The default rubric is calibrated against a corpus of real CJA + AA
implementations. If a rule fires incorrectly on your snapshot, you
have two options:

1. **Open a public issue** with a synthetic, anonymized reduction of
   the snapshot that reproduces the false positive. Use
   `scripts/sanitize_sdr.py` to scrub tenant identifiers, then trim
   the snapshot to the smallest shape that still triggers the bug.
2. **Open a private security advisory** (link above) if the snapshot
   itself is sensitive and you'd rather not anonymize it. Include the
   raw snapshot in the advisory; I'll work with you to extract the
   reduction needed to fix the rule.

## Snapshot handling

The grader is offline by design. It reads JSON snapshots from disk and
writes HTML / JSON reports to disk. It does not transmit snapshot
contents anywhere. The rendered HTML report embeds the snapshot's
component IDs and names but does not embed the raw snapshot itself.

If you're concerned about leaking component names through a rendered
report (e.g., naming conventions that reveal customer or project
codes), redact those names in the snapshot before grading, or grade
locally and gate which reports are shared.

## Calibration corpus

The corpus at `tests/fixtures/private/` is local-only and gitignored.
It never appears in commits, CI runs, or published releases. See
[`docs/CALIBRATION_CORPUS.md`](docs/CALIBRATION_CORPUS.md) for the
intake workflow and anonymization checklist.

## Supported versions

Only the latest released version receives security fixes. If you're on
an older version, upgrade before reporting issues.
