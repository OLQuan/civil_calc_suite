"""Unit registry and conversion utility.

Every calculation module receives its inputs in the unit declared on each
``Param`` (mostly SI: m, mm, kN, kPa, MPa, kg, m3/s ...).  Users may type
any recognised unit after a number ("30 ft", "4000 psi", "2%", "45-30-15")
and ``parse_quantity`` converts it for them, so mixed-unit input is safe.

Conversion model: base = (value + offset) * factor   (offset only for temperature)
Base units: m, m2, m3, N, Pa, N-m, N/m, N/m3, kg, kg/m3, m3/s, m/s, rad, s, K,
            W, m2/s, m4, ratio (1.0).
"""
from __future__ import annotations

import math
import re

__all__ = [
    "UnitError", "convert", "dimension", "canonical", "parse_quantity",
    "parse_list", "known_units", "dual_unit", "is_known", "G", "GAMMA_W",
]

G = 9.80665          # m/s2, standard gravity
GAMMA_W = 9.81       # kN/m3, unit weight of fresh water (rounded, common practice)


class UnitError(ValueError):
    """Unknown unit or incompatible dimensions."""


# dimension -> list of ((display name, alias, alias...), factor_to_base[, offset])
_DEFS: dict[str, list] = {
    "length": [
        (("m", "meter", "meters", "metre", "metres"), 1.0),
        (("mm",), 1e-3), (("cm",), 1e-2), (("km",), 1e3), (("um",), 1e-6),
        (("in", "inch", "inches", '"'), 0.0254),
        (("ft", "foot", "feet", "'"), 0.3048),
        (("yd", "yard", "yards"), 0.9144),
        (("mi", "mile", "miles"), 1609.344),
    ],
    "area": [
        (("m2", "sqm"), 1.0), (("mm2",), 1e-6), (("cm2",), 1e-4), (("km2",), 1e6),
        (("ha", "hectare"), 1e4), (("acre", "acres"), 4046.8564224),
        (("ft2", "sqft"), 0.09290304), (("in2", "sqin"), 0.00064516),
        (("yd2", "sqyd"), 0.83612736),
    ],
    "volume": [
        (("m3", "cum"), 1.0), (("mm3",), 1e-9), (("cm3", "cc"), 1e-6),
        (("L", "lit", "liter", "litre", "liters", "litres"), 1e-3), (("mL",), 1e-6),
        (("ft3", "cuft"), 0.028316846592), (("yd3", "cuyd"), 0.764554857984),
        (("in3", "cuin"), 1.6387064e-5),
        (("gal", "usgal"), 0.003785411784), (("igal",), 0.00454609),
    ],
    "force": [
        (("N", "newton"), 1.0), (("kN", "kilonewton"), 1e3), (("MN",), 1e6),
        (("lbf",), 4.4482216152605), (("kip", "kips"), 4448.2216152605),
        (("kgf",), 9.80665), (("tf",), 9806.65), (("tonf",), 8896.443230521),
    ],
    "pressure": [
        (("Pa",), 1.0), (("kPa",), 1e3), (("MPa", "N/mm2"), 1e6), (("GPa",), 1e9),
        (("psi",), 6894.757293168), (("ksi",), 6894757.293168),
        (("psf",), 47.88025898), (("ksf",), 47880.25898), (("tsf",), 95760.518),
        (("bar",), 1e5), (("atm",), 101325.0),
        (("kgf/cm2",), 98066.5), (("kgf/m2",), 9.80665), (("tf/m2",), 9806.65),
    ],
    "moment": [
        (("N-m", "nmeter"), 1.0), (("kN-m", "knm"), 1e3), (("N-mm",), 1e-3),
        (("kN-mm",), 1.0), (("MN-m",), 1e6),
        (("kip-ft", "kipft", "k-ft"), 1355.8179483314),
        (("kip-in", "kipin", "k-in"), 112.98482902762),
        (("lbf-ft", "lb-ft"), 1.3558179483314), (("lbf-in", "lb-in"), 0.11298482902762),
        (("kgf-m",), 9.80665), (("tf-m",), 9806.65),
    ],
    "line_load": [
        (("N/m",), 1.0), (("kN/m",), 1e3), (("N/mm",), 1e3),
        (("kip/ft", "klf"), 14593.90294), (("plf", "lbf/ft"), 14.59390294),
        (("lbf/in",), 175.1268369), (("kgf/m",), 9.80665), (("tf/m",), 9806.65),
    ],
    "unit_weight": [
        (("N/m3",), 1.0), (("kN/m3",), 1e3), (("pcf", "lbf/ft3"), 157.0874606),
        (("kip/ft3",), 157087.4606), (("lbf/in3",), 271447.1),
        (("kgf/m3",), 9.80665), (("tf/m3",), 9806.65),
    ],
    "density": [
        (("kg/m3",), 1.0), (("t/m3", "kg/L", "g/cm3", "g/cc"), 1000.0),
        (("lb/ft3",), 16.01846337), (("lb/in3",), 27679.9047), (("lb/yd3",), 0.593276421),
    ],
    "mass": [
        (("kg",), 1.0), (("g",), 1e-3), (("t", "tonne", "tonnes", "mt"), 1000.0),
        (("lb", "lbs"), 0.45359237), (("ton", "shortton"), 907.18474),
        (("lton", "longton"), 1016.0469088),
    ],
    "flow": [
        (("m3/s", "cms"), 1.0), (("L/s", "lps"), 1e-3), (("m3/h", "m3/hr"), 1 / 3600),
        (("m3/day", "m3/d"), 1 / 86400), (("L/min", "lpm"), 1e-3 / 60),
        (("ft3/s", "cfs"), 0.028316846592), (("gpm",), 6.30901964e-5),
        (("mgd",), 0.043812636), (("MLD",), 0.011574074),
    ],
    "velocity": [
        (("m/s",), 1.0), (("mm/s",), 1e-3), (("cm/s",), 1e-2),
        (("km/h", "kph", "kmh"), 1 / 3.6), (("mph",), 0.44704), (("ft/s", "fps"), 0.3048),
        (("m/day", "m/d"), 1 / 86400), (("ft/day", "ft/d"), 0.3048 / 86400),
        (("m/h", "m/hr"), 1 / 3600), (("mm/h", "mm/hr"), 1e-3 / 3600),
        (("in/h", "in/hr"), 0.0254 / 3600),
    ],
    "angle": [
        (("rad", "radian", "radians"), 1.0),
        (("deg", "degree", "degrees"), math.pi / 180), (("grad", "gon"), math.pi / 200),
    ],
    "time": [
        (("s", "sec"), 1.0), (("min", "minute", "minutes"), 60.0),
        (("h", "hr", "hour", "hours"), 3600.0), (("day", "days", "d"), 86400.0),
        (("week", "weeks"), 604800.0), (("yr", "year", "years"), 31557600.0),
    ],
    "temperature": [
        (("degC", "c", "celsius"), 1.0, 273.15),
        (("degF", "f", "fahrenheit"), 5 / 9, 459.67),
        (("K", "kelvin"), 1.0, 0.0),
    ],
    "ratio": [
        (("-", "ratio", "none"), 1.0), (("%", "percent"), 0.01),
    ],
    "power": [
        (("W",), 1.0), (("kW",), 1e3), (("MW",), 1e6), (("hp",), 745.69987158),
    ],
    "diffusivity": [
        (("m2/s",), 1.0), (("cm2/s", "St"), 1e-4), (("mm2/s",), 1e-6),
        (("m2/yr",), 1 / 31557600.0), (("m2/day", "m2/d"), 1 / 86400.0),
    ],
    "second_moment": [
        (("m4",), 1.0), (("mm4",), 1e-12), (("cm4",), 1e-8), (("in4",), 4.162314256e-7),
    ],
}

