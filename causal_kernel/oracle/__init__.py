"""Oracle layer: parallel independent implementations used for
differential testing only.

The oracle layer MUST NOT be imported by any runtime, input, or
output module. It reads the same validated Program the runtime
receives, produces comparable results, and hands them to the
differential comparator.

Oracle dependencies (pgmpy, ananke) are development/test-time only
and should be declared separately from production requirements.
"""
