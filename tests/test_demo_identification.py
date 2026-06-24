"""Pin the three identification demo cases (scripts/run_demo_identification.py).

These cases are the spine of the Themis demo — backdoor / front-door / bow
arc walking the full identification spectrum. They are self-asserting in the
script (each carries its expected verdict), so this test just drives every
case and confirms it still reproduces it. If the identification engine,
verifier, or data-gap classifier drifts, the demo breaks here loudly rather
than during a live recording.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "run_demo_identification.py"
)
_spec = importlib.util.spec_from_file_location("run_demo_identification", _SCRIPT)
demo = importlib.util.module_from_spec(_spec)
# Register before exec so the frozen dataclasses can resolve their module
# (Python 3.13's dataclass machinery looks the module up in sys.modules).
sys.modules[_spec.name] = demo
_spec.loader.exec_module(demo)


@pytest.mark.parametrize("case", demo.CASES, ids=lambda c: c.name)
def test_demo_case_reproduces_expected_verdict(case):
    report = demo.run_case(case)
    assert report.status == "PASS", (
        f"{case.name} regressed:\n  " + "\n  ".join(report.failures)
    )


def test_demo_main_exits_zero():
    assert demo.main(["--json"]) == 0
