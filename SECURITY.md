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

## Report-sharing privacy matrix

This matrix is the privacy authority for every report-sharing surface. A report
does not contain the raw input snapshot, but it can retain production-derived
names, IDs, rule findings, remediation text, counts, configuration fragments,
and other implementation details. Review the exact bytes, not just the source
snapshot or a screenshot, before changing their audience.

| Surface | Retained data | Minimization / review | Access audience | Leaves the local machine? | Retention effect |
|---|---|---|---|---|---|
| HTML report | Self-contained grade, category scores, component names and IDs quoted by findings, remediation, methodology, and optional charts; large item lists may be capped | Open the complete file locally, inspect names and finding bodies, and share only the minimum report needed | Only local users until shared; after sharing, every recipient and system storing the file | No during local generation or viewing; yes when emailed, uploaded, synced, or opened through a remote service | The file remains until its holder deletes it; no automatic grader retention applies |
| Uncapped JSON | Complete report model including every finding body and uncapped component-item list, identities, versions, timestamps, and action targets | Treat as the highest-detail report; inspect with local tools, remove unnecessary copies, and prefer a smaller reviewed summary when full fidelity is unnecessary | Only local users until shared; after sharing, every recipient and system storing the file | No during local generation or local parsing; yes when uploaded, synced, or supplied to another service | The file remains until its holder deletes it; no automatic grader retention applies |
| CI logs | Command output, error diagnostics, workflow metadata, paths, and any text a workflow or failing command prints; `--quiet` suppresses the normal grader summary but not errors | Use `--quiet`, avoid printing report bodies or shell tracing, use generic paths, and review failed-step diagnostics | Repository collaborators and organization or CI administrators according to provider and repository settings | Yes for hosted CI because logs are sent to the CI provider; self-hosted routing depends on runner configuration | Controlled by the CI provider's log-retention settings, separately from artifact retention |
| GitHub Actions artifacts | The exact opted-in HTML and JSON files, including all data retained by each format | Upload only after an explicit repository opt in, review the full files, and prefer no upload for sensitive reports | Anyone allowed to access the workflow artifacts; public-repository artifacts are not confidential | Yes when the upload-artifact step runs; no upload occurs when the opt in is absent | Seven days reduces exposure duration but is not access control, sanitization, confidentiality, or durable public release evidence |
| Claude conversation context | Selected helper output such as a summary, filtered findings, one finding body and remediation, or a comparison; quoted report text can be included | Choose the narrowest helper operation, review the report path and requested fields, and acknowledge the boundary before the first read | The user and the Claude service, account, workspace, and administrators covered by the applicable provider policy | Yes when selected helper output is returned in the Claude conversation context | Controlled by the Claude account and provider policy; deleting a local report does not retract conversation content |

Retention changes how long a remote copy is kept. It does not change who can
read it while retained, remove sensitive content, make a public artifact
confidential, or turn a workflow artifact into durable release evidence.

## Private compatibility and calibration corpus

The corpus at `tests/fixtures/private/` is local-only and gitignored.
It never appears in commits, CI runs, or published releases. Compatibility
collection does not make an entry calibration evidence. See
[`docs/CALIBRATION_CORPUS.md`](docs/CALIBRATION_CORPUS.md) for the
intake workflow and privacy-review checklist.

## Supported versions

| Version | Security support |
|---|---|
| `1.2.x` | Supported |
| `1.1.x` | Not supported |
| `<1.1` | Not supported |

Only the latest supported minor line receives new security fixes. If
you are on an older line, upgrade before reporting an issue. A report
against an unsupported version is still useful when the behavior also
reproduces on the supported line.
