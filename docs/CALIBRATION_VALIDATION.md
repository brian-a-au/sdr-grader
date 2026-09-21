# Independent calibration validation protocol

Status: **HOLD — protocol and acceptance values pending approval; no study has
been run and no accuracy claim is supported.**

This protocol defines the evidence required before describing a bundled rule
threshold, pack, or score as calibrated or validated. The distribution report
from `scripts/calibrate_thresholds.py` is an input to study design only. Its
`confidence` label is a heuristic over meaningful-observation count, smallest
denominator, and observed range; it is not an accuracy estimate, an inflection
test, or an outcome label.

Do not claim validation or clear this hold until
an approved study plan has filled every `Pending` item below, frozen those
choices before review begins, and recorded passing results against the frozen
criteria. Compatibility snapshots and calibration-admitted snapshots do not
become outcome evidence merely by appearing in a distribution report.

## Pre-registration gate

The study owner and an independent reviewer must approve and date a candidate-
bound study record before any outcome labels are inspected. That record must
include:

| Item to freeze before review | Required record | Current state |
|---|---|---|
| Candidate and rubric identity | Commit SHA, package version, pack revisions, and rule parameters | Pending |
| Primary claims | Exact rule/pack, platform, and strict/pragmatic claims the study is powered to assess | Pending |
| Independent organizations | Minimum total organizations and minimum per platform; one organization may not be counted more than once | Pending |
| Snapshot sampling | Inclusion/exclusion rules, sampling frame, time window, and at most one primary snapshot per organization per platform | Pending |
| Held-out split | Organization-level development/held-out allocation and randomization seed; no organization may cross splits | Pending |
| Review volume | Minimum applicable findings and minimum reviewed non-findings per rule/platform/pack cell | Pending |
| Applicability floor | Minimum organizations on which each rule is applicable; cells below it are reported as insufficient evidence | Pending |
| Accuracy thresholds | Maximum false-discovery and false-omission proportions; any claimed population false-positive/false-negative rates; interval method and bound | Pending |
| Agreement threshold | Minimum independent-reviewer agreement and the statistic used | Pending |
| Pack-level criteria | Permitted score error or decision disagreement, if any pack/score claim is proposed | Pending |
| Multiplicity and exclusions | Handling of multiple rules/cells, missing fields, abstentions, and unusable evidence | Pending |

The values must be justified prospectively. Observed results must not be used
to choose the sample minimums, cutoffs, split, exclusions, or acceptance
thresholds. Any later change creates a new protocol version and requires a new
held-out evaluation.

## Corpus, independence, permission, and privacy

Recruit organizations independently of the maintainers who chose the current
thresholds. Record an opaque organization identifier so that multiple
snapshots, business units, or submissions from the same organization remain in
one split and count as one organization for independence totals. Report
snapshot counts separately from organization counts.

Obtain explicit permission for outcome-validation use; compatibility-testing
or distribution-calibration permission alone is insufficient. Apply the
sanitization and description review in
[`CALIBRATION_CORPUS.md`](CALIBRATION_CORPUS.md), minimize retained data, limit
access to named reviewers, and record retention and deletion terms. The public
study report contains only aggregate cells large enough to satisfy the
predeclared privacy rule. It must not publish snapshots, organization
identities, component text, or small-cell details that could identify a
participant.

The repository contains neither the private corpus nor human labels. Store the
approved protocol, access log, consent/permission record, split assignment,
adjudication log, and immutable result digest in the authorized evidence
system. A release record may cite their identifiers and aggregate results; it
must not copy private source data into the repository.

## Platform, pack, and rule applicability

Evaluate every proposed claim as a separate rule × platform × pack cell.
Derive applicability from the candidate's bundled rubric rather than assuming
that AA and CJA have the same rule inventory. A rule excluded by its platform
configuration is not a true negative and must not enter that cell's
denominator. Likewise, missing source evidence that makes a rule incapable of
assessment must follow the predeclared abstention/exclusion policy.

Run both `strict` and `pragmatic` configurations using their actual candidate
parameters and severities. Do not reuse a strict judgment as pragmatic evidence
when different parameters change which records the rule flags. Report cells
separately before any permitted roll-up. Evidence for one platform, pack, or
rule does not validate another, and this protocol does not authorize adding a
platform or expanding a rule's configured applicability.

## Blind review and adjudication

Freeze the candidate output for every sampled snapshot, then construct two
review queues per applicable cell:

1. **Findings:** every flagged item, or the predeclared probability sample if
   volume makes full review impractical. Record the sampling weights.
2. **Non-findings:** a predeclared probability sample of eligible items that
   the rule did not flag. Reviewing non-findings is mandatory because false
   negatives cannot be estimated from findings alone.

Two qualified reviewers who did not select the threshold independently label
each queued item against a written, rule-specific outcome rubric while blinded
to pack, threshold, grader result, other reviewer, and development/held-out
assignment where practical. Labels are `actionable defect`, `acceptable`, or
`insufficient evidence`, with a reason code and cited source evidence.

After independent labeling, disagreements go to a third qualified adjudicator.
The adjudicator sees the source evidence and the two rationales, records a
final label and reason, and may not silently discard ambiguous cases.
`Insufficient evidence` is reported separately and handled exactly as
predeclared; it must not be converted into a favorable label. Retain the
original labels so agreement can be calculated before adjudication.

## Analysis and decision

Use the development split only for investigating candidate thresholds or
clarifying the review rubric. Any threshold or procedure selected with that
split is frozen before opening held-out labels. Evaluate the held-out split
once. Further tuning requires a newly reserved held-out set from independent
organizations.

For each rule × platform × pack cell, publish at least:

- independent organization, snapshot, applicable-item, finding, reviewed-
  finding, reviewed-nonfinding, abstention, and adjudication counts;
- false-discovery proportion: false positives divided by reviewed findings;
- false-omission proportion: false negatives divided by reviewed non-findings;
- if population error rates are claimed, sampling-weighted estimates of
  FP / (FP + TN) and FN / (FN + TP), with the declared unit of analysis;
- predeclared uncertainty intervals accounting for sampling and clustering
  within organizations, rather than treating all component labels as independent;
- reviewer agreement before adjudication; and
- the frozen acceptance criterion, result, and `PASS`, `FAIL`, or
  `INSUFFICIENT EVIDENCE` decision.

A claim passes only when every cell in its predeclared scope meets its sample,
applicability, agreement, and declared error criteria on the
held-out organizations. A failed or underpowered cell cannot be hidden by an
aggregate. Pack-level or score-level claims also require their separately
predeclared criterion to pass. Report adverse results and exclusions alongside
successful cells.

## Hold condition for validation claims

The current disposition is **HOLD**. It remains HOLD while any prerequisite is
pending, the protocol lacks independent approval, permission or privacy review
is incomplete, the held-out study has not run, a scoped cell fails, or evidence
is insufficient. Clearing the hold requires all of the following:

1. a dated, independently approved pre-registration with every pending value
   resolved;
2. an authorized corpus satisfying the frozen independent-organization,
   platform, applicability, and review-volume minimums;
3. completed blinded review, non-finding review, and adjudication;
4. immutable aggregate results bound to the candidate and protocol version;
5. a recorded decision showing every claimed cell passed; and
6. maintainer review of any resulting threshold or documentation change.

This hold governs validation claims, not a separately approved scoped preview.
Any score-changing correction still requires versioned rubrics, migration
evidence, a new candidate, and fresh release gates.

Until then, public language must say that thresholds are maintainer judgment
and that generated percentiles are descriptive distribution evidence only.
