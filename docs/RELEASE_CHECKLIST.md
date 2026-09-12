# Release checklist

This is the tracked control record for a release candidate. Complete it
against one immutable commit. A passing build is not publication
approval, and publication is not announcement approval.

## Candidate identity

- [ ] Version: `________`
- [ ] Candidate commit SHA (40 characters): `________`
- [ ] Annotated tag to create only after approval: `v________`
- [ ] Package/plugin/marketplace version: `________`
- [ ] Bundled pack version: `________`
- [ ] JSON schema version: `________`
- [ ] Candidate is the reviewed `main` commit and the working tree is
      clean.
- [ ] `python3 scripts/check_version_sync.py --tag v<version>` passes.
- [ ] No code, workflow, manifest, pack, generated example, or hosted
      control changed after the final evidence run.

## Required checks

Record the successful run URLs for these stable checks:

- [ ] `Lint`: `________`
- [ ] `Tests / Python 3.11`: `________`
- [ ] `Tests / Python 3.12`: `________`
- [ ] `Examples drift`: `________`
- [ ] `Version identity`: `________`
- [ ] `Dependency review`: `________`
- [ ] `CodeQL / Python`: `________`
- [ ] Cross-repository color-pack contract comparator against the exact grader
      and visualizer candidate commits, including mirrored text/non-text
      contrast-pair gates: `________`
- [ ] Linked green sibling `sdr-visualizer` PR or commit from the same release
      cycle (URL and SHA): `________`
- [ ] Strict plugin and clean local marketplace smoke: `________`
- [ ] Private compatibility-cohort attestation and entry count: `________`
- [ ] Calibration-cohort attestation and admitted entry count: `________`

An unavailable, inconclusive, skipped, or stale check is a failure. The
private corpus stays outside Git and public CI; its aggregate evidence must
identify the candidate, tool version, corpus revision, compatibility count,
and calibration-admitted count without customer identifiers, stable
fingerprints, raw scores, or local paths. A compatibility pass is not
calibration evidence.

Color-pack changes are a paired release gate. The comparator must prove exact
equality of the ordered catalog, every ordered source-swatch list, and the
required semantic-role list exported by both repositories. The linked sibling
PR or commit must be green in the same release cycle. Do not publish a
one-sided grader or visualizer color-pack change.

## Artifact evidence

- [ ] Command was exactly `uv build --no-sources --clear
      --no-create-gitignore`; the log says the wheel was built from the
      source distribution.
- [ ] Exactly one wheel and one sdist were produced.
- [ ] `scripts/verify_release_artifacts.py` passed and its JSON evidence
      is attached to the draft release.
- [ ] Wheel SHA-256: `________`
- [ ] Sdist SHA-256: `________`
- [ ] Wheel inventory tree SHA-256: `________`
- [ ] Sdist inventory tree SHA-256: `________`
- [ ] Wheel and sdist installed outside the checkout on Python 3.11 and
      3.12.
- [ ] Installed `sdr-grader --version`, CJA HTML+JSON, AA HTML+JSON,
      bundled packs/templates/CSS/data, and packaged Claude resources
      passed.
- [ ] Wheel and sdist produced byte-identical CJA/AA HTML+JSON outputs.
- [ ] GitHub attestation subject digests, issuer, repository, workflow,
      and candidate SHA match the evidence: `________`

Never rebuild after this point. A failed candidate is discarded; do not
move or reuse a published tag or version.

## Hosted controls

Save the before/after JSON or screenshots in the restricted release
evidence store. A repository file is not proof that a hosted setting is
effective.

- [ ] Repository description, homepage, and topics are correct.
- [ ] Private vulnerability reporting is enabled and a non-admin view
      exposes the Security policy/reporting route.
- [ ] Secret scanning and push protection are enabled.
- [ ] Dependency graph, Dependabot alerts, and security updates are
      enabled; no high/critical item is unresolved.
- [ ] A `main` ruleset requires pull requests, conversation resolution,
      and the stable checks above, prevents force pushes/deletion, and
      applies to administrators except for a narrow emergency bypass.
- [ ] A tag ruleset protects `v*` creation/update/deletion and prevents
      tag reuse.
- [ ] The `pypi` environment has the intended required reviewer and
      deployment-branch/tag policy. PyPI trusted publishing names this
      repository, `release.yml`, and environment exactly; no long-lived
      PyPI token exists.
- [ ] The `github-release` environment has the intended required
      reviewer and tag policy.
- [ ] CODEOWNERS review is required where intended.
- [ ] Code of Conduct, enforcement route, Security policy, issue
      templates, and community profile are visible publicly.
