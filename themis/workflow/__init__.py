"""Workflow utilities built on top of runtime + output.

Unlike runtime / input / oracle / output — each of which has a single
responsibility in the dispatch pipeline — workflow modules coordinate
multiple passes to help a user close an investigation loop.

Modules:

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
