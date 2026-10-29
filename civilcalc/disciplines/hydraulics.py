"""6. Water Resources and Hydraulics (SI)."""
from __future__ import annotations

import math

from ..core import Calculation, Case, Discipline, Param, Result, need
from ..units import G


# ------------------------------------------------------------- geometry
def _geom(shape, y, width, z, dia):
    """Return (area, wetted perimeter, top width) at depth y."""
    if shape == "rect":
        return width * y, width + 2 * y, width
    if shape == "trap":
        return (width + z * y) * y, width + 2 * y * math.sqrt(1 + z * z), width + 2 * z * y
    th = 2 * math.acos(max(-1.0, min(1.0, 1 - 2 * y / dia)))
    return dia ** 2 / 8 * (th - math.sin(th)), dia * th / 2, dia * math.sin(th / 2)


def _q(shape, y, width, z, dia, n, s):
    a, p, _ = _geom(shape, y, width, z, dia)
    return a / n * (a / p) ** (2 / 3) * math.sqrt(s) if p > 0 else 0.0


def manning(shape, width, z, dia, n, slope, depth, q):
    r = Result("Manning open-channel / partially full pipe flow")
    need((depth is None) != (q is None), "Give EITHER the flow depth OR the discharge Q (leave the other blank).")
    if shape in ("rect", "trap"):
        need(width is not None, "Bottom width is required for rectangular/trapezoidal sections.")
    else:
        need(dia is not None, "Diameter is required for a circular section.")
    ymax = dia if shape == "circ" else 100.0
    if depth is not None:
        need(depth <= ymax, f"Depth ({depth:g} m) cannot exceed the pipe diameter ({ymax:g} m).")
        y = depth
    else:
        lo, hi = 1e-6, (0.938 * dia if shape == "circ" else ymax)
        qcap = _q(shape, hi, width, z, dia, n, slope)
        need(q <= qcap, f"Q = {q:g} m3/s exceeds the section capacity ({qcap:.3f} m3/s) at this slope.")
        for _ in range(200):
            mid = (lo + hi) / 2
            if _q(shape, mid, width, z, dia, n, slope) < q:
                lo = mid
            else:
                hi = mid
        y = (lo + hi) / 2
    a, p, t = _geom(shape, y, width, z, dia)
    qq = _q(shape, y, width, z, dia, n, slope)
    v = qq / a
    r.eq("Q = (1/n) A R^(2/3) S^(1/2);  R = A/P;  Froude Fr = V / sqrt(g A / T)")
    r.add("y", "Flow depth", y, "m", 3, primary=depth is None)
    r.add("q", "Discharge Q", qq, "m3/s", 4, primary=depth is not None)
    r.add("v", "Mean velocity V", v, "m/s", 3)
    r.add("area", "Flow area A", a, "m2", 4)
    r.add("perim", "Wetted perimeter P", p, "m", 3)
    r.add("rh", "Hydraulic radius R", a / p, "m", 3)
    if t > 1e-6 * max(width or 0.0, dia or 0.0, 1.0):
        fr = v / math.sqrt(G * a / t)
        r.add("fr", "Froude number", fr, "", 2, note="subcritical" if fr < 1 else "supercritical")
    else:
        r.add("fr", "Froude number", "n/a (pipe flowing full: no free surface)", "")
    if shape == "circ":
        qfull = (1 / n) * (math.pi * dia ** 2 / 4) * (dia / 4) ** (2 / 3) * math.sqrt(slope)
        r.add("qfull", "Full-pipe capacity", qfull, "m3/s", 4, note="(1/n)(pi D^2/4)(D/4)^(2/3) S^0.5")
        r.add("fill", "Depth / diameter", y / dia, "", 3)
    if v < 0.6:
        r.warn("Velocity below ~0.6 m/s: sediment deposition likely in drains/sewers.")
    if v > 3.0:
        r.warn("Velocity above ~3 m/s: erosion/abrasion risk; check lining and energy dissipation.")
    r.assume("Steady uniform flow, prismatic section. Manning n is a code/handbook table value (e.g. concrete 0.013, "
             "earth channel 0.025, grassed 0.035) - verify for your surface.")
    return r


