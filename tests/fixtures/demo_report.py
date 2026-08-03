"""Canonical demo Report used for renderer tests and example regeneration.

Used as both:
- a stable input for renderer regression tests, and
- the source for scripts/generate_examples.py and examples/templated-report.html.

The `generated_at` timestamp is hard-coded so renderer output is deterministic.
"""

from __future__ import annotations

from datetime import UTC, datetime

from markupsafe import Markup

from sdr_grader.render import (
    Adapter,
    Category,
    Distribution,
    DistributionChart,
    Finding,
    FindingAction,
    FindingBlock,
    Methodology,
    Remediation,
    Report,
    Rubric,
    SkippedRules,
)
from sdr_grader.render.svg import category_comparison_chart, histogram_chart


def build_demo_report() -> Report:
    """Construct the canonical demo Report (B− CJA implementation)."""
    report = Report(
        id="SDR-2026-0425-PROD-WEB",
        instance_name="Production Web Analytics",
        instance_id="dv_prod_web",
        grade="B−",
        overall_pct=71,
        components_evaluated=487,
        components_skipped=0,
        components_skipped_reason=None,
        adapter=Adapter(platform="CJA", tool="cja_auto_sdr", version="3.5.17"),
        rubric=Rubric(pack="strict", version="2.0"),
        generated_at=datetime(2026, 4, 25, 9, 14, tzinfo=UTC),
        tldr_html=(
            "This illustrative implementation graded <strong>B−</strong>. In the configured reference "
            "distribution, that score is near the median. <strong>Schema hygiene</strong> and "
            "<strong>naming consistency</strong> "
            "are strong; the largest gaps are in <strong>calculated metric maintainability</strong> (61%) and "
            "<strong>governance posture</strong> (54%), driven by a long tail of duplicate-near-equivalent "
            "metrics and the absence of any tracked snapshot history. The five highest-priority remediations "
            "are listed below in severity-derived priority order."
        ),
        categories=[
            Category("Schema hygiene", 82, "B"),
            Category("Naming consistency", 79, "B−"),
            Category("Segment complexity", 74, "C+"),
            Category("Calc. metric maint.", 61, "D+"),
            Category("Attribution coverage", 68, "C"),
            Category("Governance posture", 54, "D"),
        ],
        remediations=[
            Remediation(
                text="Consolidate the seven near-duplicate revenue calculated metrics into a single canonical metric.",
                refs=["CALC-014"],
                priority_weight=6,
            ),
            Remediation(
                text=("Establish snapshot tracking for the data view via cja_auto_sdr and commit "
                      "the baseline to version control."),
                refs=["GOV-001"],
                priority_weight=4,
            ),
            Remediation(
                text=("Add descriptions to the 120 dimensions currently lacking them. Required fields "
                      "exist in the data view; populate them via the API."),
                refs=["SCH-003"],
                priority_weight=3,
            ),
            Remediation(
                text=("Refactor the three segments with nesting depth above 5 into composed sub-segments "
                      "to make their intent reviewable."),
                refs=["SEG-007"],
                priority_weight=2,
            ),
            Remediation(
                text=("Document the attribution override used by 12 data view metrics, or remove "
                      "overrides that are not intentional."),
                refs=["ATTR-004"],
                priority_weight=2,
            ),
        ],
        findings=[
            Finding(
                id="CALC-014",
                severity="high",
                category="calculated metric maintainability",
                title="Seven near-duplicate revenue calculated metrics detected",
                body=[
                    FindingBlock(kind="paragraph", html=(
                        "Jaccard similarity across calculated metric formulas identified seven metrics "
                        "with ≥ 0.85 formula overlap that all compute revenue per visit, with minor "
                        "variations in attribution model and allocation. They appear to be the result "
                        "of independent authors solving the same problem without coordination."
                    )),
                    FindingBlock(kind="components", items=[
                        "cm_revenue_per_visit              author: r.kim@      created: 2024-03-12",
                        "cm_rev_per_visit_v2               author: a.patel@    created: 2024-08-04",
                        "cm_revpv_lasttouch                author: r.kim@      created: 2024-11-19",
                        "cm_rev_visit_linear               author: m.chen@     created: 2025-01-22",
                        "cm_revenue_visit_corrected        author: a.patel@    created: 2025-04-08",
                        "cm_rpv_marketing                  author: l.gomez@    created: 2025-09-15",
                        "cm_rev_per_visit_final            author: r.kim@      created: 2026-02-03",
                    ]),
                    FindingBlock(kind="section", label="Why this matters", body_html=(
                        "Near-duplicate metrics produce subtly different numbers in different reports, "
                        "which surfaces as &ldquo;the dashboards disagree&rdquo; complaints from "
                        "executives. They also create maintenance debt: when the underlying definition "
                        "needs to change, all seven must be updated in lockstep, and inevitably one is missed."
                    )),
                    FindingBlock(kind="section", label="How to remediate", body_html=(
                        "Designate one canonical metric, document its attribution and allocation choices, "
                        "and update downstream Workspace projects to reference it. Deprecate the others "
                        "by tagging them with a sunset date and reviewing downstream references before "
                        "retirement."
                    )),
                ],
                actions=[
                    FindingAction("Review remediation plan", "#remediations"),
                    FindingAction("Review methodology", "#methodology"),
                ],
            ),
            Finding(
                id="GOV-001",
                severity="high",
                category="governance posture",
                title="No snapshot history detected for this data view",
                body=[
                    FindingBlock(kind="paragraph", html=(
                        "The grader could not locate any prior snapshots of this data view in the configured "
                        "snapshot directory. Without snapshot history, configuration changes cannot be diffed, "
                        "drift cannot be detected, and audit trails are unavailable for compliance review."
                    )),
                    FindingBlock(kind="section", label="How to remediate"),
                    FindingBlock(kind="code", text=(
                        "cja_auto_sdr dv_prod_web --include-all-inventory --format json "
                        "--output snapshots/snapshot_2026-04-25.json\n"
                        "sdr-grader snapshots/ --trend --output snapshots/trend.html"
                    )),
                    FindingBlock(kind="paragraph", html=(
                        "Store dated snapshots in version control and schedule the same supported export "
                        "command at an interval appropriate for the project."
                    )),
                ],
                actions=[
                    FindingAction("Review remediation plan", "#remediations"),
                    FindingAction("Review methodology", "#methodology"),
                ],
            ),
            Finding(
                id="SCH-003",
                severity="medium",
                category="schema hygiene",
                title="120 dimensions lack descriptions",
                body=[
                    FindingBlock(kind="paragraph", html=(
                        "120 dimensions in this data view have empty "
                        "<span class=\"mono\">description</span> fields. Descriptions are the primary way "
                        "new analysts and AI agents understand what a component measures; missing "
                        "descriptions force readers to infer intent from names alone, which is frequently wrong."
                    )),
                    FindingBlock(kind="section", label="Distribution", body_html=(
                        "Dimensions: 120 of 203 missing (59%). The strict@2.0 rubric threshold is 56%."
                    )),
                    FindingBlock(kind="section", label="How to remediate", body_html=(
                        "Use the component IDs reported above to populate descriptions via the data view "
                        "API. Establish a CI check that fails new components added without descriptions."
                    )),
                ],
                actions=[
                    FindingAction("Review remediation plan", "#remediations"),
                    FindingAction("Review methodology", "#methodology"),
                ],
            ),
            Finding(
                id="SEG-007",
                severity="medium",
                category="segment complexity",
                title="Three segments exceed nesting depth threshold",
                body=[
                    FindingBlock(kind="paragraph", html=(
                        "The rubric flags segments with container nesting depth above 5 as difficult to "
                        "review. Three segments in this data view exceed that threshold; the deepest "
                        "reaches depth 8."
                    )),
                    FindingBlock(kind="components", items=[
                        "seg_qualified_lead_v3             depth: 8     containers: event/session/person mixed",
                        "seg_high_intent_returning         depth: 6     containers: session/event nested",
                        "seg_b2b_account_engaged           depth: 6     containers: event/session mixed",
                    ]),
                    FindingBlock(kind="section", label="Why this matters", body_html=(
                        "Deep nesting makes intent illegible. Reviewers cannot easily tell whether the "
                        "segment matches what its name implies, and small definitional changes have "
                        "unpredictable population effects."
                    )),
                    FindingBlock(kind="section", label="How to remediate", body_html=(
                        "Decompose each segment into composed sub-segments, named for what each layer "
                        "captures. The surface segment then becomes a shallow combination of well-named "
                        "pieces, each independently reviewable."
                    )),
                ],
                actions=[
                    FindingAction("Review remediation plan", "#remediations"),
                    FindingAction("Review methodology", "#methodology"),
                ],
            ),
            Finding(
                id="ATTR-004",
                severity="medium",
                category="attribution coverage",
                title="12 data view metrics use attribution overrides without documentation",
                body=[
                    FindingBlock(kind="paragraph", html=(
                        "Twelve data view metrics configure an attribution override, but their descriptions "
                        "do not identify the model or explain why the override is appropriate."
                    )),
                    FindingBlock(kind="section", label="How to remediate", body_html=(
                        "Update each metric description to name the configured attribution model and its "
                        "purpose, or remove an override that is not intentional."
                    )),
                ],
                actions=[
                    FindingAction("Review remediation plan", "#remediations"),
                    FindingAction("Review methodology", "#methodology"),
                ],
            ),
            Finding(
                id="NAME-001",
                severity="low",
                category="naming consistency",
                title="Inconsistent prefix convention in custom dimensions",
                body=[
                    FindingBlock(kind="paragraph", html=(
                        "73% of custom dimensions follow the <span class=\"mono\">c_</span> prefix "
                        "convention. The rubric expects ≥ 80%. Four components diverge from the established pattern."
                    )),
                    FindingBlock(kind="components", items=[
                        "product_category          (expected: c_product_category)",
                        "user_segment              (expected: c_user_segment)",
                        "cart_value_band           (expected: c_cart_value_band)",
                        "last_search_term          (expected: c_last_search_term)",
                    ]),
                    FindingBlock(kind="section", label="How to remediate", body_html=(
                        "Rename the four affected components via the data view API. Document the prefix "
                        "convention in the SDR for future contributors."
                    )),
                ],
                actions=[
                    FindingAction("Review remediation plan", "#remediations"),
                    FindingAction("Review methodology", "#methodology"),
                ],
            ),
        ],
        methodology=Methodology(
            paragraphs=[
                ("This illustrative grade was produced by <span class=\"mono\">sdr-grader</span> using "
                 "the <span class=\"mono\">strict@2.0</span> rubric pack. The default CJA inventory "
                 "contains 27 rules across six active categories; six are represented by findings in "
                 "this report. Each rule contributes to a category subtotal weighted by severity "
                 "(critical: 4, high: 3, medium: 2, low: 1). Category subtotals roll up to the overall "
                 "score using the category weights defined in the rubric pack."),
                ("The grader is rule-based and deterministic — the same input always produces the same "
                 "grade. Findings carry stable rule IDs that can be checked against the rubric "
                 "documentation and rule definitions in the sdr-grader repository. Rules can be "
                 "suppressed or reweighted via a project-level "
                 "<span class=\"mono\">.sdr-grader.yaml</span>."),
            ],
            skipped=[
                SkippedRules(
                    ids=["CALC-001", "SEG-005"],
                    reason=(
                        "Suppressed by the demo project's example configuration to reflect an "
                        "accepted legacy documentation backlog."
                    ),
                ),
            ],
        ),
        distribution=Distribution(charts=[
            DistributionChart(
                label="Overall score vs reference distribution",
                svg=histogram_chart(your_score=71, median=67, p25=54, p75=79),
            ),
            DistributionChart(
                label="Category scores vs median (n = 142 instances)",
                svg=category_comparison_chart([
                    ("Schema hygiene",       82, 71),
                    ("Naming",               79, 73),
                    ("Seg. complexity",      74, 77),
                    ("Calc. metric maint.",  61, 72),
                    ("Attribution",          68, 68),
                    ("Governance",           54, 60),
                ]),
            ),
        ]),
    )
    # This fixture owns its static presentation fragments. Production report
    # values remain plain text unless their renderer construction site marks
    # them explicitly after escaping dynamic insertions.
    report.tldr_html = Markup(report.tldr_html)
    report.methodology.paragraphs = [
        Markup(paragraph) for paragraph in report.methodology.paragraphs
    ]
    for finding in report.findings:
        for block in finding.body:
            if block.html is not None:
                block.html = Markup(block.html)
            if block.body_html is not None:
                block.body_html = Markup(block.body_html)
    return report
