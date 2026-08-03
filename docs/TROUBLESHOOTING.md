# Troubleshooting installed `sdr-grader`

This guide covers the public, installed-user failure modes for `sdr-grader`
1.2.2. Run `sdr-grader --version` first so the diagnostic is tied to a known
release. File, directory, and stdin grading are local; only `--dataview` and
`--rsid` invoke child generators that call Adobe APIs.

## Missing generator

An error such as `cja_auto_sdr not found` or `aa_auto_sdr not found` applies
only to the child-generator modes. Install the generator separately; it is not
a dependency of `sdr-grader`:

- CJA: follow the upstream
  [installation instructions](https://github.com/brian-a-au/cja_auto_sdr#install-from-pypi-recommended).
- AA: follow the upstream
  [installation instructions](https://github.com/brian-a-au/aa_auto_sdr#install-from-pypi-recommended).

Confirm that the executable is on the same `PATH` used to launch the grader:

```bash
command -v cja_auto_sdr   # macOS or Linux
command -v aa_auto_sdr
```

```powershell
Get-Command cja_auto_sdr  # Windows PowerShell
Get-Command aa_auto_sdr
```

If the generator remains unavailable, generate the JSON in its own documented
environment and grade the downloaded file with `sdr-grader snapshot.json`.

## Adobe authentication

Adobe authentication is owned by `cja_auto_sdr` or `aa_auto_sdr`, not by the
grader. Configure the relevant generator's Adobe credentials and test that
generator directly before using `sdr-grader --dataview` or `--rsid`:

- [CJA credential configuration](https://github.com/brian-a-au/cja_auto_sdr#3-configure-credentials)
- [AA credential configuration](https://github.com/brian-a-au/aa_auto_sdr#3-configure-credentials-adobe-analytics-api-20-oauth-server-to-server)

Check the organization, client ID, scopes, and secret or certificate selected
by the generator. Do not paste credentials into a snapshot, report, issue, CI
log, or troubleshooting request. Child diagnostics are intentionally bounded;
rerun the generator itself when its full authentication error is needed.

## Incomplete CJA inventory

For a file or pipeline created directly by `cja_auto_sdr`, use
`--include-all-inventory`. Without it, calculated metrics and segments can be
absent or empty, so their rules have no input and stay silent. Regenerate, then
grade the new JSON:

```bash
cja_auto_sdr dv_prod_web --include-all-inventory --format json --output snapshot.json
sdr-grader snapshot.json --output grade.html --json grade.json
```

The installed `sdr-grader --dataview dv_prod_web` convenience mode supplies
`--include-all-inventory` automatically. `aa_auto_sdr` includes its component
inventories by default.

## Platform detection

The grader detects CJA or AA from the snapshot's JSON shape. If detection says
the shape is unknown or ambiguous, first confirm the file is the generator's
JSON output rather than an HTML, CSV, truncated download, or shell diagnostic.
You may explicitly select a known shape to diagnose it:

```bash
sdr-grader snapshot.json --platform cja --output grade.html
sdr-grader snapshot.json --platform aa --output grade.html
```

`--platform` does not convert one platform to another and does not make an
invalid or partial snapshot valid. Use the option only when you know which
generator produced the file.

## Mixed-platform and mixed-instance directories

Keep one platform and one Data View or report suite per directory. Ordinary
directory grading selects one candidate and only uses same-platform,
same-instance siblings as history evidence. A trend run must have timestamped
filenames and rejects a mixed-platform or mixed-instance directory.

A portable layout is:

```text
snapshots/
  cja/dv_prod_web/snapshot_2026-07-01.json
  cja/dv_prod_web/snapshot_2026-08-01.json
  aa/prod_us/snapshot_2026-08-01.json
```

Move files with Finder or `mv` on macOS, a file manager or `mv` on Linux, and
File Explorer or `Move-Item` on Windows. Then point `sdr-grader --trend` at a
single leaf directory.

## Generator compatibility warning

`warning [generator-version]` means the snapshot reports a generator version
newer than the newest version tested with this grader release. The warning is
not an authentication error and does not stop grading, but newer snapshot
fields may not be represented. Check the
[sdr-grader changelog](https://github.com/brian-a-au/sdr-grader/blob/main/CHANGELOG.md)
for a newer compatible release. If none exists, retain the warning with the
grade and review the resulting findings before using them as a gate.

Do not silence the warning by editing the snapshot's version field; that would
make its provenance inaccurate.

## Output-path error

HTML and JSON destinations must resolve to different regular files. A symlink,
the same path supplied to both flags, an unwritable parent, a read-only file, or
an invalid platform-specific filename can produce an output-path error.

Use a writable local directory and distinct extensions:

```bash
mkdir -p reports  # macOS or Linux
sdr-grader snapshot.json --output reports/grade.html --json reports/grade.json
```

```powershell
New-Item -ItemType Directory -Force reports | Out-Null  # Windows PowerShell
sdr-grader snapshot.json --output reports\grade.html --json reports\grade.json
```

The grader creates missing parent directories, but it cannot bypass operating
system permissions. Avoid network shares while diagnosing a write failure, and
do not choose either input snapshot as an output destination.

## Privacy and safe diagnostics

Snapshots and reports can retain production-derived component names, IDs,
configuration fragments, and findings. Keep them local until the exact bytes
have been reviewed. Do not attach a raw snapshot or unreviewed report to a
public issue, chat, or CI artifact.

The current authority for what each output and sharing surface retains is the
[report-sharing privacy matrix](https://github.com/brian-a-au/sdr-grader/blob/main/SECURITY.md#report-sharing-privacy-matrix).
Prefer a synthetic reduction when reporting a defect, and follow that policy
before transferring any production-derived material.
