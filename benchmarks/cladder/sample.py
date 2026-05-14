"""Sample CLadder questions stratified by rung for the dry run.

Picks 2 questions per rung (Pearl's 3-rung causal hierarchy), saved as
``samples.json``. The format is what the agent-runner consumes:

    {
      "id": <cladder id>,
      "rung": 1|2|3,
      "query_type": "marginal|ate|nde|...",
      "graph_id": "mediation|fork|chain|...",
      "prompt": <cladder prompt verbatim>,
      "label": "yes"|"no",
    }

We keep ``reasoning`` and ``formal_form`` out of the agent-facing payload
(they leak the answer). They're preserved separately in ``samples_full.json``
for scoring / debugging.
"""
import json
import random
from pathlib import Path

from datasets import load_dataset

random.seed(42)

d = load_dataset("causalnlp/CLadder", split="full_v1.5_default")
print(f"Loaded {len(d)} CLadder questions")

# Stratified sample: 2 per rung. Within each rung, pick diverse query_types.
samples_per_rung = 2
sampled = []
for rung in [1, 2, 3]:
    indices = [i for i, row in enumerate(d) if row["rung"] == rung]
    random.shuffle(indices)
    # Try to diversify query_type within the rung
    seen_query_types = set()
    picked = []
    for idx in indices:
        qt = d[idx]["query_type"]
        if qt not in seen_query_types:
            seen_query_types.add(qt)
            picked.append(idx)
        if len(picked) == samples_per_rung:
            break
    # Fallback if not enough diverse types
    if len(picked) < samples_per_rung:
        picked = indices[:samples_per_rung]
    sampled.extend(picked)

print(f"Sampled {len(sampled)} questions")
for idx in sampled:
    print(
        f"  id={d[idx]['id']:>5}  rung={d[idx]['rung']}  "
        f"query_type={d[idx]['query_type']:<20}  "
        f"graph={d[idx]['graph_id']}  label={d[idx]['label']}"
    )

# Agent-facing payload (no answer leaks)
agent_payload = [
    {
        "id": d[idx]["id"],
        "rung": d[idx]["rung"],
        "query_type": d[idx]["query_type"],
        "graph_id": d[idx]["graph_id"],
        "prompt": d[idx]["prompt"],
        "label": d[idx]["label"],
    }
    for idx in sampled
]

# Full payload (for scoring / debugging)
full_payload = [
    {
        "id": d[idx]["id"],
        "rung": d[idx]["rung"],
        "query_type": d[idx]["query_type"],
        "graph_id": d[idx]["graph_id"],
        "prompt": d[idx]["prompt"],
        "label": d[idx]["label"],
        "reasoning": d[idx]["reasoning"],
        "formal_form": d[idx]["formal_form"],
    }
    for idx in sampled
]

out_dir = Path(__file__).resolve().parent
(out_dir / "samples.json").write_text(
    json.dumps(agent_payload, indent=2, ensure_ascii=False), encoding="utf-8"
)
(out_dir / "samples_full.json").write_text(
    json.dumps(full_payload, indent=2, ensure_ascii=False), encoding="utf-8"
)

print(f"\nWrote: {out_dir / 'samples.json'}")
print(f"       {out_dir / 'samples_full.json'}")