# alias(normalised) -> (dimension, factor, offset, display name)
_LOOKUP: dict[str, tuple] = {}


def _norm(u: str) -> str:
    u = u.strip().lower()
    for a, b in (("²", "2"), ("³", "3"), ("⁴", "4"), ("^", ""),
                 ("·", "-"), ("*", "-"), ("×", "-"), (" ", ""),
                 ("°", "deg"), (".", "-")):
        u = u.replace(a, b)
    return u


def _build() -> None:
    for dim, entries in _DEFS.items():
        for e in entries:
            names, factor = e[0], e[1]
            offset = e[2] if len(e) > 2 else 0.0
            for name in names:
                key = _norm(name)
                if key in _LOOKUP and _LOOKUP[key][0] != dim:
                    raise RuntimeError(f"unit alias clash: {name!r}")
                _LOOKUP[key] = (dim, factor, offset, names[0])


_build()
_LOOKUP[""] = ("ratio", 1.0, 0.0, "-")


def _get(unit: str) -> tuple:
    try:
        return _LOOKUP[_norm(unit)]
    except KeyError:
        raise UnitError(
            f"Unknown unit '{unit}'. Type '?' at a prompt (or run 'units' in the CLI) "
            f"to list recognised units.") from None


def is_known(unit: str) -> bool:
    """True when ``unit`` is a registered unit (labels such as 'ESAL' or 'persons' are not)."""
    return _norm(unit) in _LOOKUP


def dimension(unit: str) -> str:
    return _get(unit)[0]


