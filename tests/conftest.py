"""How this suite is distributed, and why not by file.

Two facts pull against each other. Several modules build something
expensive once and share it across their tests, so splitting a module
across workers pays for that thing again on every worker — which is why
the documented run has always been ``--dist loadfile``. And one module is
a census: one walk over every row of the answer corpus, every public door
and every kind of lie about every leaf. Measured back to back on six
workers, the whole suite is 30m40s and the suite minus that one file is
8m51s — seventy-one per cent of the run is one file, because under
loadfile it is one worker's work while the others finish and wait. It
grows every time the corpus does, and paying for it by sweeping fewer rows
would narrow the instrument.

So the suite is distributed by GROUP, and the group is the module —
which is what loadfile did — except where a module says otherwise. A
module opts out by declaring ``SPREAD_ACROSS_WORKERS = True``, because
whether a module's tests share something expensive is a fact about that
module, and a list of exceptions kept here would be a list standing where
a criterion belongs.

Run it as ``-n <k> --dist loadgroup``. Under ``--dist loadfile`` the marks
are ignored and the arrangement is exactly what it was before.
"""
import pytest


def pytest_collection_modifyitems(session, config, items):
    for item in items:
        module = getattr(item, "module", None)
        if getattr(module, "SPREAD_ACROSS_WORKERS", False):
            continue
        name = (module.__name__ if module is not None
                else item.nodeid.split("::")[0])
        item.add_marker(pytest.mark.xdist_group(name))
