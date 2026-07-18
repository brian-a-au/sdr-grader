"""Canonical demo Report used for renderer tests and example regeneration.

Used as both:
- a stable input for renderer regression tests, and
- the source for scripts/generate_examples.py and examples/templated-report.html.

The `generated_at` timestamp is hard-coded so renderer output is deterministic.
"""

from __future__ import annotations

from datetime import UTC, datetime

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
    return Report(
        id="SDR-2026-0425-PROD-WEB",
        instance_name="Production Web Analytics",
        grade="B−",
        overall_pct=71,
        components_evaluated=487,
        components_skipped=23,
        components_skipped_reason="missing required schema fields",
        adapter=Adapter(platform="CJA", tool="cja_auto_sdr", version="3.5.17"),
        rubric=Rubric(pack="strict", version="1.2"),
        generated_at=datetime(2026, 4, 25, 9, 14, tzinfo=UTC),
        tldr_html=(
            "This implementation graded <strong>B−</strong>, sitting near the median for self-graded "
            "production CJA instances. <strong>Schema hygiene</strong> and <strong>naming consistency</strong> "
            "are strong; the largest gaps are in <strong>calculated metric maintainability</strong> (61%) and "
            "<strong>governance posture</strong> (54%), driven by a long tail of duplicate-near-equivalent "
            "metrics and the absence of any tracked snapshot history. The five highest-impact remediations "
            "are listed below; addressing the top three would move the overall grade to B+."
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
                refs=["CALC-014", "CALC-015", "CALC-022"],
                impact_pts=6,
            ),
            Remediation(
                text=("Establish snapshot tracking for the data view via cja_auto_sdr and commit "
                      "the baseline to version control."),
                refs=["GOV-001"],
                impact_pts=4,
            ),
            Remediation(
                text=("Add descriptions to the 38 metrics and 51 dimensions currently lacking them. "
                      "Required fields exist in the data view; populate them via the API."),
                refs=["SCH-003"],
                impact_pts=3,
            ),
            Remediation(
                text=("Refactor the four segments with nesting depth ≥ 5 into composed sub-segments "
                      "to make their intent reviewable."),
                refs=["SEG-007"],
                impact_pts=2,
            ),
            Remediation(
                text=("Document attribution model selection in calculated metrics — 12 metrics use "
                      "last-touch implicitly without justification."),
                refs=["ATTR-002"],
                impact_pts=2,
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
                        "by tagging them with a sunset date and auditing references via "
                        "<span class=\"mono\">cja_auto_sdr --org-report</span>."
                    )),
                ],
                actions=[
                    FindingAction("View rule definition", "#"),
                    FindingAction("Suppress this rule", "#"),
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
                        "cja_auto_sdr dv_prod_web --snapshot ./snapshots/baseline.json\n"
                        "cja_auto_sdr --git-init --git-dir ./snapshots\n"
                        "cja_auto_sdr dv_prod_web --git-commit --git-message \"Initial baseline\""
                    )),
                    FindingBlock(kind="paragraph", html=(
                        "From this baseline, schedule weekly snapshots via the GitHub Action template in "
                        "the <span class=\"mono\">cja_auto_sdr</span> examples directory."
                    )),
                ],
                actions=[
                    FindingAction("View rule definition", "#"),
                    FindingAction("Suppress this rule", "#"),
                ],
            ),
            Finding(
                id="SCH-003",
                severity="medium",
                category="schema hygiene",
                title="89 components lack descriptions",
                body=[
                    FindingBlock(kind="paragraph", html=(
                        "38 metrics and 51 dimensions in this data view have empty "
                        "<span class=\"mono\">description</span> fields. Descriptions are the primary way "
                        "new analysts and AI agents understand what a component measures; missing "
                        "descriptions force readers to infer intent from names alone, which is frequently wrong."
                    )),
                    FindingBlock(kind="section", label="Distribution", body_html=(
                        "Metrics: 38 of 142 missing (27%). Dimensions: 51 of 203 missing (25%). "
                        "Both rates exceed the rubric threshold of 10%."
                    )),
                    FindingBlock(kind="section", label="How to remediate", body_html=(
                        "Generate the list of components missing descriptions with "
                        "<span class=\"mono\">cja_auto_sdr --quality-report json</span> and populate via the "
                        "data view API. Establish a CI check that fails new components added without descriptions."
                    )),
                ],
                actions=[
                    FindingAction("View rule definition", "#"),
                    FindingAction("Suppress this rule", "#"),
                ],
            ),
            Finding(
                id="SEG-007",
                severity="medium",
                category="segment complexity",
                title="Four segments exceed nesting depth threshold",
                body=[
                    FindingBlock(kind="paragraph", html=(
                        "The rubric flags segments with container nesting depth ≥ 5 as difficult to review. "
                        "Four segments in this data view exceed that threshold; the deepest reaches depth 8."
                    )),
                    FindingBlock(kind="components", items=[
                        "seg_qualified_lead_v3             depth: 8     containers: event/session/person mixed",
                        "seg_high_intent_returning         depth: 6     containers: session/event nested",
                        "seg_b2b_account_engaged           depth: 6     containers: event/session mixed",
                        "seg_promo_responsive              depth: 5     containers: event nested",
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
                    FindingAction("View rule definition", "#"),
                    FindingAction("Suppress this rule", "#"),
                ],
            ),
            Finding(
                id="ATTR-002",
                severity="medium",
                category="attribution coverage",
                title="12 calculated metrics use last-touch attribution without documented rationale",
                body=[
                    FindingBlock(kind="paragraph", html=(
                        "Last-touch is the default attribution model and is appropriate for some use cases, "
                        "but the rubric flags it when applied to revenue and conversion metrics without "
                        "justification. Twelve such metrics were identified."
                    )),
                    FindingBlock(kind="section", label="How to remediate", body_html=(
                        "For each flagged metric, either change the attribution model to one appropriate "
                        "for the metric&rsquo;s intended use (algorithmic, linear, or U-shaped for "
                        "journey-aware metrics), or document in the metric description why last-touch "
                        "is the correct choice."
                    )),
                ],
                actions=[
                    FindingAction("View rule definition", "#"),
                    FindingAction("Suppress this rule", "#"),
                ],
            ),
            Finding(
                id="NAME-002",
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
                    FindingAction("View rule definition", "#"),
                    FindingAction("Suppress this rule", "#"),
                ],
            ),
        ],
        methodology=Methodology(
            paragraphs=[
                ("This grade was produced by <span class=\"mono\">sdr-grader v1.0.0</span> using the "
                 "<span class=\"mono\">strict@1.2</span> rubric pack. The rubric encodes 73 rules across "
                 "six categories; 68 ran successfully against the input data view and 5 were skipped "
                 "(see below). Each rule contributes to a category subtotal weighted by severity "
                 "(CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1). Category subtotals roll up to the overall "
                 "score using the category weights shown in the rubric definition."),
                ("The grader is rule-based and deterministic. The same input always produces the same grade. "
                 "Findings are auditable: every rule&rsquo;s source YAML is linked from its finding, and "
                 "rules can be suppressed or reweighted via a project-level "
                 "<span class=\"mono\">.sdr-grader.yaml</span>."),
            ],
            skipped=[
                SkippedRules(
                    ids=["PERF-001", "PERF-002"],
                    reason=(
                        "performance posture rules require Query Service access; "
                        "not configured for this run."
                    ),
                ),
                SkippedRules(
                    ids=["WS-001", "WS-002"],
                    reason=(
                        "workspace project quality rules require Workspace API scope; "
                        "not granted to the service account."
                    ),
                ),
                SkippedRules(
                    ids=["LBL-003"],
                    reason="data-labeling rule requires AEP governance API access.",
                ),
            ],
        ),
        distribution=Distribution(charts=[
            DistributionChart(
                label="Overall score vs publicly graded instances",
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