def canonical(unit: str) -> str:
    return _get(unit)[3]


def convert(value: float, from_unit: str, to_unit: str) -> float:
    """Convert ``value`` between two units of the same dimension."""
    d1, f1, o1, _ = _get(from_unit)
    d2, f2, o2, _ = _get(to_unit)
    if d1 != d2:
        raise UnitError(f"Cannot convert {from_unit} ({d1}) to {to_unit} ({d2}).")
    base = (value + o1) * f1
    return base / f2 - o2


# --------------------------------------------------------------------------
# Parsing of user text
# --------------------------------------------------------------------------
_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
_RE_QTY = re.compile(rf"^\s*({_NUM})\s*(.*?)\s*$")
_RE_DMS = re.compile(
    r"^\s*([+-])?\s*(\d+(?:\.\d+)?)\s*(?:°|d|-|:|\s)\s*(\d+(?:\.\d+)?)\s*"
    r"(?:'|m|-|:|\s)?\s*(?:(\d+(?:\.\d+)?)\s*(?:\"|s)?)?\s*$", re.IGNORECASE)
_RE_FTIN = re.compile(
    r"^\s*(\d+(?:\.\d+)?)\s*(?:'|ft)\s*-?\s*(\d+(?:\.\d+)?)\s*(?:\"|in)?\s*$", re.IGNORECASE)


def _parse_dms(s: str) -> float | None:
    m = _RE_DMS.match(s)
    if not m:
        return None
    sign = -1.0 if m.group(1) == "-" else 1.0
    deg, mins, secs = float(m.group(2)), float(m.group(3)), float(m.group(4) or 0.0)
    if mins >= 60 or secs >= 60:
        raise UnitError(f"Minutes and seconds must be below 60 in '{s}'.")
    return sign * (deg + mins / 60.0 + secs / 3600.0)


def parse_quantity(text, target_unit: str) -> float:
    """Return the numeric value of ``text`` expressed in ``target_unit``.

    A bare number is taken to already be in ``target_unit``.  Accepts a unit
    suffix ("25 ft", "4000 psi", "2 %"), feet-inches ("5'6\\""), and, for angle
    targets, degrees-minutes-seconds ("45-30-15", "45d30m15s", "45:30:15").
    """
    if isinstance(text, (int, float)):
        return float(text)
    s = str(text).strip()
    if not s:
        raise UnitError("Empty value.")
    tdim = dimension(target_unit)
    if tdim == "angle":
        dms = _parse_dms(s)
        if dms is not None:
            return convert(dms, "deg", target_unit)
    if tdim == "length":
        m = _RE_FTIN.match(s)
        if m:
            return convert(float(m.group(1)) + float(m.group(2)) / 12.0, "ft", target_unit)
    s = re.sub(r"(?<=\d),(?=\d{3}\b)", "", s)          # 4,000 -> 4000
    m = _RE_QTY.match(s)
    if not m:
        raise UnitError(f"'{text}' is not a number (examples: 30, 30 MPa, 4000 psi).")
    val = float(m.group(1))
    unit = m.group(2)
    if not unit:
        return val
    return convert(val, unit, target_unit)


def parse_list(text, target_unit: str) -> list[float]:
    """Parse 'a, b, c' / 'a; b; c' / one-per-line into a list in ``target_unit``."""
    if isinstance(text, (list, tuple)):
        return [parse_quantity(t, target_unit) for t in text]
    parts = [p for p in re.split(r"[;,\n]+", str(text)) if p.strip()]
    return [parse_quantity(p, target_unit) for p in parts]


def known_units() -> dict[str, list[str]]:
    """dimension -> display names, for help screens."""
    return {dim: [e[0][0] for e in entries] for dim, entries in _DEFS.items()}


# SI/metric unit -> imperial companion, used for dual-unit display
_DUAL = {
    "m": "ft", "mm": "in", "km": "mi", "m2": "ft2", "m3": "yd3", "ha": "acre",
    "kN": "kip", "kPa": "psf", "MPa": "psi", "kN/m": "kip/ft", "kN-m": "kip-ft",
    "kN/m3": "pcf", "kg": "lb", "t": "ton", "kg/m3": "lb/ft3", "m3/s": "cfs",
    "L/s": "gpm", "m/s": "ft/s", "mm/h": "in/h", "kW": "hp", "mm4": "in4",
    "km/h": "mph", "degC": "degF", "mm2": "in2", "mm3": "in3",
}


def dual_unit(value: float, unit: str):
    """Return (value, unit) in the imperial companion unit, or None."""
    other = _DUAL.get(unit)
    if other is None:
        return None
    try:
        return convert(value, unit, other), other
    except UnitError:
        return None
