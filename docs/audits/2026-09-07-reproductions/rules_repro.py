from copy import deepcopy

from sdr_grader.adapters.aa import adapt as aa
from sdr_grader.adapters.cja import adapt as cja
from sdr_grader.core.grader import grade
from sdr_grader.rules.rubric import load_rubric

rubric = load_rubric("src/sdr_grader/rules/packs/strict")
a = {
    "report_suite": {"rsid": "x"},
    "metrics": [],
    "dimensions": [],
    "metadata": {"history_present": True, "sdr_doc_present": True},
}
c = {
    "metadata": {"Data View ID": "x", "history_present": True, "sdr_doc_present": True},
    "metrics": [],
    "dimensions": [],
}


def run(label, data, adapter):
    r = grade(adapter(data), rubric)
    print(label, r.overall_pct, r.grade, [(f.id, f.title) for f in r.findings])


for val in (False, "false", {}, {"nonsense": 0}):
    x = deepcopy(a)
    x["metadata"]["history_present"] = val
    x["metadata"]["sdr_doc_present"] = val
    run("governance " + repr(val), x, aa)
for desc in (
    "Time decay with a 7-day half-life, chosen to favor recent touchpoints.",
    "Time decay attribution with a 7-day half-life, chosen to favor recent touchpoints.",
):
    x = deepcopy(c)
    x["metrics"] = [
        {
            "id": "metrics/revenue",
            "name": "Revenue",
            "description": desc,
            "tags": ["business"],
            "attributionSetting": {
                "enabled": True,
                "attributionModel": {
                    "func": "allocation-timeDecay",
                    "context": "visitors",
                    "halfLifeNumPeriods": 7,
                    "halfLifeGranularity": "day",
                },
            },
        }
    ]
    run(desc, x, cja)
for flag in (False, "false"):
    x = deepcopy(c)
    x["dimensions"] = [
        {
            "id": "variables/x",
            "name": "X",
            "description": "Dimension",
            "tags": ["business"],
            "persistenceSetting": {
                "enabled": flag,
                "allocationModel": {"expiration": {"granularity": "day", "numPeriods": 91}},
            },
        }
    ]
    run("persistence " + repr(flag), x, cja)
s1 = {
    "id": "s1",
    "name": "S1",
    "description": "Cycle",
    "definition": {"func": "segment-ref", "id": "s1"},
}
s2 = {
    "id": "s1",
    "name": "S1b",
    "description": "No cycle",
    "definition": {"func": "container", "context": "hits", "pred": {"func": "true"}},
}
for segs in ([s1, s2], [s2, s1]):
    x = deepcopy(a)
    x["segments"] = segs
    run("duplicate ID " + str([s["name"] for s in segs]), x, aa)
