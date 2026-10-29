"""10a. Geotechnical (soil mechanics, earth retention, slopes) - extra domain beyond the core list."""
from __future__ import annotations

import math

from ..core import Calculation, Case, Discipline, Param, Result, need
from ..units import GAMMA_W


def phase(gs, e, w):
    r = Result("Soil phase relationships")
    s = w / 100 * gs / e
    gd = gs * GAMMA_W / (1 + e)
    r.eq("S e = w Gs;  gamma_d = Gs gw/(1+e);  gamma = gamma_d (1+w);  gamma_sat = (Gs+e) gw/(1+e);  n = e/(1+e)")
    r.add("s", "Degree of saturation S", s * 100, "%", 1)
    r.add("gd", "Dry unit weight", gd, "kN/m3", 2)
    r.add("g", "Bulk (moist) unit weight", gd * (1 + w / 100), "kN/m3", 2, primary=True)
    r.add("gsat", "Saturated unit weight", (gs + e) * GAMMA_W / (1 + e), "kN/m3", 2)
    r.add("gsub", "Submerged unit weight", (gs + e) * GAMMA_W / (1 + e) - GAMMA_W, "kN/m3", 2)
    r.add("n", "Porosity", e / (1 + e) * 100, "%", 1)
    if s > 1.0 + 1e-9:
        r.warn(f"w Gs / e gives S = {s*100:.0f}% (> 100%) - the water content, void ratio and Gs are not mutually possible.")
    r.assume(f"Unit weight of water {GAMMA_W:g} kN/m3.")
    return r


def atterberg(ll, pl, w):
    need(pl <= ll, f"Plastic limit ({pl:g}%) cannot exceed liquid limit ({ll:g}%).")
    r = Result("Atterberg limits and fines classification")
    pi = ll - pl
    r.eq("PI = LL - PL;  LI = (w - PL)/PI;  A-line: PI = 0.73 (LL - 20)  (Casagrande plasticity chart, ASTM D2487)")
    r.add("pi", "Plasticity index PI", pi, "%", 1, primary=True)
    if pi > 0:
        li = (w - pl) / pi
        state = ("brittle solid / very stiff" if li < 0 else "plastic" if li <= 1 else "liquid-like (sensitive)")
        r.add("li", "Liquidity index LI", li, "", 2, note=state)
    a_line = 0.73 * (ll - 20)
    if pi < 4:
        grp = "ML" if ll < 50 else "MH"
    elif pi > a_line:
        grp = "CL" if ll < 50 else "CH"
    else:
        grp = "ML" if ll < 50 else "MH"
    r.add("group", "USCS fines group (plasticity chart)", grp, "", note="CL-ML dual symbol zone (4 < PI < 7) not resolved")
    r.assume("Applies to the fraction passing the 0.075 mm sieve and assumes it is the dominant fraction; organic soils need an oven-dry LL test.")
    return r


def wall(h, b, gc, phi, gs, q, mu):
    r = Result("Rankine earth pressure and gravity-wall stability (rectangular section)")
    ka = math.tan(math.radians(45 - phi / 2)) ** 2
    pa1 = 0.5 * ka * gs * h * h
    pa2 = ka * q * h
    pa = pa1 + pa2
    w = gc * b * h
    mo = pa1 * h / 3 + pa2 * h / 2
    mr = w * b / 2
    fso = mr / mo
    fss = mu * w / pa
    xbar = (mr - mo) / w
    e = b / 2 - xbar
    r.eq("Ka = tan^2(45 - phi/2);  Pa = 0.5 Ka g H^2 + Ka q H;  FS_ot = M_r/M_o;  FS_sl = mu W / Pa;  e = B/2 - (M_r - M_o)/W")
    r.add("ka", "Active coefficient Ka", ka, "", 3)
    r.add("pa", "Active thrust Pa", pa, "kN/m", 2)
    r.add("w", "Wall weight W", w, "kN/m", 1)
    r.add("fso", "FS overturning", fso, "", 2, primary=True)
    r.add("fss", "FS sliding", fss, "", 2)
    r.add("e", "Base eccentricity e", e, "m", 3, note=f"B/6 = {b/6:.3f} m")
    if e <= b / 6:
        r.add("qmax", "Maximum toe pressure", w / b * (1 + 6 * e / b), "kPa", 1)
        r.add("qmin", "Minimum heel pressure", w / b * (1 - 6 * e / b), "kPa", 1)
    else:
        r.warn("Resultant outside the middle third; base pressure triangle is partial - widen the base.")
    r.check("FS overturning >= 2.0", fso >= 2.0)
    r.check("FS sliding >= 1.5", fss >= 1.5)
    r.check("Resultant in middle third (e <= B/6)", e <= b / 6)
    r.assume(f"Smooth vertical wall, horizontal granular backfill, no passive resistance or water pressure, base friction mu = {mu:g} "
             "(typically tan(2/3 phi) to tan(phi)). Bearing capacity of the base soil must be checked separately.")
    r.ref("Rankine (1857); Das, Principles of Foundation Engineering, Ch. 7")
    return r