def pipe_loss(method, length, dia, q, c_hw, eps, nu):
    r = Result("Pipe friction head loss")
    a = math.pi * dia ** 2 / 4
    v = q / a
    if method == "hw":
        hf = 10.67 * length * q ** 1.852 / (c_hw ** 1.852 * dia ** 4.87)
        r.eq("Hazen-Williams (SI): hf = 10.67 L Q^1.852 / (C^1.852 D^4.87)")
        r.assume(f"Hazen-Williams C = {c_hw:g} (new ductile iron ~130, old cast iron ~100, PVC ~150). Valid for water 5-25 C, turbulent flow, D > 50 mm.")
        if dia < 0.05:
            r.warn("Diameter below 50 mm: Hazen-Williams is outside its range; use Darcy-Weisbach.")
    else:
        re = v * dia / nu
        need(re > 4000, f"Reynolds number {re:.0f} is not turbulent; Swamee-Jain is invalid below 4000.")
        eps_m = eps / 1000.0                     # Param supplies mm
        f = 0.25 / math.log10(eps_m / (3.7 * dia) + 5.74 / re ** 0.9) ** 2
        hf = f * length / dia * v ** 2 / (2 * G)
        r.eq("Darcy-Weisbach: hf = f (L/D) V^2/(2g);  Swamee-Jain: f = 0.25 / [log10(e/(3.7D) + 5.74/Re^0.9)]^2")
        r.add("re", "Reynolds number", re, "", 0)
        r.add("f", "Friction factor f", f, "", 4)
        r.assume(f"Absolute roughness e = {eps:g} mm; kinematic viscosity {nu:g} m2/s (water 20 C = 1.004e-6).")
    r.add("v", "Velocity", v, "m/s", 3)
    r.add("hf", "Head loss", hf, "m", 3, primary=True)
    r.add("slope", "Hydraulic gradient", hf / length * 1000, "m/km", 2)
    if v > 3.0:
        r.warn("Velocity above 3 m/s - high for distribution mains (surge and noise concerns).")
    if v < 0.3:
        r.warn("Velocity below 0.3 m/s - sediment/stagnation concern.")
    return r


def rational(areas, cs, intensity):
    need(len(areas) == len(cs), f"{len(areas)} areas but {len(cs)} runoff coefficients - give one C per area.")
    r = Result("Rational method peak runoff")
    at = sum(areas)
    cw = sum(a * c for a, c in zip(areas, cs)) / at
    q = cw * intensity * at / 360
    r.eq("Q = C i A / 360   (Q m3/s, i mm/h, A ha);  C_w = sum(C_i A_i) / sum(A_i)")
    r.add("area", "Total area", at, "ha", 3)
    r.add("cw", "Weighted runoff coefficient", cw, "", 3)
    r.add("q", "Peak discharge", q, "m3/s", 3, primary=True)
    r.assume("Intensity must be read from the IDF curve for the design return period at a duration equal to the time of concentration. "
             "Rational method is reliable for catchments below about 80 ha.")
    if at > 80:
        r.warn("Catchment above 80 ha: use a hydrograph method (SCS/unit hydrograph) instead.")
    return r


def kirpich(length, slope):
    r = Result("Time of concentration (Kirpich)")
    tc = 0.0195 * length ** 0.77 * slope ** -0.385
    r.eq("tc = 0.0195 L^0.77 S^-0.385   (tc minutes, L m, S m/m)  - Kirpich (1940)")
    r.add("tc", "Time of concentration", tc, "min", 1, primary=True)
    r.assume("Small rural catchments (< 80 ha) with well-defined channels; for overland/paved flow use another method.")
    return r


