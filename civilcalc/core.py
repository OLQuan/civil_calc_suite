"""Core engine: parameter validation, results, and the calculation/discipline containers.

Calculation functions never talk to the user.  They receive validated values
(already converted to the unit declared on each ``Param``) and return a
``Result``.  The CLI (cli.py) and the tests both drive them through
``Calculation.run``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

from . import units


class CivilCalcError(Exception):
    """Base class for all errors raised by the suite."""


class InputError(CivilCalcError):
    """The user's input is missing, malformed, or physically impossible."""


class CalcError(CivilCalcError):
    """Inputs are individually valid but the calculation cannot proceed."""


def need(condition: bool, message: str) -> None:
    """Cross-field validation helper: raise InputError when ``condition`` is False."""
    if not condition:
        raise InputError(message)


def fnum(v: float, sig: int = 6) -> str:
    return f"{v:.{sig}g}"


# --------------------------------------------------------------------------
# Parameters
# --------------------------------------------------------------------------
@dataclass
class Param:
    """One input of a calculation.

    unit      unit in which the calculation function receives the value
              ('' for dimensionless numbers).  Users may type another unit.
    kind      float | int | choice | text | floatlist | textlist
    default   used when the user leaves the field blank; shown in the report
    optional  blank allowed and passed to the function as None
    min/max   HARD limits (non-physical values are rejected)
    typical   (lo, hi) SOFT range; outside it a warning is attached to the result
    choices   list of (value, label) for kind == 'choice'
    """
    key: str
    label: str
    unit: str = ""
    kind: str = "float"
    default: Any = None
    optional: bool = False
    min: float | None = None
    max: float | None = None
    min_exclusive: bool = False
    max_exclusive: bool = False
    typical: tuple[float, float] | None = None
    choices: list[tuple[Any, str]] | None = None
    help: str = ""
    min_items: int = 1

    # ------------------------------------------------------------------
    def _u(self) -> str:
        return f" {self.unit}" if self.unit and self.unit != "-" else ""

    def _tu(self) -> str:
        """Registry unit used for parsing. Pure labels (ESAL, persons, veh/day) parse as dimensionless."""
        return self.unit if self.unit and units.is_known(self.unit) else "-"

    def _strip_label(self, raw: Any) -> Any:
        """Allow the user to type the label itself after a number ('5e6 ESAL')."""
        if isinstance(raw, str) and self.unit and self._tu() == "-" and self.unit != "-":
            s = raw.strip()
            if s.lower().endswith(self.unit.lower()):
                return s[: -len(self.unit)].strip()
        return raw

    def describe_range(self) -> str:
        bits = []
        if self.min is not None:
            bits.append(f"{'>' if self.min_exclusive else '>='} {fnum(self.min)}")
        if self.max is not None:
            bits.append(f"{'<' if self.max_exclusive else '<='} {fnum(self.max)}")
        return ", ".join(bits)

    def _hard(self, v: float) -> None:
        lo, hi = self.min, self.max
        if lo is not None and (v < lo or (self.min_exclusive and v <= lo)):
            word = "greater than" if self.min_exclusive else "at least"
            raise InputError(f"{self.label} must be {word} {fnum(lo)}{self._u()} (you entered {fnum(v)}).")
        if hi is not None and (v > hi or (self.max_exclusive and v >= hi)):
            word = "less than" if self.max_exclusive else "at most"
            raise InputError(f"{self.label} must be {word} {fnum(hi)}{self._u()} (you entered {fnum(v)}).")

    def _soft(self, vals: list[float]) -> list[str]:
        if not self.typical:
            return []
        lo, hi = self.typical
        out = [v for v in vals if v < lo or v > hi]
        if out:
            shown = ", ".join(fnum(v) for v in out[:4])
            return [f"{self.label} = {shown}{self._u()} is outside the typical range "
                    f"{fnum(lo)} to {fnum(hi)}{self._u()}; confirm it is intended."]
        return []

    # ------------------------------------------------------------------
    def parse(self, raw: Any) -> tuple[Any, bool, list[str]]:
        """Return (value, used_default, warnings) or raise InputError."""
        blank = raw is None or (isinstance(raw, str) and not raw.strip())
        if blank:
            if self.default is not None:
                v = self.default
                return v, True, (self._soft([v]) if self.kind in ("float", "int") else [])
            if self.optional:
                return None, False, []
            raise InputError(f"{self.label} is required (no default available).")
        try:
            if self.kind == "float":
                v = self._number(raw)
                return v, False, self._soft([v])
            if self.kind == "int":
                v = self._number(raw)
                if abs(v - round(v)) > 1e-9:
                    raise InputError(f"{self.label} must be a whole number (you entered {fnum(v)}).")
                return int(round(v)), False, self._soft([v])
            if self.kind == "floatlist":
                vals = units.parse_list(self._strip_label(raw), self._tu())
                if len(vals) < self.min_items:
                    raise InputError(f"{self.label} needs at least {self.min_items} value(s), separated by commas.")
                for x in vals:
                    self._finite(x)
                    self._hard(x)
                return vals, False, self._soft(vals)
            if self.kind == "textlist":
                items = [t.strip() for t in str(raw).replace("\n", ";").replace(",", ";").split(";") if t.strip()]
                if len(items) < self.min_items:
                    raise InputError(f"{self.label} needs at least {self.min_items} item(s), separated by commas.")
                return items, False, []
            if self.kind == "choice":
                return self._choice(raw), False, []
            if self.kind == "text":
                return str(raw).strip(), False, []
        except units.UnitError as e:
            raise InputError(f"{self.label}: {e}") from None
        raise CivilCalcError(f"Parameter {self.key}: unknown kind {self.kind!r}")

    def _finite(self, v: float) -> None:
        if not math.isfinite(v):
            raise InputError(f"{self.label} must be a finite number.")

    def _number(self, raw: Any) -> float:
        v = units.parse_quantity(self._strip_label(raw), self._tu())
        self._finite(v)
        self._hard(v)
        return v

    def _choice(self, raw: Any) -> Any:
        choices = self.choices or []
        s = str(raw).strip().lower()
        for val, _label in choices:
            if str(val).lower() == s:
                return val
        if s.isdigit() and 1 <= int(s) <= len(choices):
            return choices[int(s) - 1][0]
        for val, label in choices:
            if label.lower() == s:
                return val
        hits = [val for val, label in choices if label.lower().startswith(s)] if s else []
        if len(hits) == 1:
            return hits[0]
        opts = ", ".join(f"{i}={lab}" for i, (_v, lab) in enumerate(choices, 1))
        raise InputError(f"{self.label}: '{raw}' is not a valid choice. Options: {opts}.")

    def display(self, value: Any) -> str:
        if value is None:
            return "(not given)"
        if self.kind == "choice":
            for val, label in self.choices or []:
                if val == value:
                    return label
        if isinstance(value, list):
            return ", ".join(fnum(x) if isinstance(x, float) else str(x) for x in value)
        if isinstance(value, float):
            return fnum(value, 7)
        return str(value)


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------
@dataclass
class Output:
    key: str
    label: str
    value: Any
    unit: str = ""
    decimals: int = 2
    note: str = ""
    primary: bool = False


