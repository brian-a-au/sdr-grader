# Release verifier recovery

This repair applies to future tags containing it. It does not change or replace
[the original incident evidence](2026-09-07-release-verifier.md), historical tags,
release assets, or package files. No grading findings, scores, user CLI exits,
accepted grading inputs, rubric pack 2.0, JSON schema 1, thresholds, or severities
change as part of this prerequisite.

## Repair contract

Recovered packages require the original manifest and exact wheel/sdist inventory,
byte sizes and SHA-256 hashes, plus provenance bound to repository, source ref/SHA,
and `release.yml`. Original run artifacts remain immutable. Recovery copies use
attempt-qualified names. Public verifiers have read-only recovery independent of
publication dependency results; publication retains its existing prerequisites.

The terminal assertion examines every hosted attempt and requires explicit
success for all seven required verifier identities. A newer failure, skip,
cancellation, or incomplete job invalidates an older success. Missing, ambiguous,
or unavailable job evidence fails closed. A green workflow without these results
is not a verified release.

Only the observed pinned-uv exact-version-not-discovered diagnostic can retry:
six attempts, five ten-second delays, and a 120-second process timeout per attempt.
Matching public artifacts and frozen identity must pass first. Other failures
are immediate. Installer diagnostics remain ordered and attempt-qualified.

## Harness boundaries

`release.yml` retains the top-level PyPI Trusted Publishing identity. Every manual
dispatch is strictly nonpublishing; tag pushes cannot activate fixtures. The
harness uses the same production jobs, dependencies, immutable build, real hosted
attestation, artifact/plugin smoke checks, and terminal API assertion. Endpoint
fixtures call the existing production validators. A loopback package index serves
the retained distributions to the real uv installer; dependencies use the public
index. Fixture endpoint coverage is labeled separately from public-release proof.

Dispatch with the source version, for example:

```bash
gh workflow run release.yml --ref main -f version=1.2.9 -f scenario=success
gh run rerun RUN_ID
gh run rerun RUN_ID --failed
gh run rerun RUN_ID --job JOB_ID
```

Scenarios cover `success`, `fail-once`, `fail-later`, `skip`, `cancel`, `discovery`,
`exhausted`, `mismatch`, and `source-mismatch`. The `cancel` case prints a readiness
marker and requires actual cancellation. An individual public 3.12 rerun of
`fail-later` must invalidate the initial successful execution.

## Evidence status

Local focused workflow, installer, security, and terminal tests passed: 59 tests.
The tests exercise missing and superseded jobs, retries and fatal diagnostics,
process termination, fixture isolation, and provenance constraints. Lint and
actionlint 1.7.12 workflow validation passed.

Hosted evidence is required before v1.3.0 publication. This initial implementation
record does not claim prerequisite clearance. The release executor must append
run/job URLs, per-attempt outcomes, and immutable hash comparisons after executing
the harness, including explicit negative outcomes. Public v1.3.0 verification must
then succeed independently against actual GitHub and PyPI endpoints.

## Initial hosted fixture defect (preserved evidence)

Source `30d809be12ba2b49f06d4a13edf6d86b6d777b12` exposed missing HTTP
HEAD support in the fixture server. Real uv failed with HTTP 501; this remained
a fatal installer error and every terminal assertion correctly failed.
The real discovery case classified exact-version absence on attempt one, then
failed on HEAD during attempt two. These runs do not establish clearance:

- [Initial](https://github.com/brian-a-au/sdr-grader/actions/runs/34178138388)
- [One-time failure](https://github.com/brian-a-au/sdr-grader/actions/runs/34178234043)
- [Discovery](https://github.com/brian-a-au/sdr-grader/actions/runs/34178238011)

The focused fix shares response metadata between GET and HEAD and omits the
HEAD body. A real localhost HTTP regression failed before the fix and passed
afterward. Production endpoints and retry classification are unchanged.
New dispatches must prove the corrected source; rerunning an old frozen run
cannot load this fix. All original artifacts and failed evidence are retained.
