# Platform coverage

## Public preview evidence boundary

Grading is provisional. Bundled thresholds and severities reflect maintainer
judgment, and zero implementations are currently admitted to grading
calibration. Treat findings as review prompts: verify each one against the
source implementation before changing production configuration.

The tested preview matrix is Ubuntu with Python 3.11 and 3.12. macOS with
Python 3.12 has historical local exercise only. Windows and later Python
versions are unverified, although the README retains Windows examples as
guidance. The package metadata's Python 3.11-or-newer requirement is an
installation constraint, not a claim that every later Python or operating
system combination has been verified.

The default packs grade both CJA and AA, but the two platforms
expose different configuration surfaces — so coverage is broader on
CJA than on AA. Thresholds apply only where the platform exposes the
underlying field.

Bundled pack `2.1` contains 27 rule definitions. All 27 apply to CJA;
23 apply to AA. The four CJA-only definitions below are excluded from
AA execution and from its scoring denominator.

## Bundled coverage inventory

The `strict` and `pragmatic` 2.1 packs have the same ID and platform
inventory; only severities and parameters differ.

| Platform | Applicable rules | Excluded IDs |
|---|---:|---|
| CJA | 27 | — |
| AA | 23 | SCH-007, SCH-008, SCH-009, ATTR-004 |

**Private evidence boundary.** The 108-entry private cohort contains 100 CJA
Data Views and 8 AA report suites and is used for compatibility regression.
Zero entries are currently admitted to calibration, so bundled thresholds are
maintainer judgment rather than a grading-calibration claim. CJA-informed
thresholds apply to AA only where the underlying field shape is equivalent
(descriptions, tags, complexity, nesting); see the audit for the per-rule
rationale and [`CALIBRATION_CORPUS.md`](CALIBRATION_CORPUS.md) for admission
requirements.

**CJA-only rules** grade CJA Data View and derived-field semantics. They are
not AA rules awaiting more input fields: AA excludes them from execution and
scoring rather than treating them as passed:

| Rule | What it grades |
|---|---|
| SCH-007 | Persistence lookback against the 90-day platform cap |
| SCH-008 | Derived field circular references |
| SCH-009 | Derived field references to missing components |
| ATTR-004 | Data View metric attribution override without rationale |

**Separate AA coverage gaps.** The grader does not yet assess these four
AA admin areas: eVar allocation/expiration, counter versus numeric success
events, event serialization, and merchandising product binding. These are not
one-to-one replacements for SCH-007, SCH-008, SCH-009, and ATTR-004.

As checked on September 20, 2026, Adobe documents read access to eVar
allocation, expiration, merchandising syntax, and binding events through
[Dimensions API expansions](https://developer.adobe.com/analytics-apis/docs/2.0/guides/endpoints/dimensions/).
The [migration guide](https://developer.adobe.com/analytics-apis/docs/2.0/guides/migration)
still excludes reading success-event configuration objects. Event reporting
`type` is not proof of the configured counter/numeric type or serialization.
The earlier blanket claim that all four areas require the legacy Admin API
is outdated; Adobe's [1.4 retirement notice](https://developer.adobe.com/analytics-apis/docs/1.4/guides/eol/)
gives August 31, 2026 as the retirement date.

Closing these gaps requires AA-specific rules, documented input contracts,
and evidence-aware applicability. API documentation alone does not establish
that an installed exporter captures the fields or that a rule has been
validated. Missing evidence must be reported as not assessed rather than
counting as a successful check. No such new rules ship in pack 2.1.

**Honest framing.** The grader works on AA today and catches real
bugs there (broken references, naming inconsistency, segment
complexity, and documentation/governance gaps). It
is not a full audit of every AA configuration choice. CJA's 27-of-27
bundled-rule coverage likewise describes this pack, not a complete audit
of every CJA configuration choice. If you're picking a launch tier:

- **CJA**: full default-pack coverage including Data View settings.
- **AA**: 23 applicable rules from the current bundled catalog, excluding
  the four CJA-only definitions. The separate AA admin gaps above remain
  unassessed until new rules and their required evidence are implemented.

## Reference grading policy 2.1

AA and CJA use the same narrow exemption in SCH-002 and CALC-002 under both
bundled packs. Explicitly typed, unresolved calculated-metric segment references
remain unverified and unscored. Other reference kinds, unknown or ambiguous
identities, and references from segment consumers retain existing checks.
The catalog still contains 27 IDs; platform applicability, suppression, and
excluded-only policy states determine the effective count for a snapshot.
No exporter upgrade, live API collection, or re-export is required. See
[Reference grading policy](REFERENCE_GRADING_POLICY.md).
