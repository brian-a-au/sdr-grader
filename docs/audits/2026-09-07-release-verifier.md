# v1.2.8 public verifier: separately confirmed, deferred workflow patch

Evidence: [release run 34165517834](https://github.com/brian-a-au/sdr-grader/actions/runs/34165517834).
Read original and retry job APIs and original failed logs on 2026-09-07.
No rerun, rebuild, upload or publication was performed during this investigation.

## P1: green retry did not verify the release

`.github/workflows/release.yml:639` installs the exact new version through uv
**0.11.16** once. Attempt 1 job **101876541210**, Python 3.12, failed with
`Because there is no version of sdr-grader==1.2.8`. Python 3.11 job
**101876541274** succeeded. Publication/byte/provenance checks had succeeded.
This establishes temporary version discovery inconsistency, not which cache
or endpoint caused it and not a missing package artifact.

Attempt 2 is overall success, but its public matrix job **101876747830** is
**skipped**, as are publish-github and its upstream publication verification.
`verify-public` at lines 561-564 requires `publish-github.result == 'success'`.
The attempt-sensitive build/recover conditions (57,129) and dependent smoke
conditions (180-185,252-257) do not safely model a failed-jobs-only rerun:
successful build/plugin results are retained while the install matrix and
recovery path skip. The skip propagates to publication and the verifier.
There is no unconditional terminal assertion that all required verifiers ran.
Expected: retry must actually verify frozen bytes or fail visibly. Actual: no
public verification ran on retry. Score/grade impact: none; release assurance
is incomplete. A skipped verifier is not a pass.

Read-only reproduction:

```sh
gh api repos/brian-a-au/sdr-grader/actions/runs/34165517834/attempts/1/jobs --jq '.jobs[] | {name,conclusion,id}'
gh api repos/brian-a-au/sdr-grader/actions/runs/34165517834/attempts/2/jobs --jq '.jobs[] | {name,conclusion,id}'
gh run view 34165517834 --attempt 1 --log-failed
```

[GitHub's rerun contract](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs)
distinguishes all-jobs, failed-jobs and individual-job reruns and preserves the
original SHA/ref. Thus changing current main cannot repair the frozen v1.2.8
workflow by retrying it. The observed job graph, not just the run conclusion,
is authoritative evidence here.

## Bounded proposed follow-up (not implemented in the grading PR)

Give post-publication verification a read-only recovery path that independently
validates the frozen tag SHA, manifest, exact wheel/sdist hashes and provenance,
then public package identity and installed behavior. No dependency skip may
substitute for any check. Keep publication jobs gated; do not loosen their
conditions just to make the verifier runnable. Add a terminal always-run result
assertion requiring each required verifier's explicit success, including every
supported Python matrix entry. Cancellation/skips/failures cannot become success.

Only after frozen identity and matching public artifact evidence are established,
retry the observed exact-version-not-discovered condition with fresh index
metadata, a fixed attempt cap and delay budget (for example 6 attempts separated
by 10 seconds). Never retry hash/provenance mismatch, wrong version, dependency
conflicts, authentication failures, or arbitrary resolver failures as propagation.
Retain evidence on exhaustion. Never rebuild or republish on verifier recovery.

Required regressions: initial run, full rerun, failed-only rerun and individual
verifier rerun; discovery absent-then-present and always-absent; immediate fatal
mismatch; skipped/cancelled matrix entry; fixed artifact identity across all
attempts. Validate graph behavior on GitHub using synthetic immutable artifacts
before adopting it in release publication. This is separate from grading because
mocked Python tests alone do not establish hosted Actions rerun semantics.
