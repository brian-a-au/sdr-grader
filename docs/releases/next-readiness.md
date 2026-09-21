# Next release readiness record

**Decision: HOLD — candidate not selected; publication and announcement are not approved.**

This is the preparation record for the score-neutral public-preview patch.
Rename it to `<version>-readiness.md` when an unused version is selected.
The [release checklist](../RELEASE_CHECKLIST.md) is the canonical gate list;
all applicable checks must have candidate-specific evidence here before GO.
No pending field or historical observation counts as a passed gate.

## Identity and scope

| Field | Value |
| --- | --- |
| Package / plugin / marketplace version | Pending selection |
| Candidate release commit (40-character SHA) | Pending freeze |
| Annotated tag / tag object SHA | Pending approval and creation |
| Rubric / schema | Intended: 2.1 / 1; confirm against candidate |
| Wheel / sdist names and SHA-256 digests | Pending build-once validation |
| Artifact inventory and provenance evidence / digest | Pending |
| Evidence revision / durable evidence store | Pending |
| Monitor revision / candidate config digest | Pending |
| Announcement scope | Scoped public preview only |
| Accountable maintainer | Brian Au; approval not yet recorded |

Proposed claims: deterministic offline snapshot linting; versioned,
maintainer-judgment thresholds; CJA 27/27 bundled rules; AA 23/27, excluding
eVar allocation/expiration, success-event type distinctions, serialization,
and merchandising product binding. This is not a complete AA audit or a
calibration-validated measure of implementation quality. Review findings
against the source platform before production changes.

## Evidence register

| Required evidence | Status / reference |
| --- | --- |
| Lint; Python 3.11 and 3.12 source tests; 99% coverage | Pending candidate checks |
| Examples drift; version identity; dependency review; CodeQL | Pending candidate checks |
| Color-pack comparator and same-cycle companion | Pending diff review; N/A only if contracts unchanged |
| Strict packaged plugin and clean marketplace smoke | Pending |
| Private compatibility attestation: candidate, tool, corpus revision, platform counts | Pending authorized run |
| Calibration admission attestation: candidate, corpus revision, admitted counts | Pending authorized confirmation; historical documented count is zero |
| Aggregate beta validation and exit decision | Missing; see [beta validation](../BETA_VALIDATION.md) |
| Artifact inventories; installed wheel/sdist equivalence; provenance | Pending |
| Hosted controls; history/namespace scans; human security review | Pending owner verification |
| Publication approval and terminal release-completion run | Pending |
| Public endpoint bytes and remote plugin operations | Pending |
| Final readiness audit | Pending |

## Environment and workflow evidence

| Environment / workflow | Evidence boundary |
| --- | --- |
| Ubuntu, Python 3.11 and 3.12 | Existing CI matrix; new candidate results pending |
| macOS, Python 3.12 | Historical local audit only; new candidate results pending |
| Windows / later Python versions | Unverified; no verified-support claim |
| CJA and AA file/directory/stdin; strict/pragmatic; HTML/JSON; threshold exits | Candidate evidence pending |
| Live `--dataview` / `--rsid` and exporter versions | Unverified for this candidate; credential/network behavior is separate |
| Plugin summary/findings/show/compare | Candidate evidence pending |

## Soak and decision record

Start only when PyPI, GitHub, provenance, and the remote plugin are simultaneously
healthy. Capture hourly observations and retain the complete timeline.

| Evidence | Value |
| --- | --- |
| Start / +4h / +24h / +48h checkpoints | Pending |
| Maximum observation gap (limit four hours) | Pending |
| Failed-run dispositions and inbound report triage | Pending |
| Timeline URL / SHA-256 / durable copy | Pending |
| Post-48h owner private clearance / timestamp | Pending |
| Final audit path / evidence revision | Pending |
| Exact approved announcement copy | Pending |
| Publication approver / timestamp / candidate identity | Not approved |
| Announcement approver / timestamp / candidate identity | Not approved |

No GO may be inferred from the passage of time, synthetic tests, a successful
workflow alone, or a previous release's evidence. Broader grading claims remain
on Hold until independent outcome validation supports them.
