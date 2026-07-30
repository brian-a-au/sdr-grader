# Security and privacy

## Reporting vulnerabilities

If you find a security issue in `sdr-grader` — for example, an adapter
that can be tricked into executing input, a path-traversal bug in the
CLI, or anything else that lets a malicious snapshot affect the host
running the grader — please report it privately.

Open a private security advisory at
<https://github.com/brian-a-au/sdr-grader/security/advisories/new>
rather than a public issue. I aim to respond within a week.

## Reporting false positives on private data

The default rubric has been compatibility-tested against real CJA + AA
implementations, but its thresholds remain maintainer judgment until an
explicitly admitted calibration cohort exists. If a rule fires incorrectly on
your snapshot, you have two options:

1. **Prefer a synthetic reduction** that reproduces the false positive
   without using production-derived values.
2. **If a production-derived reduction is necessary**, run
   `scripts/sanitize_sdr.py`, trim the result to the smallest reproducer,
   and manually inspect every key and value. The script emits a
   restricted review candidate, not an approval to disclose it.

Do not attach a raw snapshot to a public issue or security advisory.
Contact the maintainer through a private advisory first and agree on the
minimum data needed before uploading any production-derived candidate.
GitHub is a third-party service and attachments are retained under its
policies.

The sanitizer prints a SHA-256 review digest without echoing private file
paths. Record a share/abort decision against that digest so later edits do
not inherit an earlier review. For release or calibration evidence, the
maintainer performs a second review of the exact digest; the submitter's
review is not sufficient by itself.

## Snapshot handling

File and stdin grading read JSON snapshots locally and write HTML / JSON
reports locally. The rendered HTML report embeds the snapshot's component
IDs and names but does not embed the raw snapshot itself.

If you're concerned about leaking component names through a rendered
report (for example, naming conventions that reveal customer or project
codes), keep the report local until a human has reviewed the complete
artifact.

## Private compatibility and calibration corpus

The corpus at `tests/fixtures/private/` is local-only and gitignored.
It never appears in commits, CI runs, or published releases. Compatibility
collection does not make an entry calibration evidence. See
[`docs/CALIBRATION_CORPUS.md`](docs/CALIBRATION_CORPUS.md) for the
intake workflow and privacy-review checklist.

## Supported versions

| Version | Security support |
|---|---|
| `1.2.x` | Supported after `1.2.0` is published |
| `1.1.x` | Supported until `1.2.0` is published |
| `<1.1` | Not supported |

Only the latest supported minor line receives new security fixes. If
you are on an older line, upgrade before reporting an issue. A report
against an unsupported version is still useful when the behavior also
reproduces on the supported line.
