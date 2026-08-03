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
- [ ] Strict plugin and clean local marketplace smoke: `________`
- [ ] Private compatibility-cohort attestation and entry count: `________`
- [ ] Calibration-cohort attestation and admitted entry count: `________`

An unavailable, inconclusive, skipped, or stale check is a failure. The
private corpus stays outside Git and public CI; its aggregate evidence must
identify the candidate, tool version, corpus revision, compatibility count,
and calibration-admitted count without customer identifiers, stable
fingerprints, raw scores, or local paths. A compatibility pass is not
calibration evidence.

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
| No candidate files on PyPI; GitHub release is still a draft | Rerun the failed release job. The normal publication path uploads the frozen candidate. |
| Some candidate files exist on PyPI and every existing digest matches | Rerun the failed job. The digest gate permits only the missing candidate file to upload, then attestation and draft publication continue. |
| All candidate files exist on PyPI and every digest matches | Rerun the failed job. Upload is skipped; attestation and publication continue against the same bytes. |
| Any PyPI filename or digest differs from the frozen candidate | Stop. Do not upload, publish the draft, move the tag, or reuse the version. Classify the incident and choose a new version only after review. |
| GitHub release is public but endpoint verification fails | Do not rebuild. Compare PyPI, GitHub, and evidence digests, then fix forward or yank following the security classification. |

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

For the bounded v1.2.2 soak, `.github/workflows/release-soak.yml` records
hourly public-release checkpoints from a frozen monitor revision. New or
updated grader issues block until a maintainer applies either
`soak-triaged-nonblocking` or `soak-triaged-resolved`. A failed workflow run
does not count as an observation and blocks finalization unless a maintainer
records an infrastructure-only disposition in release PR #41 using the marker
`sdr-grader-v1.2.2-soak-run-<run-id>-triaged-infrastructure`; release-health
failures restart the 48-hour soak instead. Rerunning a failed workflow is not
allowed because the runs API exposes only the latest attempt; use a new manual
dispatch so the failed run remains in the timeline. GitHub's repository-scoped
workflow token cannot read private vulnerability reports or secret-scanning
alerts, so the final GO additionally requires an owner-authenticated,
post-48h clearance comment carrying
`sdr-grader-v1.2.2-private-advisory-clear`. That clearance must be no more than
two hours old, records aggregate counts only, and never includes advisory or
alert content. The owner-side gate refreshes it until the announcement-GO
record is observable.

Do not announce while any release, security, control, calibration,
plugin, or soak evidence is missing or stale.
