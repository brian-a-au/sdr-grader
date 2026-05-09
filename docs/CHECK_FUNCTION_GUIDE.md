# Writing a check function

Rules are YAML; checks are pure Python functions. Adding a new rule is a
YAML entry. Adding a new *kind* of check is a Python function plus a YAML
reference. This separation is non-negotiable.

## The contract

A check function lives in `src/sdr_grader/rules/checks/<category>.py`.
It is registered with `@register_check("name")` and has the shape:

```python
from sdr_grader.rules.checks._helpers import category_display, compact
from sdr_grader.render import Finding, FindingBlock
from sdr_grader.rules.registry import register_check

@register_check("missing_descriptions")
def check_missing_descriptions(impl, ctx) -> list[Finding]:
    threshold = float(ctx.params.get("threshold", 0.10))
    # … pure logic against impl …
    return [
        Finding(
            id=ctx.rule_id,
            severity=ctx.severity,
            category=category_display(ctx.category),
            title=f"{count} components lack descriptions",
            body=[FindingBlock(kind="paragraph", html="…")],
        )
    ]
```

## Properties

A check function must be:

- **Pure.** No I/O, no globals, no side effects. Same `Implementation`
  + same `RuleContext` -> same findings, byte-for-byte.
- **Returning a list.** Empty list = the rule passed cleanly. Multiple
  findings allowed for rules that surface several distinct issues.
- **Self-contained.** Don't reach into other check modules. Shared
  helpers go in `rules/checks/_helpers.py`.
- **Tolerant of shape variation.** The normalized model is stable but
  some fields can be `None` (e.g. `description`, `owner`, `data_type`).
  Default sensibly.

## Inputs

| Symbol            | Type                | What it is                          |
|-------------------|---------------------|-------------------------------------|
| `impl`            | `Implementation`    | Normalized model (SPEC §5)          |
| `ctx`             | `RuleContext`       | Per-rule context the engine assembles |
| `ctx.rule_id`     | `str`               | The rule ID from YAML               |
| `ctx.severity`    | `str`               | Already-overridden severity         |
| `ctx.category`    | `str`               | Slug; use `category_display()` to humanize |
| `ctx.params`      | `dict[str, Any]`    | Verbatim from the YAML rule's `params:` |
| `ctx.rationale`   | `str`               | YAML rationale (informational)      |
| `ctx.remediation` | `str`               | YAML remediation; useful as a finding section |

## FindingBlock kinds

The renderer understands four block kinds. Use them to compose finding
bodies:

- `paragraph` with `html` — free prose; raw inline HTML allowed.
- `section` with `label` + optional `body_html` — labeled subsection
  (e.g. "Distribution", "Why this matters", "How to remediate").
- `components` with `items: list[str]` — each line renders as a row
  (used for ID lists).
- `code` with `text` — preformatted block.

Conventional finding shape:

```python
[
    FindingBlock(kind="paragraph", html="<topline summary>"),
    FindingBlock(kind="section", label="Distribution", body_html="<numbers>"),
    FindingBlock(kind="components", items=["id1  some metadata", ...]),
    FindingBlock(kind="section", label="How to remediate", body_html="<advice>"),
]
```

## Registering and wiring up

1. Add the function to the right `rules/checks/<category>.py`.
2. Add an import line for the module in
   `rules/registry.py::_import_all_checks()` if it's a new file.
3. Add the rule definition to the YAML in your pack:

   ```yaml
   - id: NEW-001
     name: My new rule
     severity: medium
     platforms: [cja, aa]
     check: my_check_function
     params:
       threshold: 0.20
     rationale: |
       Why this matters.
     remediation: |
       What to do about it.
   ```

4. Add at least one test in `tests/test_rules_<category>.py` that
   exercises the firing path and at least one quiet path.

## Determinism is testable

`tests/test_cli.py::test_cli_run_is_deterministic` asserts that two
runs over the same input produce byte-identical HTML. If your check
introduces randomness or wall-clock dependence, this test will catch
it. Don't bypass it; redesign the check.
