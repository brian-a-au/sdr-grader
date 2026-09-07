import json
from copy import deepcopy
from pathlib import Path

import yaml

from sdr_grader.cli.main import main

root = Path("/tmp/sdr-audit")
root.mkdir(exist_ok=True)
snapshot = {
    "report_suite": {"rsid": "audit"},
    "metadata": {"history_present": True, "sdr_doc_present": True},
    "metrics": [],
    "dimensions": [{"id": "variables/x", "name": "Web Page", "description": None, "tags": ["web"]}],
}
(root / "minimal.json").write_text(json.dumps(snapshot))
base = yaml.safe_load(Path("src/sdr_grader/rules/packs/strict/_meta.yaml").read_text())
base.update(
    pack="order-audit",
    category_weights={"a": 0.1, "b": 0.2, "c": 0.7},
    severity_weights={"critical": 19, "high": 9, "medium": 1, "low": 1},
)
for name, weights in [
    ("abc", {"a": 0.1, "b": 0.2, "c": 0.7}),
    ("cba", {"c": 0.7, "b": 0.2, "a": 0.1}),
]:
    p = root / name
    p.mkdir(exist_ok=True)
    meta = deepcopy(base)
    meta["category_weights"] = weights
    (p / "_meta.yaml").write_text(yaml.safe_dump(meta, sort_keys=False))
    for cat, severity in [("a", "critical"), ("b", "medium"), ("c", "high")]:
        rules = [
            {
                "id": cat + "-pass",
                "severity": severity,
                "platforms": ["aa"],
                "check": "missing_descriptions",
                "params": {"threshold": 1, "targets": ["dimensions"]},
            }
        ]
        if cat != "b":
            rules.append(
                {
                    "id": cat + "-fail",
                    "severity": "low",
                    "platforms": ["aa"],
                    "check": "missing_descriptions",
                    "params": {"threshold": 0, "targets": ["dimensions"]},
                }
            )
        (p / (cat + ".yaml")).write_text(yaml.safe_dump({"category": cat, "rules": rules}))
    out = root / (name + ".json")
    rc = main(
        [
            str(root / "minimal.json"),
            "--rubric",
            str(p),
            "--output",
            str(root / (name + ".html")),
            "--json",
            str(out),
            "--fail-below",
            "A",
        ]
    )
    report = json.loads(out.read_text())
    print(
        name,
        report["overall_pct"],
        report["grade"],
        rc,
        [(x["name"], x["pct"]) for x in report["categories"]],
    )
# malformed suppression type should reject under documented list-of-strings contract
for value in [False, 0, {}, ""]:
    p = root / "bad-suppression.yaml"
    p.write_text(yaml.safe_dump({"suppress": [{"rule": "a-fail", "components": value}]}))
    out = root / "bad-suppression.json"
    out.unlink(missing_ok=True)
    rc = main(
        [
            str(root / "minimal.json"),
            "--rubric",
            str(root / "abc"),
            "--suppress-config",
            str(p),
            "--output",
            str(root / "bad-suppression.html"),
            "--json",
            str(out),
            "--fail-below",
            "A",
        ]
    )
    if rc != 0 and not out.exists():
        print("components=", repr(value), "rejected with exit", rc)
        continue
    report = json.loads(out.read_text())
    print("components=", repr(value), "score", report["overall_pct"], report["grade"], "exit", rc)
