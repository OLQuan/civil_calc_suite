"""Runs every Discipline.cases entry and reports pass/fail.

Each case is run twice: with the inputs as written, and with every value turned
into text - which is exactly what the interactive menu and the command line
send - so the text-parsing path is verified as well as the arithmetic.
"""
from __future__ import annotations

from . import registry
from .core import CivilCalcError, InputError


def _as_text(inputs: dict) -> dict:
    return {k: (v if isinstance(v, str) else str(v)) for k, v in inputs.items()}


def _check(calc, case, inputs) -> str | None:
    """Return None when the case passes, else a failure message."""
    if case.expect_error is not None:
        try:
            calc.run(inputs)
        except InputError as e:
            if case.expect_error.lower() in str(e).lower():
                return None
            return f"wrong error: {e}"
        return f"expected an error containing '{case.expect_error}'"
    res = calc.run(inputs)
    bad = []
    for k, exp in case.expect.items():
        tol = case.rel
        if isinstance(exp, tuple):
            exp, tol = exp
        got = res[k]
        ok = got == exp if isinstance(exp, str) else abs(got - exp) <= tol * max(abs(exp), 1e-9)
        if not ok:
            bad.append(f"{k}: got {got!r}, expected {exp!r}")
    return "; ".join(bad) or None


def run_all(verbose: bool = False) -> int:
    total = failed = 0
    for d in registry.load():
        for case in d.cases:
            tag = f"{d.key}.{case.calc}"
            for mode, inputs in (("native", case.inputs), ("text", _as_text(case.inputs))):
                total += 1
                try:
                    msg = _check(d.get(case.calc), case, inputs)
                except CivilCalcError as e:
                    msg = str(e)
                except Exception as e:     # a programming error inside a calculation
                    msg = f"{type(e).__name__}: {e}"
                if msg:
                    failed += 1
                    print(f"FAIL {tag} [{mode}] ({case.note}): {msg}")
                elif verbose:
                    print(f"ok   {tag} [{mode}]: {case.note}")
    print(f"\n{total - failed}/{total} worked-example checks passed "
          f"({total // 2} cases x native and text input).")
    return 1 if failed else 0
