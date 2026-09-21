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

Default packs `strict@3.0` and `pragmatic@3.0` each contain 31 rule
definitions: 23 shared, four CJA-only, and four AA-only. Each platform has
27 applicable checks. Platform-inapplicable rules are excluded from execution
and scoring. Applicable rules with incomplete required evidence may also be
excluded and disclosed as not assessed; availability is not proof of assessment.

## Bundled coverage inventory

Both default packs have the same IDs and platform inventory; severities and
parameters may differ. The existing six category weights are unchanged.

| Platform | Applicable rules | Excluded IDs |
|---|---:|---|
| CJA | 27 | AA-001, AA-002, AA-003, AA-004 |
| AA | 27 | SCH-007, SCH-008, SCH-009, ATTR-004 |

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

**AA administration coverage in the default packs.** Four AA-only rules
assess configuration against declared expectations: eVar
allocation/expiration, counter/numeric/currency success-event type, serialization,
and merchandising settings. These are not
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

The [AA administration input contract](AA_ADMIN_INPUT.md) combines expanded API
fields with supplementary observations and independent business expectations.
Use `--extra-input aa_admin=FILE` with the default strict pack or `--pack pragmatic`.
The standalone `--pack aa-admin` remains available for a four-rule-only report.
It assesses only declared targets; missing or unsupported evidence excludes the
entire affected rule from its denominator and reports it as not assessed.
Pack 3.0 includes AA-001/AA-004 in attribution coverage and AA-002/AA-003 in
schema hygiene. Complete evidence activates their scoring contribution; absent
evidence preserves the earlier numeric scores and discloses the missing checks.
Grades with different rubric versions or evidence scopes are not interchangeable.
The four additional checks have synthetic regression and CLI coverage; live
tenant/exporter verification remains pending. Settings agreement does not prove
runtime event-ID delivery, deduplication, or merchandising product binding.

**Honest framing.** The grader works on AA today and catches real
bugs there (broken references, naming inconsistency, segment
complexity, and documentation/governance gaps). It
is not a full audit of every AA configuration choice. The same boundary applies
to CJA: 27 applicable checks describes the available platform-specific inventory,
not complete platform certification. “27 of 27 assessed” is appropriate only for
a report whose effective inventory actually contains all 27 checks. Missing
required inputs must remain visible, never converted into passing results.

## Reference grading policy 2.1

AA and CJA use the same narrow exemption in SCH-002 and CALC-002 under both
bundled packs. Explicitly typed, unresolved calculated-metric segment references
remain unverified and unscored. Other reference kinds, unknown or ambiguous
identities, and references from segment consumers retain existing checks.
The reference-policy exemption is retained in the 31-ID catalog; platform applicability, suppression, and
excluded-only policy states determine the effective count for a snapshot.
The reference-policy behavior itself needs no exporter upgrade or re-export;
the AA admin additions have their separate evidence contract above. See
[Reference grading policy](REFERENCE_GRADING_POLICY.md).
