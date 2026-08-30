"""Workflow utilities built on top of runtime + output.

Unlike runtime / input / oracle / output — each of which has a single
responsibility in the dispatch pipeline — workflow modules coordinate
multiple passes to help a user close an investigation loop.

Modules:

- ``bundle`` — the envelope both loops hand work back in: a version, a
  kind, and one list of records under the key that kind names. Owns the
  one check of it, the one exception class it raises, and the words that
  say what was wrong. Each loop below keeps only what is its own, which
  for a patch bundle is the item-by-item check no other kind has a
  vocabulary of legal fields for
- ``parameter_fill`` — export missing-parameter skeletons from a run,
  merge user-filled values back into a program, diff before/after
  runs (the Phase 5 fill-back loop)
- ``variable_framing`` — same shape applied to variable declarations:
  extract a framing skeleton from underframed variables, merge a
  filled-in declaration back, support the strict-gate fill-back loop
  used by ``apply_patch_and_run`` (Phase 6 / A3)

These functions compose the existing pieces (scheduler, pusher,
theta_builder, semantic_validator); they never reach into runtime
internals.
"""
