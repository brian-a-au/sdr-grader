# Next release readiness record

**Decision: HOLD — candidate not selected; publication and announcement are not approved.**

This is the preparation record for the public-preview readiness work and the
AA administration checks in the default packs. The added capability expands the original
patch scope; select the release version under the project's version policy.
Rename it to `<version>-readiness.md` when an unused version is selected.
The [release checklist](../RELEASE_CHECKLIST.md) is the canonical gate list;
all applicable checks must have candidate-specific evidence here before GO.
No pending field or historical observation counts as a passed gate.

## Development verification — September 20, 2026

Prior development verification at `7ffc58b` on `chore/announcement-readiness`
(before default-pack integration):

- macOS / Python 3.12.13: 1,873 tests passed; 99.08% source coverage.
- Ruff lint, version identity, and generated-example drift checks passed.
  A separate optional repository-wide format check found existing formatting
  differences; no broad formatting rewrite was made.
- The soak workflow parsed, and all 15 shell steps passed Bash syntax and
  ShellCheck. A regression test verifies exact durable comment retention before
  disabling the monitor. The candidate configuration remains inactive.
- An isolated installed wheel produced CJA, AA, and optional AA-admin HTML/JSON
  reports outside the checkout, with bundled pack/plugin/template resources.
- Adobe's documented eVar response shape is covered, including API null fields.
  Invalid binding IDs are rejected. Supplementary event evidence and all four
  rule pass/fail/exclusion paths have synthetic coverage. No live tenant was used.
- Independent Astra inspection found and verified the fixes for completion
  comment newlines, API null handling, and malformed binding IDs.
  Code review: skipped (ce-code-review unavailable) — the full review could not
  complete because of the agent thread limit. A manual diff scan and the bounded
  independent inspection supplement testing; they are not a full review receipt.

### Default-pack integration follow-up

The four AA administration checks are now included in `strict@3.0` and
`pragmatic@3.0`: 31 catalog definitions, 27 applicable checks per platform.
They retain the existing six category weights and exclude missing evidence.

- 1,885 tests passed with 99.08% source coverage; Ruff and version checks passed.
- Generated examples are stable. Existing fixture scores remain unchanged;
  AA reports without the new evidence disclose four unassessed rules.
- The isolated installed default CLI assessed all 27 AA rules with complete
  evidence, and 23 with four disclosures when the supplementary input was absent.
- Actual installed compatibility gates passed against v1.2.2 and v1.2.9,
  including 65 exact correctness outcomes. A separate reviewed expectation
  layer preserves the historical contracts. New probes require all four AA
  findings and exact category/overall scores, including the implicit default CLI.
- Independent Astra inspection covered default-pack wiring, scoring exclusions,
  claims, and the compatibility transformation. Its test assertion and scoring
  probe findings were corrected. No full release-review receipt is claimed.

These are development checks, not approved release evidence. Package version
1.4.0 is still the development identity; select an unused candidate version and
refresh release-pinned documentation links before publication. Re-run the
candidate checks and complete independent review after that freeze.

## Identity and scope

| Field | Value |
| --- | --- |
| Package / plugin / marketplace version | Pending selection |
| Candidate release commit (40-character SHA) | Pending freeze |
| Annotated tag / tag object SHA | Pending approval and creation |
| Rubric / schema | Default packs 3.0; standalone aa-admin 1.0; JSON schema 1 |
| Wheel / sdist names and SHA-256 digests | Pending build-once validation |
| Artifact inventory and provenance evidence / digest | Pending |
| Evidence revision / durable evidence store | Pending |
| Monitor revision / candidate config digest | Pending |
| Announcement scope | Scoped public preview only |
| Accountable maintainer | Brian Au; approval not yet recorded |

Proposed claims: deterministic offline snapshot linting; versioned,
maintainer-judgment thresholds; 27 applicable default checks per platform from
a shared catalog of 31. Four AA-only default checks compare allocation/
expiration, success-event type, serialization, and merchandising settings
against declared expectations when evidence is complete. Its synthetic checks
do not verify live API collection, runtime event IDs, or product binding.
This is not a complete AA audit or a
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
| Default AA admin API fields and supplementary event configuration | Synthetic validation available; live tenant evidence and operator source review pending |
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
