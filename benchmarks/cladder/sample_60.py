"""Stratified sample of 60 CLadder questions for Phase 1b Sonnet run.

20 per rung × 3 rungs. Within each rung, diversify query_types.
Output: samples_60.json (agent-facing, no answer leak) and
samples_60_full.json (with reasoning + formal_form for scoring).
"""
import json
import random
from collections import defaultdict
from pathlib import Path

from datasets import load_dataset

random.seed(42)

d = load_dataset("causalnlp/CLadder", split="full_v1.5_default")
print(f"Loaded {len(d)} CLadder questions")

per_rung = 20
sampled = []
for rung in [1, 2, 3]:
    # Group indices by query_type within this rung
    by_qt = defaultdict(list)
    for i, row in enumerate(d):
        if row["rung"] == rung:
            by_qt[row["query_type"]].append(i)

    # Round-robin across query_types to diversify
    query_types = list(by_qt.keys())
    for qt in query_types:
        random.shuffle(by_qt[qt])

    picked = []
    rr_idx = 0
    while len(picked) < per_rung:
        qt = query_types[rr_idx % len(query_types)]
        if by_qt[qt]:
            picked.append(by_qt[qt].pop())
        rr_idx += 1
        if rr_idx > 1000:
            break
    sampled.extend(picked[:per_rung])

# Don't double-include the 6-question dry run set (we want fresh data
# for Phase 1b, distinct from the questions we already analyzed).
dry_run_ids = {8706, 6772, 7847, 24227, 9864, 18357}
sampled = [i for i in sampled if d[i]["id"] not in dry_run_ids]

# If we lost any to overlap, top up
while len(sampled) < 60:
    # Pick any random row not already in sampled and not in dry run
    idx = random.randrange(len(d))
    if idx not in sampled and d[idx]["id"] not in dry_run_ids:
        sampled.append(idx)

sampled = sampled[:60]
print(f"Sampled {len(sampled)} questions")

# Summary
from collections import Counter
rung_counts = Counter(d[i]["rung"] for i in sampled)
qt_counts = Counter(d[i]["query_type"] for i in sampled)
print("rung distribution:", dict(rung_counts))
print("query_type distribution:", dict(qt_counts))

agent_payload = [
    {
        "id": d[i]["id"],
        "rung": d[i]["rung"],
        "query_type": d[i]["query_type"],
        "graph_id": d[i]["graph_id"],
        "prompt": d[i]["prompt"],
        "label": d[i]["label"],
    }
    for i in sampled
]
full_payload = [
    {**a,
     "reasoning": d[i]["reasoning"],
     "formal_form": d[i]["formal_form"]}
    for a, i in zip(agent_payload, sampled)
]

out_dir = Path(__file__).resolve().parent
(out_dir / "samples_60.json").write_text(
    json.dumps(agent_payload, indent=2, ensure_ascii=False),
    encoding="utf-8",
)
(out_dir / "samples_60_full.json").write_text(
    json.dumps(full_payload, indent=2, ensure_ascii=False),
    encoding="utf-8",
)
print("Wrote:", out_dir / "samples_60.json")
