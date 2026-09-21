# Candidate release soak runbook

The monitor ships **inactive**. This runbook describes maintainer operations for
an approved published candidate; merging it does not start a soak or approve an
announcement. The [release checklist](RELEASE_CHECKLIST.md) remains authoritative.

## Prepare identities before activation

1. Merge and review the monitor implementation while `candidate.json` remains
   inactive. Retain that commit as `monitor_commit`. A later activation commit
   changes the manifest only. The validator compares the workflow and both
   monitor scripts byte-for-byte with the earlier implementation commit.
2. Complete publication and verify public PyPI/GitHub bytes, immutable tags,
   provenance, and the remote plugin. Record the actual release commit, tag
   object, asset names, and SHA-256 digests; do not substitute the monitor SHA.
3. Create a release evidence issue and an owner-authored placeholder comment in
   that issue. Save its permanent issue-comment URL. Apply the appropriate
   triage disposition to the evidence issue so it does not block its own soak.
   This URL is reserved before activation; it is not yet start evidence.
4. Fill the active manifest described below, including an unused window ID and
   planned UTC start/end at least 48 hours apart. Start the first successful
   checkpoint within two hours of the planned start. Finish all merges before
   the window and freeze main, monitor code, and applicable controls.
5. Validate with `python3 .github/scripts/validate_release_soak_config.py
   --verify-monitor`. Review and merge the activation manifest. Re-enable the
   workflow if it was disabled after a prior soak. The frozen activation SHA is
   this main revision; it differs from the published release and monitor commits.

## Manifest contract

The inactive form is `{"schema_version": 1, "active": false}`. Do not populate
an active manifest from guessed values. The active form requires:

| Field | Required value |
| --- | --- |
| `schema_version` / `active` | Integer `1` / boolean `true` |
| `release.version` / `release.tag` | Exact `X.Y.Z` / `vX.Y.Z` |
| `release.commit` / `release.tag_object` | Full lowercase 40-character immutable SHA values |
| `release.wheel` | `{name: sdr_grader-X.Y.Z-py3-none-any.whl, sha256: <64 hex>}` |
| `release.sdist` | `{name: sdr_grader-X.Y.Z.tar.gz, sha256: <64 hex>}` |
| `release.evidence` | `{name: release-artifacts.json, sha256: <64 hex>}` |
| `monitor_commit` | Earlier reviewed implementation commit |
| `window_id` | Unique lowercase letters/digits/hyphens, 8–64 characters |
| `start_at` / `end_at` | UTC timestamps in `YYYY-MM-DDTHH:MM:SSZ` form |
| `issue_number` | Positive integer for this repository's evidence issue |
| `start_evidence_url` | Exact `https://github.com/brian-a-au/sdr-grader/issues/<issue_number>#issuecomment-<id>` |
| `readiness_record` | Tracked `docs/releases/<version>-readiness.md` path |
| `companion` | Explicit applicability and rationale as described below |

Use `companion: {"applicable": false, "reason": "<reviewed reason>"}` for a
grader-only announcement with no companion contract change. An applicable
companion also requires `release` with the same identity fields, using
`sdr_visualizer` filenames and `SHA256SUMS` as evidence. Never inherit an old
visualizer release implicitly. Color-pack changes retain their separate paired
release gates.

The complete synthetic examples in `tests/test_release_soak_config.py` exercise
both candidate identities and companion branches. They are test identities,
not releasable manifests.

## Prove the start

After the first scheduled or manual first-attempt run succeeds, inspect its
`Public release checkpoint`, `Grader security and inbound reports`, and
`Retain aggregate checkpoint` jobs and retained artifact. All must be successful.
Update the reserved owner comment with **only** a JSON object of this form:

```json
{
  "config_sha256": "<SHA-256 of the exact raw candidate.json bytes>",
  "release_commit": "<published release commit>",
  "head_sha": "<frozen activation/main SHA>",
  "run_id": 123456,
  "window": "sdr-grader-v<VERSION>-<window_id>"
}
```

Use the actual numeric run ID. The finalizer fetches the authenticated comment,
run, and attempt-specific jobs; a URL or owner assertion alone does not establish
success. The observation start is the successful required jobs' completion time.
The +4h/+24h/+48h checkpoints and private-clearance boundary derive from that
actual start. A planned 48-hour end does not shorten the real observation window.

## Observe, triage, and retain

- The schedule runs hourly. Successful observations may never be more than four
  hours apart. Checkpoints must satisfy the verifier's two-hour tolerance.
- Use new manual dispatches if needed; never rerun an observation. A rerun can
  hide the first attempt and invalidates the timeline.
- Review every new or updated inbound report. The workflow checks the labels
  `soak-triaged-nonblocking` and `soak-triaged-resolved`; label freshness is a
  maintainer obligation. Remove an obsolete disposition when an update changes
  the report's severity or recovery class.
- A genuine infrastructure-only failed run needs a new owner comment with this
  exact standalone line: `<!-- <PREFIX>-soak-run-<RUN_ID>-triaged-infrastructure -->`.
  Explain the reason without secrets. A disposition does not create an observation
  or waive a gap. Release-health failures require repair and a new window.
- After 48 actual hours, the owner checks private vulnerability reports and
  secret-scanning state using owner credentials and posts aggregate clearance
  with the exact standalone line `<!-- <PREFIX>-private-advisory-clear -->`.
  Here `<PREFIX>` is the `window` value above. Clearance must be no more than two
  hours old at finalization; never post private advisory or alert contents.
- Monitor/config/main or relevant hosted-control changes invalidate the window.
  Start a new window with a new ID and proof after repair; retain prior failures.

The finalizer waits without producing completion evidence while a valid window
is still running or fresh owner clearance is pending. Invalid or unhealthy
evidence still fails. Once ready, it retains the full timeline JSON plus SHA-256 in
the evidence issue before disabling the workflow. Workflow artifacts are an
additional copy retained for 90 days. Preserve a durable copy in the release
record/evidence store, including the issue URL and digest. Oversized evidence
that cannot be retained causes finalization to fail rather than silently drop it.

`SOAK_COMPLETE` only means the observation record passed verification. The
release owner must still complete the final audit and explicitly approve the
announcement scope, copy, candidate identity, and evidence revision. Refresh
private clearance if it becomes stale before that decision. No automated output
claims successful live Adobe flows, empirical calibration, or announcement GO.
