# Beta validation evidence

**Status: unverified — no candidate-specific beta exit decision is recorded.**

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
| Clean public install and version check | Pending | Pending |
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
