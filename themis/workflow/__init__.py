"""Workflow utilities built on top of runtime + output.

Unlike runtime / input / oracle / output — each of which has a single
responsibility in the dispatch pipeline — workflow modules coordinate
multiple passes to help a user close an investigation loop.

v0.2 contents:

- ``parameter_fill``: export missing-parameter skeletons from a run,
  merge user-filled values back into a program, diff before/after runs.

These functions compose the existing pieces (scheduler, pusher,
theta_builder, semantic_validator); they never reach into runtime
internals.
"""
