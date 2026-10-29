"""9. Unit Conversions and Utilities."""
from __future__ import annotations

import math

from .. import units
from ..core import Calculation, Case, Discipline, InputError, Param, Result, need


def convert(value, from_unit, to_unit):
    r = Result("Unit conversion")
    try:
        out = units.convert(value, from_unit, to_unit)
    except units.UnitError as e:
        raise InputError(str(e)) from None
    r.eq("value_to = (value_from + offset_from) x factor_from / factor_to - offset_to   (temperature has offsets)")
    r.add("result", f"{value:g} {from_unit}  =", out, to_unit, 6, primary=True)
    r.assume(f"Dimension: {units.dimension(from_unit)}. Factors are exact definitions (e.g. 1 in = 25.4 mm, 1 lbf = 4.4482216 N, "
             "1 US gal = 3.785411784 L); 'ton' = US short ton, 't' = metric tonne.")
    return r


def angle(value):
    r = Result("Angle formats")
    deg = value
    hundredths = round(abs(deg) * 360000)        # whole 0.01" so rounding can never print 60.00"
    d, rest = divmod(hundredths, 360000)
    m, s100 = divmod(rest, 6000)
    sign = "-" if deg < 0 and hundredths else ""
    r.add("deg", "Decimal degrees", deg, "deg", 6, primary=True)
    r.add("dms", "Degrees-minutes-seconds", f"{sign}{d}° {m}' {s100 / 100:.2f}\"", "")
    r.add("rad", "Radians", math.radians(deg), "rad", 6)
    r.add("grad", "Gradians", deg * 10 / 9, "gon", 4)
    r.eq("1 rad = 180/pi deg;  1 gon = 0.9 deg;  1 deg = 60' = 3600\"")
    return r


def slope(mode, value):
    r = Result("Slope conversion")
    if mode == "percent":
        pct = value
    elif mode == "degrees":
        need(value < 90, "Slope angle must be below 90 degrees.")
        pct = math.tan(math.radians(value)) * 100
    else:
        need(value > 0, "Ratio must be positive.")
        pct = 100 / value
    r.eq("grade % = 100 tan(theta) = 100 rise/run;  ratio 1V:nH with n = 100/grade%")
    r.add("pct", "Grade", pct, "%", 3, primary=True)
    r.add("deg", "Angle", math.degrees(math.atan(pct / 100)), "deg", 3)
    r.add("ratio", "1 vertical in H horizontal, H =", 100 / pct if pct else float("inf"), "", 2)
    r.add("mm_m", "Fall per metre", pct * 10, "mm/m", 1)
    return r


MATERIALS = [
    ("plain_concrete", "Plain concrete", 23.5, "23-24"), ("rc", "Reinforced concrete", 24.5, "24-25"),
    ("steel", "Structural steel", 78.5, "77-78.5"), ("brick", "Brick masonry", 18.5, "17-20"),
    ("softwood", "Softwood timber", 5.5, "4-6"), ("hardwood", "Hardwood timber", 8.0, "6-10"),
    ("granite", "Granite", 26.5, "26-28"), ("sand_dry", "Dry sand", 16.0, "15-17"),
    ("clay", "Clay (moist)", 18.5, "16-21"), ("asphalt", "Asphalt concrete", 23.0, "21-24"),
    ("water", "Fresh water", 9.81, "9.81"),
]


def dead_load(material, volume, thickness):
    r = Result("Self-weight from typical unit weights")
    name, gamma, rng = next((m[1], m[2], m[3]) for m in MATERIALS if m[0] == material)
    r.eq("W = gamma x V;   area load = gamma x thickness")
    r.add("gamma", f"Typical unit weight - {name}", gamma, "kN/m3", 2, note=f"range {rng}")
    r.add("w", "Weight of volume", gamma * volume, "kN", 2, primary=True)
    if thickness is not None:
        r.add("q", "Area load for the given thickness", gamma * thickness, "kPa", 3)
    r.assume("Typical mid-range unit weights for preliminary loads. Use ASCE 7 Table C3.1-1 / your national loading code for design.")
    return r


UNIT_CHOICES = [(m[0], f"{m[1]} (~{m[2]:g} kN/m3)") for m in MATERIALS]

CALCS = [
    Calculation("convert", "Unit converter", "Convert between metric and imperial units of any dimension",
                [Param("value", "Value", ""), Param("from_unit", "From unit (e.g. psi, ft, kip-ft, gpm)", "", "text"),
                 Param("to_unit", "To unit (e.g. MPa, m, kN-m, L/s)", "", "text")],
                convert, "Exact conversion factors (NIST SP 811)"),
    Calculation("angle", "Angle formats", "Decimal degrees, DMS, radians, gradians",
                [Param("value", "Angle (deg, or d-m-s such as 45-30-15)", "deg", typical=(-360, 360))],
                angle, "Angle definitions"),
    Calculation("slope", "Slope converter", "Percent grade, degrees, and 1:n ratio",
                [Param("mode", "Input is", "", "choice", default="percent",
                       choices=[("percent", "Percent grade"), ("degrees", "Degrees"), ("ratio", "Ratio 1 : n (n = H per 1 V)")]),
                 Param("value", "Value", "", min=0, min_exclusive=True)],
                slope, "Trigonometry"),
    Calculation("dead_load", "Material weights", "Typical unit weights and self-weight",
                [Param("material", "Material", "", "choice", default="rc", choices=UNIT_CHOICES),
                 Param("volume", "Volume", "m3", default=1.0, min=0),
                 Param("thickness", "Thickness (optional, for kPa)", "m", optional=True, min=0)],
                dead_load, "Typical values; ASCE 7 Table C3.1-1"),
]

CASES = [
    Case("convert", {"value": 4000, "from_unit": "psi", "to_unit": "MPa"}, {"result": 27.579}, "4000 psi", rel=0.0005),
    Case("convert", {"value": 100, "from_unit": "degF", "to_unit": "degC"}, {"result": 37.7778}, "100 F", rel=0.0005),
    Case("convert", {"value": 1, "from_unit": "ft", "to_unit": "MPa"}, expect_error="Cannot convert"),
    Case("convert", {"value": 1, "from_unit": "cubit", "to_unit": "m"}, expect_error="Unknown unit"),
    Case("angle", {"value": "45-30-15"}, {"deg": 45.504167, "rad": 0.794195}, "DMS input", rel=0.0001),
    Case("slope", {"mode": "ratio", "value": 2}, {"pct": 50.0, "deg": 26.565}, "2:1 slope", rel=0.001),
    Case("dead_load", {"material": "steel", "volume": 2}, {"w": 157.0}, "78.5 kN/m3"),
]

DISCIPLINE = Discipline("utilities", "Unit Conversions and Utilities",
                        "Unit converter, angles, slopes, typical weights", CALCS, CASES, order=90)