- [ ] The maintainer has recorded the ruleset/environment IDs and a
      second verified recovery path before enforcement.

## History and namespace scan

- [ ] Scan every reachable commit and tag, not only the working tree.
- [ ] Inspect `git lfs ls-files --all`, if LFS is configured.
- [ ] Inspect current and historical GitHub release assets and source
      archives.
- [ ] Inspect wheel/sdist member inventories and the public package
      namespace for every published version.
- [ ] Inspect plugin/marketplace archives and installed caches.
- [ ] Record each scanner/tool version and immutable build identity:
      `________`
- [ ] Resolve every high-confidence result. Each suppression names an
      owner, rationale, and expiry.
- [ ] Rotate a suspected live credential before history cleanup or
      disclosure investigation.
- [ ] Human security review covers HTML execution, sanitization,
      diagnostics, plugin authority, artifact inventory/provenance, and
      private-corpus handling: `________`

Confirmed private artifacts, live credentials, unexplained
high-confidence results, or unresolved high/critical advisories block
publication.

## Recovery procedure

Before changing a rule or environment, export its current configuration
and record its numeric ID. Confirm that the maintainer can still reach
repository settings through an independent authenticated session.

If a required-check rename or ruleset error blocks maintenance:

1. Prefer a normal pull request that restores the expected check name.
2. If that is impossible, use only the named maintainer emergency
   bypass on the affected ruleset.
3. Restore the saved configuration or correct the single affected rule;
   do not disable unrelated scanners or tag protection.
4. Record the actor, time, reason, before/after state, and recovery
   commit.
5. Re-enable enforcement immediately and verify from a non-admin/public
   view.

If publication partially succeeds, leave the GitHub release in draft,
classify the PyPI result, and follow the release-state recovery table.
Do not reuse the version. Yank an unsafe package and publish security
guidance when the defect affects privacy or security.

| Observed state | Permitted recovery |
| --- | --- |
| No candidate files on PyPI; GitHub release is still a draft with the exact candidate assets | Rerun the complete release workflow. Recovery verifies the distributions' tag-bound provenance and retained SHA-bound evidence before the normal publication path uploads them. |
| Some candidate files exist on PyPI, every existing digest matches, and the exact GitHub draft exists | Rerun the complete release workflow. Recovery verifies the draft distributions' provenance and evidence; the digest gate permits only the missing candidate file to upload, then publication continues. |
| All candidate files exist on PyPI, every digest matches, and the exact GitHub draft exists | Rerun the complete release workflow. Recovery verifies the draft distributions' provenance and evidence; upload is skipped and publication continues against the same bytes. |
| The failed run has no exact GitHub release to recover | Reuse the original retained candidate and evidence artifacts only after identity and provenance checks. If neither retained artifacts nor an exact frozen release is available, stop; rebuilding is forbidden. |
| Any PyPI filename or digest differs from the frozen candidate | Stop. Do not upload, publish the draft, move the tag, or reuse the version. Classify the incident and choose a new version only after review. |
| GitHub release is public but endpoint verification fails | Rerun the failed public verifier using read-only published-artifact recovery. Compare PyPI, GitHub, and evidence digests; never rebuild or replace assets. Fix forward or yank if the security classification requires it. |

On reruns, `Recover immutable artifacts` alone receives repository write access
for draft visibility. It selects the original retained candidate/evidence pair
first, or verifies frozen release assets when those artifacts are unavailable.
Recovery copies use attempt-qualified names and never overwrite the originals.
GitHub removes run artifacts during a full rerun; their prior presence does not
guarantee availability. Production must recover the exact frozen release assets
when no retained pair remains, or fail without rebuilding.
Every consumer validates manifest identity and provenance bound to repository,
source ref/SHA, and `release.yml` before executing package code. Smoke jobs use
read-only access. Public verifiers independently recover published assets with
read-only access, even when a publication dependency was skipped.

The terminal `Require complete release verification` job requires explicit success
for both artifact Python versions, frozen plugin smoke, prepublication README,
PyPI publication verification, and both public-install Python versions. It
checks every attempt of the same run and frozen SHA. A newer failed, skipped,
cancelled, or incomplete job supersedes an older success. Missing, ambiguous,
or unavailable API evidence fails closed; workflow color alone is not proof.

After a successful PyPI upload, version-specific metadata may take time to
propagate. The postpublication verifier allows up to five minutes for that
endpoint, with at most 16 attempts and backoff capped at 30 seconds. Ordinary
missing links remain immediate failures; digest or content mismatches are never
retried as propagation failures. Keep the GitHub release in draft if this bound
is exhausted and classify the observed PyPI state before recovery.

