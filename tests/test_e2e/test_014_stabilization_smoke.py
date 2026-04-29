"""Guard the 0.14 stabilization smoke chain.

The script is intentionally a user-facing command, but keeping this
test means regular pytest runs will catch breakage in the command as
well as in the underlying run/verify/estimate/KB paths.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "run_014_stabilization_smoke.py"


def _load_smoke_module():
    spec = importlib.util.spec_from_file_location(
        "run_014_stabilization_smoke",
        SCRIPT,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_014_stabilization_smoke_has_no_failures():
    module = _load_smoke_module()
    results = module.run_all()

    names = {result.name for result in results}
    assert names == {
        "dose_response_diagnostic",
        "transport_verify_and_gap",
        "dose_response_estimate_verify",
        "kb_patch_loop",
    }
    failures = [result for result in results if result.status == "FAIL"]
    assert failures == []
