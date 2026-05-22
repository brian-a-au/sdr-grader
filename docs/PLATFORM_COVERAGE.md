# Platform coverage

The default packs grade both CJA and AA, but the two platforms
expose different configuration surfaces — so coverage is broader on
CJA than on AA, and thresholds are calibrated on the platform where
the data lives.

**Calibration corpus.** Default thresholds were measured against
108 real-world snapshots: 100 CJA Data Views and 8 AA report suites.
Every threshold in the rubric ships with its source in
[`threshold_calibration.md`](threshold_calibration.md)
(percentile + confidence per rule). CJA-derived thresholds apply to
AA on rules where the underlying field shape is equivalent
(descriptions, tags, complexity, nesting) — see the audit for the
per-rule rationale.

**CJA-only rules** grade Data View configuration that AA's 2.0
Reporting API doesn't expose. They no-op on AA snapshots rather than
false-firing:

| Rule | What it grades |
|---|---|
| SCH-007 | Persistence lookback against the 90-day platform cap |
| SCH-008 | Derived field circular references |
| SCH-009 | Derived field references to missing components |
| ATTR-004 | Data View metric attribution override without rationale |

**Known AA coverage gaps.** Four bug classes the audit identifies as
high-leverage are not yet implementable from the AA 2.0 Reporting
API alone — the underlying configuration (counter / numeric event
types, eVar allocation+expiration, event serialization, merchandising
eVar product binding) lives in the legacy 1.4 Admin API surface.
Adobe has indicated these are migrating to 2.0 eventually; until
then the rule shapes are documented in
[`RUBRIC_AUDIT.md`](RUBRIC_AUDIT.md) so they're ready when
the data is.

**Honest framing.** The grader works on AA today and catches real
bugs there (broken references, naming inconsistency, segment
complexity, governance signals — all calibrated and verified). It
just isn't yet a full audit of every AA configuration choice the way
it is for CJA. If you're picking a launch tier:

- **CJA**: full default-pack coverage including Data View settings.
- **AA**: full default-pack coverage minus the four
  admin-surface rules above. Plan to revisit when Adobe ships the
  2.0 admin endpoints.