class Result:
    """Everything a calculation reports; rendered by report.py."""

    def __init__(self, title: str):
        self.title = title
        self.inputs: list[tuple[str, str, str, bool]] = []   # label, shown value, unit, defaulted
        self.outputs: list[Output] = []
        self.checks: list[tuple[str, bool, str]] = []
        self.equations: list[str] = []
        self.references: list[str] = []
        self.assumptions: list[str] = []
        self.warnings: list[str] = []
        self.sections: list[tuple[str, list[Output]]] = []   # optional named tables

    # builders ---------------------------------------------------------
    def add(self, key, label, value, unit="", decimals=2, note="", primary=False) -> "Result":
        self.outputs.append(Output(key, label, value, unit, decimals, note, primary))
        return self

    def eq(self, text: str) -> "Result":
        self.equations.append(text)
        return self

    def ref(self, text: str) -> "Result":
        if text not in self.references:
            self.references.append(text)
        return self

    def assume(self, text: str) -> "Result":
        self.assumptions.append(text)
        return self

    def warn(self, text: str) -> "Result":
        if text not in self.warnings:
            self.warnings.append(text)
        return self

    def check(self, label: str, ok: bool, detail: str = "") -> bool:
        self.checks.append((label, bool(ok), detail))
        return bool(ok)

    # access -----------------------------------------------------------
    def __getitem__(self, key: str):
        for o in self.outputs:
            if o.key == key:
                return o.value
        raise KeyError(key)

    def get(self, key: str, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "inputs": [{"label": a, "value": b, "unit": c, "default_used": d} for a, b, c, d in self.inputs],
            "outputs": [{"key": o.key, "label": o.label, "value": o.value, "unit": o.unit, "note": o.note}
                        for o in self.outputs],
            "checks": [{"label": a, "passed": b, "detail": c} for a, b, c in self.checks],
            "equations": self.equations, "references": self.references,
            "assumptions": self.assumptions, "warnings": self.warnings,
        }


