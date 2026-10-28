# Beta validation evidence

**Status: unverified — no candidate-specific beta exit decision is recorded.**

Current preparation: [1.6.1](releases/1.6.1-readiness.md), with
prospective candidate-specific beta evidence pending. The latest published release is [1.6.0](releases/1.6.0-readiness.md).
Candidate-specific beta evidence for it is pending. Earlier release records are
historical; their artifact identities and engineering checks remain in those ledgers.
The owner confirms independent testing of prior releases. The candidate-specific
beta protocol, participation details, findings, and exit decision remain unrecorded.

Historical statements that beta rounds occurred are not an acceptance record.
The documented 108 compatibility snapshots (100 CJA, 8 AA) are not counts of
independent beta participants, organizations, or calibration-admitted entries.
This document defines the aggregate evidence to collect; its existence does
not satisfy the [release checklist](RELEASE_CHECKLIST.md).

## Before the round

The release owner records the candidate SHA, package/rubric/schema versions,
permitted data use, intended announcement claims, coverage requirements, and
exit criteria before reviewing outcomes. Use existing authorized records if
they contain this evidence; otherwise run a prospective round and identify it
as such. Keep participant identities and supporting reports in the restricted
evidence store. Do not solicit or publish raw production snapshots here.

Use these severity definitions consistently:

- **P0:** private-data exposure, credential exposure, or unsafe artifact/plugin
  behavior requiring immediate containment. Stop the round and follow SECURITY.md.
- **P1:** confirmed incorrect grading or output, installation failure, or broken
  core workflow that invalidates an advertised use without a reliable workaround.
- **P2:** bounded defect or usability problem with a documented workaround or an
  explicitly excluded workflow. Record an owner, disposition, and limitation.

Preview exit requires no unresolved P0/P1, disposition of every P2, completion
of the intended workflow/environment coverage, candidate-bound compatibility
and calibration-status attestations, and the release owner's recorded decision.
No minimum participant count or accuracy claim has been approved. Record actual
independent participation and its limits rather than inventing a target after
the results are known.

For a new release, obtain source/tag-preparation authorization and use the
protected tag workflow to build and retain the immutable wheel/sdist before
running candidate-specific beta attempts. Keep the protected `pypi` approval
pending; local pretag builds are engineering checks, not the approved pair. Install those exact artifacts for the
prepublication round; confirm public installation after publication. A public
install cannot be a prerequisite for publishing that same new candidate.
For an already published candidate, run a prospective round against the exact
public version and record that timing; it does not establish a historical
prepublication beta pass.

## Aggregate round record

| Field | Evidence |
| --- | --- |
| Round / dates / protocol revision | Pending |
| Candidate SHA / package / rubric / schema | Pending |
| Independent participants / independent organizations | Unknown |
| CJA / AA snapshot counts | Unknown for this round |
| OS / Python / exporter versions | Pending |
| Required coverage and acceptance criteria approved before round | Pending |
| Permission and private human-review attestation | Pending |
| Restricted evidence reference / public evidence revision | Pending |

## Workflow results

For each row record attempts, completions, independent organizations, tested
environments, and issue dispositions. Do not substitute a synthetic test pass
for a beta attempt. Mark unavailable live flows unverified.

| Workflow | Attempts / completions | Findings / evidence |
| --- | --- | --- |
| Clean frozen-artifact install and version check (new candidate, prepublication) | Pending | Pending |
| Clean public install and version check (postpublication) | Pending | Pending |
| CJA file grading, complete component inventory | Pending | Pending |
| AA file grading and coverage disclosure | Pending | Pending |
| Directory and stdin inputs | Pending | Pending |
| HTML and JSON review | Pending | Pending |
| Strict and pragmatic packs | Pending | Pending |
| Threshold exits and CI interpretation | Pending | Pending |
| Plugin summary / findings / show / compare | Pending | Pending |
| Live CJA `--dataview` / exporter version | Pending | Unverified |
| Live AA `--rsid` / exporter version | Pending | Unverified |

## Findings and exit decision

| Evidence | Result |
| --- | --- |
| Confirmed P0 / P1 / P2 counts and unresolved counts | Unknown |
| False-positive themes, reviewed denominator, rule/platform | Pending |
| False-negative themes, reviewed non-findings denominator, rule/platform | Pending |
| Remediation usefulness and reviewer disagreement | Pending |
| P2 owners, dispositions, and workarounds | Pending |
| Unresolved risks and limits of the sample | Pending |
| Candidate-bound compatibility corpus revision / CJA / AA counts | Pending |
| Candidate-bound calibration admitted count / review attestation | Pending |
| Exit decision / reviewer / timestamp / evidence revision | HOLD / pending |

False-positive and false-negative themes are qualitative until a defined
sampling and independent labeling method supports rates. Small or incomplete
samples cannot support universal implementation-quality claims.

Publish aggregate evidence only after privacy review: no customer names,
production-derived component text, stable fingerprints, raw scores, local paths,
raw snapshots, or unreviewed report excerpts. Public issue links may be used only
when their contents already meet that boundary. See [SECURITY.md](../SECURITY.md)
and the [calibration admission contract](CALIBRATION_CORPUS.md).
