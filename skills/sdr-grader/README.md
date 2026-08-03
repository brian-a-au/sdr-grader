# sdr-grader Claude Code skill

Helps you ask follow-up questions about a `sdr-grader --json` output
without re-running the grader. Filter findings by severity / category /
rule, pull up the body and remediation for a specific finding, or diff
two grade JSONs side by side.

## Install

Either route works. The plugin route gives you `/plugin update` later.

### As a plugin (recommended)

```text
/plugin marketplace add brian-a-au/sdr-grader
/plugin install sdr-grader@sdr-grader
/reload-plugins
```

Invoke the installed plugin skill as `/sdr-grader:sdr-grader`.

### As a personal skill

```bash
mkdir -p ~/.claude/skills
ln -s "$(pwd)/skills/sdr-grader" ~/.claude/skills/sdr-grader
# or, if symlinks aren't an option:
cp -R skills/sdr-grader ~/.claude/skills/
```

Invoke a personal installation as `/sdr-grader`.

If the personal skill directory was created during the current session,
restart Claude Code so it discovers `~/.claude/skills/sdr-grader`.

## Use

Once installed, supply an explicit grade JSON path and ask for a summary,
finding filter, present-finding explanation, or comparison. The skill does not
search for reports or consult a rule catalog. Plugin and personal invocation
are intentionally namespaced differently as shown above.

The bundled helper script also runs as plain Python with no extra
dependencies if you prefer to call it directly:

```bash
python3 skills/sdr-grader/scripts/query_grade.py summary grade.json
python3 skills/sdr-grader/scripts/query_grade.py findings grade.json --severity high
python3 skills/sdr-grader/scripts/query_grade.py show grade.json CALC-014
python3 skills/sdr-grader/scripts/query_grade.py compare current.json baseline.json
```

The helper is read-only and dependency-free. It rejects oversized,
duplicate-key, non-finite, malformed, and unsupported-schema JSON.
Comparisons are authoritative only when schema, stable instance, platform,
adapter family, and rubric pack/version match. The first compare argument is
current/newer and the second is baseline/older; delta is current minus
baseline. Legacy reports remain readable for single-report operations with a
warning. Bundled prefixes are examples; custom stable finding IDs such as
`LAUNCH-001` are supported.

The canonical [schema-1 JSON output reference](https://github.com/brian-a-au/sdr-grader/blob/v1.2.2/docs/JSON_OUTPUT.md)
defines the complete field shape, nullability, finding-body variants, and
HTML-string trust rules. When the helper is used through Claude, its selected
output enters Claude conversation context. The skill warns and requires
acknowledgment before the first read unless the request already explicitly
acknowledges that boundary. Review and minimize the requested operation; the
[report-sharing privacy matrix](https://github.com/brian-a-au/sdr-grader/blob/v1.2.2/SECURITY.md#report-sharing-privacy-matrix)
is the authority for that boundary and the other report-sharing surfaces.

## License

MIT (same as the parent project).
