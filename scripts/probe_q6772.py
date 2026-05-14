"""Probe Q6772 — kernel behavior on observational conditional theta."""
import json
import themis

program = {
    "version": "0.1",
    "domain": {"objects": [{"kind": "object", "name": "p"}]},
    "statements": [
        {"kind": "variable", "predicate": "talent", "domain": [True, False]},
        {"kind": "variable", "predicate": "effort", "domain": [True, False]},
        {"kind": "variable", "predicate": "accepted", "domain": [True, False]},
        {"kind": "cause",
         "from": {"predicate": "talent",
                  "args": [{"type": "const", "name": "p"}]},
         "to": {"predicate": "accepted",
                "args": [{"type": "const", "name": "p"}]}},
        {"kind": "cause",
         "from": {"predicate": "effort",
                  "args": [{"type": "const", "name": "p"}]},
         "to": {"predicate": "accepted",
                "args": [{"type": "const", "name": "p"}]}},
        {"kind": "probability",
         "provenance": "observational",
         "target": {"atom": {"predicate": "effort",
                             "args": [{"type": "const", "name": "p"}]},
                    "value": True},
         "given": [{"atom": {"predicate": "talent",
                             "args": [{"type": "const", "name": "p"}]},
                    "value": False},
                   {"atom": {"predicate": "accepted",
                             "args": [{"type": "const", "name": "p"}]},
                    "value": False}],
         "value": 1.00},
        {"kind": "probability",
         "provenance": "observational",
         "target": {"atom": {"predicate": "effort",
                             "args": [{"type": "const", "name": "p"}]},
                    "value": True},
         "given": [{"atom": {"predicate": "talent",
                             "args": [{"type": "const", "name": "p"}]},
                    "value": False},
                   {"atom": {"predicate": "accepted",
                             "args": [{"type": "const", "name": "p"}]},
                    "value": True}],
         "value": 0.94},
        {"kind": "probability",
         "provenance": "observational",
         "target": {"atom": {"predicate": "effort",
                             "args": [{"type": "const", "name": "p"}]},
                    "value": True},
         "given": [{"atom": {"predicate": "talent",
                             "args": [{"type": "const", "name": "p"}]},
                    "value": True},
                   {"atom": {"predicate": "accepted",
                             "args": [{"type": "const", "name": "p"}]},
                    "value": False}],
         "value": 0.98},
        {"kind": "probability",
         "provenance": "observational",
         "target": {"atom": {"predicate": "effort",
                             "args": [{"type": "const", "name": "p"}]},
                    "value": True},
         "given": [{"atom": {"predicate": "talent",
                             "args": [{"type": "const", "name": "p"}]},
                    "value": True},
                   {"atom": {"predicate": "accepted",
                             "args": [{"type": "const", "name": "p"}]},
                    "value": True}],
         "value": 0.92},
        {"kind": "query", "id": "q", "query": {
            "kind": "probability",
            "target": {"atom": {"predicate": "effort",
                                "args": [{"type": "const", "name": "p"}]},
                       "value": True},
            "given": [{"atom": {"predicate": "accepted",
                                "args": [{"type": "const", "name": "p"}]},
                       "value": True},
                      {"atom": {"predicate": "talent",
                                "args": [{"type": "const", "name": "p"}]},
                       "value": True}],
        }},
    ],
}

out = themis.run(program)
r = out["results"][0]
print("status:", r.get("status"))
print("numeric_solved:", r.get("numeric_solved"))
if r.get("missing_information"):
    print("missing_information:")
    print(json.dumps(r["missing_information"][:3], indent=2, default=str))
for step in r.get("derivation", {}).get("steps", []) or []:
    if step.get("rule") == "numeric_result":
        print("numeric_result:", step.get("output"))
