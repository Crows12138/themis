"""The browser's source, read by the one reader that understands it.

Everything this suite holds the browser to, it holds by parsing TypeScript
with Python: the vocabularies restated from the kernel, the accounting of
what the envelope can carry, the order two sections render in. Those rules
are about what the source SAYS, and a regex is enough for them.

Nothing had ever asked whether it COMPILES. Three errors were sitting on
HEAD when this module was written, and the interesting one was not a typo:
``bootstrapDraws`` requires ``kind``, ``requested`` and ``used``, and the
browser's hand-written mirror of that shape had all three optional — so a
call site that used the guarantee the kernel actually gives was a type
error, and the only ways to silence it were to invent a default the kernel
can never produce or to leave it there. It was left there, because nothing
ran the compiler.

A regex cannot be taught to find that and does not need to be. The
compiler already knows; what was missing is somebody asking it.

Where the toolchain is absent the first two skip, and the third does not:
the shipped bundle is built by ``pnpm build``, so what guarantees the
compiler runs on a machine that is not this one is that ``build`` still
begins with it.
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
FRONTEND = REPO / "themis" / "web" / "frontend"
TSC = FRONTEND / "node_modules" / "typescript" / "bin" / "tsc"
PACKAGE = FRONTEND / "package.json"

#: Where the counterexample goes: beside ``src`` rather than in it. Every
#: other rule about this surface scans ``src`` for TypeScript, and a suite
#: running eight workers would otherwise let one of them read a file another
#: put there to be refused.
PROBE_DIR = FRONTEND / "type_gate_probe"
PROBE = PROBE_DIR / "probe.ts"
PROBE_CONFIG = FRONTEND / "tsconfig.type-gate-probe.json"

#: Both mistakes that were on HEAD, in one file: a type imported and never
#: used, and a value read off something that may not be there. Written as a
#: pair because what makes the compiler catch them is two different options,
#: and a counterexample carrying one of them would leave the other's option
#: free to be turned off without a single test noticing.
PROBE_SOURCE = """\
// Written by tests/test_the_browser_s_source_is_read_by_a_compiler.py and
// deleted by it. If you are reading this in a working tree, that run died
// between the two; delete it and this config beside it.
import type { Band, BootstrapDraws } from '../src/types'

export function draws(b: BootstrapDraws | undefined): number {
  return b.used
}
"""

#: ``files`` rather than ``include``: the compiler's globs skip a directory
#: whose name starts with a dot, and a config that reaches no file at all
#: fails in a way that reads exactly like the failure this counterexample
#: is here to produce.
PROBE_CONFIG_SOURCE = """\
{
  "extends": "./tsconfig.app.json",
  "files": ["./type_gate_probe/probe.ts"]
}
"""


def _toolchain() -> str | None:
    """Why the compiler cannot be run here, or None."""
    if shutil.which("node") is None:
        return "node is not on PATH"
    if not TSC.exists():
        return f"{TSC.relative_to(REPO)} is missing; run pnpm install"
    return None


def _compile(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", str(TSC), *args],
        cwd=FRONTEND,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )


def test_the_browser_s_source_type_checks():
    """The gate. It runs the project's own build, forced.

    ``--force`` rather than the incremental default: the build info file it
    would otherwise trust is written by whoever ran the compiler last, and a
    check that can be told there is nothing to do is a check that passes for
    a reason unrelated to the source.
    """
    if reason := _toolchain():
        pytest.skip(reason)
    done = _compile("-b", "--force")
    assert done.returncode == 0, (
        "the browser's TypeScript does not compile:\n"
        + (done.stdout or "") + (done.stderr or "")
    )


def test_a_type_error_in_the_browser_s_source_would_be_refused():
    """The counterexample, compiled against this project's own options.

    The config it runs under extends the one the build uses and replaces
    only the file list, so what refuses these two lines is the same
    ``noUnusedLocals`` and the same strict null checking that the gate above
    runs under. Asserting on what the compiler SAYS rather than on the error
    numbers: a code is a fact about a compiler version, and the two mistakes
    have to keep being caught across those.
    """
    if reason := _toolchain():
        pytest.skip(reason)
    PROBE_DIR.mkdir(exist_ok=True)
    try:
        PROBE.write_text(PROBE_SOURCE, encoding="utf-8")
        PROBE_CONFIG.write_text(PROBE_CONFIG_SOURCE, encoding="utf-8")
        done = _compile("-p", PROBE_CONFIG.name)
    finally:
        shutil.rmtree(PROBE_DIR, ignore_errors=True)
        PROBE_CONFIG.unlink(missing_ok=True)
    said = (done.stdout or "") + (done.stderr or "")
    assert done.returncode != 0, f"the compiler accepted this:\n{PROBE_SOURCE}"
    assert "probe.ts" in said, said
    assert "Band" in said, f"the unused import went unreported:\n{said}"
    assert "undefined" in said, f"the unguarded read went unreported:\n{said}"


def test_the_build_that_ships_runs_the_compiler_first():
    """What holds where the two above skip.

    ``dist`` is the artifact and is not checked in, so ``pnpm build`` is the
    one place the compiler is guaranteed to run before anything reaches a
    reader. Before the bundler and not after: the bundler erases types
    without reading them, so a build in the other order ships whatever the
    compiler would have refused.
    """
    build = json.loads(PACKAGE.read_text(encoding="utf-8"))["scripts"]["build"]
    assert "tsc" in build, (
        f"the build script is {build!r} and no longer type-checks; the "
        f"bundler strips types without checking them"
    )
    assert build.index("tsc") < build.index("vite build"), (
        f"the build script is {build!r}; the compiler has to run before the "
        f"bundle is written, not after it has shipped"
    )