def infinite_slope(beta, h, c, phi, g, gsat, seep):
    r = Result("Infinite slope stability")
    tb = math.tan(math.radians(beta))
    cb = math.cos(math.radians(beta))
    tp = math.tan(math.radians(phi))
    if seep == "dry":
        fs = c / (g * h * cb * cb * tb) + tp / tb
        r.eq("FS = c / (g H cos^2(b) tan(b)) + tan(phi)/tan(b)   (no groundwater)")
    else:
        gsub = gsat - GAMMA_W
        fs = c / (gsat * h * cb * cb * tb) + gsub / gsat * tp / tb
        r.eq("FS = c / (g_sat H cos^2(b) tan(b)) + (g'/g_sat) tan(phi)/tan(b)   (seepage parallel to slope, water table at surface)")
    r.add("fs", "Factor of safety", fs, "", 2, primary=True)
    r.check("FS >= 1.5 (long-term slopes)", fs >= 1.5)
    if beta > phi and c == 0:
        r.warn("Slope angle exceeds phi for a cohesionless soil - unstable.")
    r.assume("Planar failure parallel to the slope in a uniform layer of thickness H; use limit-equilibrium software for circular surfaces.")
    return r


CALCS = [
    Calculation("phase", "Soil phase relations", "Unit weights, saturation, porosity from Gs, e, w",
                [Param("gs", "Specific gravity Gs", "", default=2.65, min=2.0, max=3.2, typical=(2.5, 2.85)),
                 Param("e", "Void ratio e", "", min=0.05, max=6, typical=(0.3, 2.5)),
                 Param("w", "Water content w", "%", default=0.0, min=0, max=300)],
                phase, "Basic soil mechanics (Das, Ch. 3)"),
    Calculation("atterberg", "Atterberg limits", "PI, LI and plasticity-chart classification",
                [Param("ll", "Liquid limit LL", "%", min=0, max=300, typical=(15, 120)),
                 Param("pl", "Plastic limit PL", "%", min=0, max=150, typical=(10, 60)),
                 Param("w", "Natural water content w", "%", default=0.0, min=0, max=300)],
                atterberg, "ASTM D4318, D2487"),
    Calculation("wall", "Retaining wall stability", "Rankine pressure; overturning, sliding, base pressure of a gravity wall",
                [Param("h", "Retained height H", "m", min=0.5, max=15, typical=(1, 8)),
                 Param("b", "Wall base width B (rectangular)", "m", min=0.3, max=15),
                 Param("gc", "Wall unit weight", "kN/m3", default=24.0, min=15, max=26),
                 Param("phi", "Backfill friction angle", "deg", default=30.0, min=0, max=45),
                 Param("gs", "Backfill unit weight", "kN/m3", default=18.0, min=10, max=24),
                 Param("q", "Surcharge on backfill", "kPa", default=0.0, min=0, max=500),
                 Param("mu", "Base friction coefficient", "", default=0.5, min=0.1, max=0.9)],
                wall, "Rankine active earth pressure"),
    Calculation("slope", "Infinite slope", "Factor of safety of a planar slope with or without seepage",
                [Param("beta", "Slope angle", "deg", min=1, max=80, typical=(5, 45)),
                 Param("h", "Depth to failure plane H", "m", min=0.1, max=50),
                 Param("c", "Effective cohesion c'", "kPa", default=0.0, min=0, max=200),
                 Param("phi", "Effective friction angle", "deg", default=30.0, min=0, max=45),
                 Param("g", "Unit weight (moist)", "kN/m3", default=18.0, min=10, max=25),
                 Param("gsat", "Saturated unit weight", "kN/m3", default=20.0, min=12, max=25),
                 Param("seep", "Groundwater", "", "choice", default="dry",
                       choices=[("dry", "None (dry)"), ("seep", "Seepage parallel to slope, water table at surface")])],
                infinite_slope, "Infinite-slope limit equilibrium (Das, Ch. 15)"),
]

CASES = [
    Case("phase", {"gs": 2.7, "e": 0.7, "w": 20}, {"s": 77.14, "gd": 15.58, "g": 18.70}, "textbook phase check", rel=0.003),
    Case("phase", {"gs": 2.7, "e": 0.5, "w": 30}, {"s": 162.0}, "over-saturated combination flagged", rel=0.01),
    Case("atterberg", {"ll": 45, "pl": 22, "w": 30}, {"pi": 23.0, "li": 8 / 23, "group": "CL"}, "above A-line"),
    Case("atterberg", {"ll": 20, "pl": 30}, expect_error="cannot exceed"),
    Case("wall", {"h": 3, "b": 2}, {"ka": 1 / 3, "pa": 27.0, "fso": 144 / 27, "fss": 0.5 * 144 / 27, "qmax": 112.5},
         "Rankine hand calc"),
    Case("slope", {"beta": 20, "h": 3}, {"fs": math.tan(math.radians(30)) / math.tan(math.radians(20))}, "dry sand"),
]

DISCIPLINE = Discipline("geotech", "Geotechnical: Soil, Walls, Slopes",
                        "Phase relations, Atterberg limits, retaining walls, slope FS", CALCS, CASES, order=75)