After matching public bytes and provenance are established, exact-version
installation discovery gets at most six attempts, five ten-second delays, and
a 120-second process timeout per attempt. Only the pinned uv diagnostic for the
requested version being absent permits retry, with refreshed index metadata.
Other resolver errors, wrong installed versions, and identity mismatches fail
immediately. Ordered installation diagnostics remain in attempt-qualified
artifacts. These recovery changes do not alter grading behavior.

A dispatch of `release.yml` is always a nonpublishing harness; only tag pushes
can publish. Use the checked-out version and a named scenario, for example
`gh workflow run release.yml --ref main -f version=1.2.9 -f scenario=success`.
Run all-jobs, failed-only, and individual-job reruns against the original run;
preserve job IDs, attempts, immutable hashes, and explicit negative outcomes.
The harness also saves its initial distributions and manifest under an exact
repository/run/source-SHA cache key and checks that the save succeeded. Full
reruns restore that same entry without prefix fallback, then validate provenance
and manifest identity before execution. A missing cache fails closed. This
backup is harness-only; production uses frozen release assets.
Harness fixture endpoint evidence does not substitute for public v1.3.0 checks.

Release workflow revisions are frozen into each tag. A fix merged after a tag
cannot change that tag's historical workflow run or make it load a new local
action. Apply this recovery path only to future tags that contain it; preserve
older red runs as incident evidence and use a new main-branch verification or
soak run to prove the fix.

## Publication approval

Approval expires after 24 hours and is invalidated by any candidate or
control change.

- [ ] Approver: `________`
- [ ] Approval timestamp: `________`
- [ ] Candidate SHA: `________`
- [ ] Gate/evidence revision: `________`
- [ ] Artifact digests: `________`
- [ ] Publish the exact approved bytes through the protected tag
      workflow.
- [ ] PyPI bytes, GitHub release bytes, attestations, and clean Python
      3.11/3.12 installs match the candidate.
- [ ] Remote Claude marketplace install and summary/findings/show/compare
      operations pass.

## Announcement approval

Start the 48-hour soak only when PyPI, GitHub, provenance, and the remote
plugin are simultaneously live and healthy.

- [ ] Start checkpoint: `________`
- [ ] `+4h` checkpoint: `________`
- [ ] `+24h` checkpoint: `________`
- [ ] `+48h` checkpoint: `________`
- [ ] No observation gap exceeded four hours.
- [ ] Inbound reports were triaged with severity and recovery class.
- [ ] Final readiness audit path: `________`
- [ ] Announcement approver and timestamp: `________`

For the bounded v1.2.3 soak, `.github/workflows/release-soak.yml` records
hourly public-release checkpoints from a frozen monitor revision. New or
updated grader issues block until a maintainer applies either
`soak-triaged-nonblocking` or `soak-triaged-resolved`. A failed workflow run
does not count as an observation and blocks finalization unless a maintainer
records an infrastructure-only disposition in release PR #46 using the marker
`sdr-grader-v1.2.3-soak-run-<run-id>-triaged-infrastructure`; release-health
failures restart the 48-hour soak instead. Rerunning a failed workflow is not
allowed because the runs API exposes only the latest attempt; use a new manual
dispatch so the failed run remains in the timeline. GitHub's repository-scoped
workflow token cannot read private vulnerability reports or secret-scanning
alerts, so the final GO additionally requires an owner-authenticated,
post-48h clearance comment carrying
`sdr-grader-v1.2.3-private-advisory-clear`. That clearance must be no more than
two hours old, records aggregate counts only, and never includes advisory or
alert content. The owner-side gate refreshes it until the announcement-GO
record is observable.

Do not announce while any release, security, control, calibration,
plugin, or soak evidence is missing or stale.

## Reference-policy 2.1 implementation verification

For package 1.4.0, verify both platforms/packs, mixed and excluded-only findings,
exact denominator/threshold behavior, complete escaped diagnostics, legacy packs,
and preserved canonical references with the offline reference-policy fixtures.
Run the historical compatibility comparator with the separate exact policy
expectations; preserve old baseline artifacts. Report schema stays 1. Existing
snapshots require no re-export, credentials, Adobe API collection, exporter
changes, or exporter-evidence source gates. U6 visualizer wording is independent
and does not gate the grader policy release. Paired color-pack gates apply when
color-pack contracts change; this release changes none.

Local implementation verification does not publish a release or establish
hosted controls, attestations, private-cohort admission, or publication approval.
Complete applicable publication gates above separately for an immutable candidate.