# --------------------------------------------------------------------------
# Calculation, Discipline, test Case
# --------------------------------------------------------------------------
@dataclass
class Calculation:
    key: str
    name: str
    summary: str
    params: list[Param]
    func: Callable[..., Result]
    standard: str = ""
    discipline: str = ""          # filled in by Discipline

    @property
    def full_id(self) -> str:
        return f"{self.discipline}.{self.key}"

    def prepare(self, raw: dict | None):
        """Validate/convert ``raw`` -> (values, warnings, echo).  Raises InputError listing every problem."""
        raw = dict(raw or {})
        known = {p.key for p in self.params}
        unknown = [k for k in raw if k not in known]
        if unknown:
            raise InputError(f"Unknown input(s): {', '.join(unknown)}. Valid inputs: {', '.join(sorted(known))}.")
        values, warnings, echo, problems = {}, [], [], []
        for p in self.params:
            try:
                v, defaulted, w = p.parse(raw.get(p.key))
            except InputError as e:
                problems.append(str(e))
                continue
            values[p.key] = v
            warnings += w
            echo.append((p.label, p.display(v), p.unit if p.unit != "-" else "", defaulted))
        if problems:
            head = "Input problem:" if len(problems) == 1 else f"{len(problems)} input problems:"
            raise InputError(head + "\n  - " + "\n  - ".join(problems))
        return values, warnings, echo

    def run(self, raw: dict | None = None) -> Result:
        values, warnings, echo = self.prepare(raw)
        res = self.func(**values)
        res.inputs = echo
        for w in warnings:
            res.warn(w)
        for label, shown, unit, defaulted in echo:
            if defaulted:
                res.assume(f"Default used for '{label}': {shown} {unit}".rstrip())
        if self.standard and self.standard not in res.references:
            res.references.insert(0, self.standard)
        return res


@dataclass
class Case:
    """A worked test case with a known answer.

    expect maps output key -> expected value, or (value, relative_tolerance).
    expect_error: substring that must appear in the InputError message.
    """
    calc: str
    inputs: dict
    expect: dict = field(default_factory=dict)
    note: str = ""
    expect_error: str | None = None
    rel: float = 0.005


@dataclass
class Discipline:
    key: str
    name: str
    description: str
    calcs: list[Calculation]
    cases: list[Case] = field(default_factory=list)
    order: int = 100

    def __post_init__(self):
        for c in self.calcs:
            c.discipline = self.key
        keys = [c.key for c in self.calcs]
        if len(keys) != len(set(keys)):
            raise CivilCalcError(f"Duplicate calculation keys in discipline {self.key}")

    def get(self, key: str) -> Calculation:
        for c in self.calcs:
            if c.key == key:
                return c
        raise KeyError(key)
