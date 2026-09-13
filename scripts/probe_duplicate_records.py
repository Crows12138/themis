"""Does anything refuse a record that is already there?

The census can only replace a leaf in place — ``_tamper`` does
``node[path[-1]] = value`` and has no append — so a lie that needs two
records to show is outside what it can say. Duplicates are that class.

The instrument here is the census's own: the same corpus, the same
``_reading_doors`` (a door that refuses the honest envelope witnesses
nothing), the same ``_refuses``. Only the mutation differs — one element
of a list is appended to that list a second time, byte for byte.

    python scripts/probe_duplicate_records.py <out.json> [--limit N]

Runs long: every question that nothing refuses costs a call to EVERY
reading door, because there is no refusal to short-circuit on. Progress
and partial results are written as it goes.
"""
from __future__ import annotations

import copy
import json
import pathlib
import sys
import time
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests import (                                             # noqa: E402
    test_every_answer_shape_is_asked_the_same_question as census)

OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "dup_probe.json")
LIMIT = None
if "--limit" in sys.argv:
    LIMIT = int(sys.argv[sys.argv.index("--limit") + 1])


def lists_in(node, path=()):
    """Every list in the envelope, with its path. Non-empty only.

    An empty list has nothing to duplicate, so it is not a question this
    probe can put; counting it would inflate the denominator with rows
    where the mutation does not exist.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            yield from lists_in(value, path + (key,))
    elif isinstance(node, list):
        if node:
            yield path, node
        for index, value in enumerate(node):
            yield from lists_in(value, path + (index,))


def with_one_more(result, path):
    """The envelope with the last element of that list repeated."""
    bent = copy.deepcopy(result)
    node = bent
    for step in path:
        node = node[step]
    node.append(copy.deepcopy(node[-1]))
    return bent


def main() -> int:
    rows = sorted(census.SHAPES)
    if LIMIT:
        rows = rows[:LIMIT]
    started = time.time()
    asked = Counter()
    refused = Counter()
    by_door = Counter()
    unread = []
    total = 0

    for row_at, name in enumerate(rows, 1):
        pair = census.SHAPES[name]
        program, result = pair["program"], pair["result"]
        doors = census._reading_doors(program, result)
        if not doors:
            unread.append(name)
            continue
        for path, _node in lists_in(result):
            shape = census._shape_of(path)
            asked[shape] += 1
            total += 1
            bent = with_one_more(result, path)
            for door in doors:
                if census._refuses(door, program, bent):
                    refused[shape] += 1
                    by_door[door] += 1
                    break
        if row_at % 10 == 0 or row_at == len(rows):
            spent = time.time() - started
            print(f"  {row_at}/{len(rows)} 行  提问 {total}  "
                  f"被拒 {sum(refused.values())}  "
                  f"{spent / 60:.1f} 分", flush=True)
            OUT.write_text(json.dumps({
                "rows_done": row_at, "rows_total": len(rows),
                "asked_total": total, "refused_total": sum(refused.values()),
                "seconds": round(spent, 1),
                "unread_rows": unread,
                "asked": dict(asked.most_common()),
                "refused": dict(refused.most_common()),
                "by_door": dict(by_door.most_common()),
            }, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n列表实例 {total}  被拒 {sum(refused.values())}  "
          f"没有门读的行 {len(unread)}")
    print("\n最宽的 12 处（都没被拒的话，就是 12 个从没被问过的地方）：")
    for shape, count in asked.most_common(12):
        print(f"  {count:>5}  {shape}  (被拒 {refused[shape]})")
    if refused:
        print("\n谁签的字：", dict(by_door.most_common()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
