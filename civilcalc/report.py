"""Plain-text rendering of a Result (no calculation logic here)."""
from __future__ import annotations

from . import units
from .core import Result

WIDTH = 72


def _fmt(o) -> str:
    v = o.value
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (int, float)):
        s = f"{v:,.{o.decimals}f}"
        if o.unit:
            s += f" {o.unit}"
            dual = units.dual_unit(v, o.unit)
            if dual:
                s += f"  ({dual[0]:,.{max(o.decimals, 2)}f} {dual[1]})"
        return s
    return f"{v} {o.unit}".strip()


def render(res: Result) -> str:
    L: list[str] = []
    bar = "=" * WIDTH
    L += [bar, res.title.upper(), bar]
    if res.inputs:
        L.append("INPUTS")
        for label, shown, unit, defaulted in res.inputs:
            tag = "  [default]" if defaulted else ""
            L.append(f"  {label:<44} {shown} {unit}".rstrip() + tag)
    if res.assumptions:
        L.append("\nASSUMPTIONS")
        L += [f"  - {a}" for a in res.assumptions]
    if res.equations:
        L.append("\nGOVERNING EQUATIONS")
        L += [f"  {e}" for e in res.equations]
    L.append("\nRESULTS")
    for o in res.outputs:
        mark = "*" if o.primary else " "
        L.append(f" {mark}{o.label:<44} {_fmt(o)}" + (f"   <- {o.note}" if o.note else ""))
    if res.checks:
        L.append("\nCHECKS")
        for label, ok, detail in res.checks:
            L.append(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" - {detail}" if detail else ""))
    if res.warnings:
        L.append("\nWARNINGS")
        L += [f"  ! {w}" for w in res.warnings]
    if res.references:
        L.append("\nREFERENCES")
        L += [f"  {r}" for r in res.references]
    L.append("-" * WIDTH)
    L.append("Results are for preliminary/verification use; the engineer of record is responsible for design.")
    return "\n".join(L)
