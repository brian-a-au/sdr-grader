# Private compatibility corpus and calibration admission

The current private store contains 108 compatibility snapshots: 100 CJA Data
Views and 8 AA report suites. It is private and unavailable in a clean
checkout. Zero entries are currently admitted to the calibration cohort, so
the release makes no grading-calibration claim and the bundled thresholds
remain maintainer judgment.

Compatibility collection and calibration admission are separate:

- A compatibility entry proves that the current adapters, grader, renderer,
  and plugin paths handle that snapshot without failure.
- A calibration entry additionally requires explicit permission, sanitizer
  success, and a recorded human review confirming that descriptions contain no
  identifying material.

`scripts/calibrate_thresholds.py` consumes only explicitly admitted entries
and regenerates [`threshold_calibration.md`](threshold_calibration.md).
Regenerate that tracked report whenever the admitted cohort changes and bind
release evidence to the candidate SHA and corpus revision in
`RELEASE_CHECKLIST.md`.

The corpus itself is **never committed**. Real SDRs carry tenant-
identifying material even after sanitization (component naming
conventions, custom taxonomy choices, internal jargon). The repository's
`.gitignore` already excludes `tests/fixtures/private/`; treat that
directory as the corpus root.

## Layout

The directory does not exist in the repository — `.gitignore` already
reserves `tests/fixtures/private/`, and you create it locally the first
time you add a snapshot:

```
tests/fixtures/private/        # gitignored, create locally
├── manifest.yaml              # cohort metadata for every snapshot
├── aa/
│   ├── sdr_<anon_id>.json
│   └── ...
└── cja/
    ├── sdr_<anon_id>.json
    └── ...
```

An example manifest in the expected shape lives at
`docs/calibration_manifest.example.yaml`.

## Intake workflow

1. Obtain the raw SDR snapshot (output of `aa_auto_sdr` /
   `cja_auto_sdr`). Confirm permission for private compatibility testing.
   Calibration requires separate permission when compatibility-only use is not
   sufficient.
2. Run the sanitizer:
   ```bash
   uv run python scripts/sanitize_sdr.py /path/to/raw.json \
       --platform cja \
       --output tests/fixtures/private/cja/sdr_<anon_id>.json \
       --redact "AcmeCorp,acmecorp.com"
   ```
   The sanitizer prints a suggested `anon_id`. Use it in the manifest.
3. **Manually review descriptions** in the sanitized JSON. The sanitizer
   does not touch `description` fields on dimensions, metrics, segments,
   or calculated metrics — the linter grades those for presence and
   quality, so blanket-stripping them would invalidate the calibration.
   Read through them; if any contain customer names, project codes, or
   PII, re-run with `--redact` or edit by hand.
4. Add an entry to `tests/fixtures/private/manifest.yaml` using the schema
   below. Leave `calibration.admitted` false unless the explicit human-review
   requirements are complete.
5. If at least one entry is admitted, run the threshold-distribution script:
   ```bash
   uv run python scripts/calibrate_thresholds.py \
       --corpus tests/fixtures/private/ \
       --output docs/threshold_calibration.md
   ```

## What the sanitizer touches

| Field                                       | Treatment                              |
|---------------------------------------------|----------------------------------------|
| `report_suite.rsid` / `parent_rsid` (AA)    | Replaced with `rsid_<hash>`            |
| `report_suite.name` (AA)                    | Replaced with `rs-name_<hash>`         |
| `data_view.data_view_id` (CJA)              | Replaced with `dv_<hash>`              |
| `data_view.data_view_name` (CJA)            | Replaced with `dv-name_<hash>`         |
| `metadata.Data View ID/Name` (CJA)          | Replaced with matching anonymized tokens |
| `owner` (emails on components)              | Replaced with `owner-<hash>@anon.example` |
| Anything matched by `--redact`              | Replaced with `[redacted]`             |
| Component descriptions / names              | **Untouched** — review manually        |
| Tags                                        | Untouched                              |

Hashes are SHA-256 truncated to 8–10 characters, so the same input
produces the same output every run (determinism).

## Manifest schema

`tests/fixtures/private/manifest.yaml`:

```yaml
version: 1
entries:
  - anon_id: sdr_abc123def0
    platform: cja                      # cja | aa
    file: cja/sdr_abc123def0.json
    submitted_at: "2026-05-21"         # YYYY-MM-DD, when added to corpus
    cohort:
      size: M                          # S | M | L; used as cohort label only,
                                       #   never as a rule input
      industry: retail                 # optional, for distribution slicing
    anonymization:
      reviewed_descriptions: true      # human confirmed PII-free
      redact_words: ["AcmeCorp"]
    calibration:
      admitted: true
      reviewed_by: "maintainer-name"
      reviewed_at: "2026-07-29"
    notes: |
      Optional free-text. Anything you want future-you to know about
      this snapshot's quirks (large segment library, unusual attribution
      mix, etc.).
```

### Cohort sizing rubric

`cohort.size` is a label for slicing the calibration output, not an
input to any rule. Use:

- **S** — combined (dimensions + metrics + segments + calc metrics) < 100
- **M** — 100 to 500
- **L** — > 500

This bucket is intentionally coarse. The point is to spot whether a
ratio threshold behaves differently for small vs large implementations,
not to fine-grain the population.

## Calibration confidence

For explicitly admitted entries, `scripts/calibrate_thresholds.py` writes
`docs/threshold_calibration.md`. Each rule gets a confidence rating:

- **high** — distribution observed across ≥ 8 snapshots in both
  platforms, with a clear inflection between healthy and unhealthy
  populations.
- **medium** — observed across ≥ 4 snapshots, but the distribution is
  smooth (no obvious cut point) or the denominator is small enough that
  individual snapshots swing the percentile noticeably.
- **low** — fewer than 4 observations, or the underlying denominator is
  usually < 10 (e.g. tenants with very few calc metrics make
  "% missing description" statistically meaningless).

Percentiles remain descriptive rather than outcome validation. Low-confidence
thresholds are expert judgment, and even high-confidence distributions do not
become a calibration claim without an independently documented healthy versus
unhealthy outcome model.

## What does **not** belong in the corpus

- Snapshots whose use you do not have permission for.
- Synthetic snapshots — those live in `tests/fixtures/` (committed) and
  serve a different purpose: per-rule edge-case unit tests, not
  distribution calibration.
- Anything you have not human-reviewed for embedded PII in descriptions.