def weir(length, head, cd):
    r = Result("Sharp-crested rectangular weir")
    q = cd * 2 / 3 * math.sqrt(2 * G) * length * head ** 1.5
    r.eq("Q = Cd (2/3) sqrt(2g) L H^1.5")
    r.add("q", "Discharge", q, "m3/s", 4, primary=True)
    r.assume(f"Discharge coefficient Cd = {cd:g} (0.58-0.65 typical, depends on weir geometry/approach); H measured upstream of drawdown.")
    return r


def orifice(area, head, cd):
    r = Result("Orifice discharge")
    q = cd * area * math.sqrt(2 * G * head)
    r.eq("Q = Cd A sqrt(2 g h)")
    r.add("q", "Discharge", q, "m3/s", 4, primary=True)
    r.add("v", "Jet velocity (vena contracta)", q / (cd * area), "m/s", 2)
    r.assume(f"Cd = {cd:g} (sharp-edged orifice ~0.60-0.62); h = head above orifice centroid.")
    return r


def pump(q, head, eff, rho):
    r = Result("Pump power")
    ph = rho * G * q * head / 1000
    r.eq("P_hydraulic = rho g Q H;   P_shaft = P_hydraulic / eta")
    r.add("hyd", "Hydraulic (water) power", ph, "kW", 2)
    r.add("shaft", "Required shaft power", ph / eff, "kW", 2, primary=True)
    r.assume(f"Wire-to-water efficiency {eff*100:.0f}% (single value); add 10-15% margin when selecting a motor.")
    return r


CALCS = [
    Calculation("manning", "Manning channel / pipe", "Normal depth or discharge for rectangular, trapezoidal, circular sections",
                [Param("shape", "Section", "", "choice", default="rect",
                       choices=[("rect", "Rectangular"), ("trap", "Trapezoidal"), ("circ", "Circular (pipe)")]),
                 Param("width", "Bottom width b (rect/trap)", "m", optional=True, min=0, min_exclusive=True),
                 Param("z", "Side slope z, H:1V (trap)", "", default=0.0, min=0, max=10),
                 Param("dia", "Diameter D (circular)", "m", optional=True, min=0, min_exclusive=True),
                 Param("n", "Manning roughness n", "", default=0.013, min=0.008, max=0.2, typical=(0.009, 0.08)),
                 Param("slope", "Bed slope S (m/m, % ok)", "", min=0, min_exclusive=True, max=0.5, typical=(0.0001, 0.1)),
                 Param("depth", "Flow depth y (blank to solve for it)", "m", optional=True, min=0, min_exclusive=True),
                 Param("q", "Discharge Q (blank to solve for Q)", "m3/s", optional=True, min=0, min_exclusive=True)],
                manning, "Manning's equation"),
    Calculation("pipe_loss", "Pipe head loss", "Hazen-Williams or Darcy-Weisbach friction loss in a full pipe",
                [Param("method", "Method", "", "choice", default="hw",
                       choices=[("hw", "Hazen-Williams"), ("dw", "Darcy-Weisbach (Swamee-Jain)")]),
                 Param("length", "Pipe length", "m", min=0, min_exclusive=True),
                 Param("dia", "Internal diameter", "m", min=0.01, max=5, typical=(0.05, 3)),
                 Param("q", "Flow Q", "m3/s", min=0, min_exclusive=True),
                 Param("c_hw", "Hazen-Williams C", "", default=120.0, min=40, max=160),
                 Param("eps", "Absolute roughness e (Darcy-Weisbach)", "mm", default=0.15, min=0, max=10),
                 Param("nu", "Kinematic viscosity", "m2/s", default=1.004e-6, min=1e-7, max=1e-4)],
                pipe_loss, "Hazen-Williams; Darcy-Weisbach with Swamee-Jain (1976)"),
    Calculation("rational", "Rational method runoff", "Peak flow from area, runoff coefficient and rainfall intensity",
                [Param("areas", "Sub-areas (comma separated)", "ha", "floatlist", min=0, min_exclusive=True, min_items=1),
                 Param("cs", "Runoff coefficient of each area", "", "floatlist", min=0, max=1, min_items=1),
                 Param("intensity", "Design rainfall intensity i", "mm/h", min=0, min_exclusive=True, max=600,
                       typical=(5, 300), help="Read from the IDF curve at the time of concentration.")],
                rational, "Rational method (Q = CiA/360)"),
    Calculation("kirpich", "Time of concentration", "Kirpich equation for small catchments",
                [Param("length", "Flow-path length", "m", min=1, max=20000),
                 Param("slope", "Average slope (m/m, % ok)", "", min=0, min_exclusive=True, max=1)],
                kirpich, "Kirpich (1940)"),
    Calculation("weir", "Rectangular weir", "Discharge over a sharp-crested weir",
                [Param("length", "Crest length L", "m", min=0, min_exclusive=True),
                 Param("head", "Head H over crest", "m", min=0, min_exclusive=True, max=10),
                 Param("cd", "Discharge coefficient Cd", "", default=0.62, min=0.4, max=0.8)],
                weir, "Weir equation (Francis/Rehbock form)"),
    Calculation("orifice", "Orifice flow", "Discharge through a submerged/free orifice",
                [Param("area", "Orifice area", "m2", min=0, min_exclusive=True),
                 Param("head", "Head over orifice centre", "m", min=0, min_exclusive=True, max=500),
                 Param("cd", "Discharge coefficient Cd", "", default=0.61, min=0.4, max=1.0)],
                orifice, "Torricelli with Cd"),
    Calculation("pump", "Pump power", "Hydraulic and shaft power from flow and total head",
                [Param("q", "Flow Q", "m3/s", min=0, min_exclusive=True),
                 Param("head", "Total dynamic head", "m", min=0, min_exclusive=True, max=2000),
                 Param("eff", "Overall efficiency (0-1, % ok)", "", default=0.70, min=0.2, max=0.95),
                 Param("rho", "Fluid density", "kg/m3", default=1000.0, min=800, max=1300)],
                pump, "P = rho g Q H / eta"),
]

CASES = [
    Case("manning", {"shape": "rect", "width": 2, "n": 0.013, "slope": 0.001, "depth": 1},
         {"q": 2 / 0.013 * 0.5 ** (2 / 3) * math.sqrt(0.001), "area": 2.0}, "R=0.5 m"),
    Case("manning", {"shape": "rect", "width": 2, "slope": "0.1%", "depth": 1, "q": 3}, expect_error="EITHER"),
    Case("manning", {"shape": "circ", "dia": 0.6, "n": 0.013, "slope": 0.005, "q": 5}, expect_error="capacity"),
    Case("pipe_loss", {"length": 1000, "dia": 0.3, "q": 0.1}, {"hf": 7.44}, "Hazen-Williams C=120", rel=0.01),
    Case("pipe_loss", {"method": "dw", "length": 1000, "dia": 0.3, "q": 0.1}, {"hf": 6.3, "f": 0.0185}, "Darcy-Weisbach, e=0.15 mm (Moody f ~0.0185)",
         rel=0.05),
    Case("rational", {"areas": "2, 3", "cs": "0.9, 0.5", "intensity": 100}, {"cw": 0.66, "q": 0.66 * 100 * 5 / 360},
         "weighted C"),
    Case("kirpich", {"length": 1000, "slope": 0.01}, {"tc": 23.45}, "Kirpich", rel=0.01),
    Case("weir", {"length": 2, "head": 0.3}, {"q": 0.6016}, "Cd 0.62", rel=0.005),
    Case("orifice", {"area": 0.05, "head": 2}, {"q": 0.1910}, "Cd 0.61", rel=0.005),
    Case("pump", {"q": 0.05, "head": 30, "eff": "70%"}, {"hyd": 14.71, "shaft": 21.01}, "rho g Q H", rel=0.005),
]

DISCIPLINE = Discipline("hydraulics", "Water Resources and Hydraulics",
                        "Manning flow, pipe losses, runoff, weirs, pumps", CALCS, CASES, order=60)
