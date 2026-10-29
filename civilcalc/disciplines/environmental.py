"""10b. Environmental / Public Health Engineering (water supply, sewerage, sedimentation)."""
from __future__ import annotations

import math

from ..core import Calculation, Case, Discipline, Param, Result, need


def population(p1, p2, interval, horizon):
    r = Result("Population forecast")
    k = (p2 - p1) / interval
    g = (p2 / p1) ** (1 / interval) - 1
    arith = p2 + k * horizon
    geom = p2 * (1 + g) ** horizon
    r.eq("Arithmetic: P = P2 + k t, k = (P2 - P1)/dt;   Geometric: P = P2 (1 + r)^t, r = (P2/P1)^(1/dt) - 1")
    r.add("k", "Arithmetic growth per year", k, "persons/yr", 0)
    r.add("r", "Geometric growth rate", g * 100, "%/yr", 2)
    r.add("arith", "Forecast - arithmetic", arith, "persons", 0)
    r.add("geom", "Forecast - geometric", geom, "persons", 0)
    r.add("design", "Suggested design population (mean of both)", (arith + geom) / 2, "persons", 0, primary=True)
    r.assume("Two census points only. Growth often slows for mature cities (logistic) and the arithmetic result suits "
             "old, developed cities; use agency planning projections where available.")
    return r


def water_demand(pop, lpcd, max_day, peak_hour, fire):
    r = Result("Water supply demand")
    avg_m3d = pop * lpcd / 1000
    avg_ls = avg_m3d / 86.4
    r.eq("Q_avg = P x q;  Q_maxday = f1 Q_avg;  Q_peak hour = f2 Q_maxday  (1 m3/d = 0.011574 L/s)")
    r.add("avg_m3d", "Average daily demand", avg_m3d, "m3/day", 0)
    r.add("avg_ls", "Average daily demand", avg_ls, "L/s", 1)
    r.add("max_ls", "Maximum day demand", avg_ls * max_day, "L/s", 1, primary=True)
    ph = avg_ls * max_day * peak_hour
    r.add("peak_ls", "Peak hour demand", ph, "L/s", 1)
    if fire is not None:
        r.add("fire_ls", "Max-day + fire flow", avg_ls * max_day + fire, "L/s", 1)
    r.assume(f"Per-capita use {lpcd:g} L/c/d, max-day factor {max_day:g}, peak-hour factor {peak_hour:g} on the max day. "
             "Use the values from your water authority's design manual.")
    return r


def sewage(pop, lpcd, ret, infil):
    r = Result("Sanitary sewage design flow")
    avg_ls = pop * lpcd * ret / 86400 + infil
    p_k = pop / 1000
    m = 1 + 14 / (4 + math.sqrt(p_k))
    r.eq("Q_avg = P q f_return/86400 + infiltration;  Harmon peaking factor M = 1 + 14 / (4 + sqrt(P)), P in thousands")
    r.add("avg", "Average dry-weather flow", avg_ls, "L/s", 2)
    r.add("m", "Harmon peaking factor M", m, "", 2)
    r.add("peak", "Peak design flow", avg_ls * m, "L/s", 2, primary=True)
    r.assume(f"{lpcd:g} L/c/d water use, {ret*100:.0f}% returned to the sewer, infiltration {infil:g} L/s. Harmon is valid for 1,000-1,000,000 people.")
    if pop < 1000 or pop > 1e6:
        r.warn("Population is outside the range where the Harmon formula is calibrated (1,000 - 1,000,000).")
    return r


def clarifier(q, sor, depth):
    r = Result("Circular sedimentation tank sizing")
    a = q / sor
    d = math.sqrt(4 * a / math.pi)
    vol = a * depth
    r.eq("A = Q / SOR;  D = sqrt(4A/pi);  V = A x depth;  detention time = V / Q")
    r.add("area", "Surface area", a, "m2", 1)
    r.add("dia", "Tank diameter", d, "m", 2, primary=True)
    r.add("vol", "Volume", vol, "m3", 0)
    r.add("dt", "Detention time", vol / q * 24, "h", 2)
    if not 1.5 <= vol / q * 24 <= 4.0:
        r.warn("Detention time outside 1.5-4 h typical for primary clarifiers; revisit depth or overflow rate.")
    r.assume(f"Surface overflow rate {sor:g} m3/m2/d (primary 30-50 at average flow; alum floc 20-30; check your design manual), side depth {depth:g} m.")
    return r


CALCS = [
    Calculation("population", "Population forecast", "Arithmetic and geometric projection from two census counts",
                [Param("p1", "Earlier census population", "", min=1),
                 Param("p2", "Later census population", "", min=1),
                 Param("interval", "Years between censuses", "years", default=10.0, min=1, max=50),
                 Param("horizon", "Years ahead of the later census", "years", default=20.0, min=0, max=60)],
                population, "Arithmetic / geometric increase methods"),
    Calculation("water_demand", "Water demand", "Average, max-day and peak-hour demand",
                [Param("pop", "Design population", "", min=1),
                 Param("lpcd", "Per-capita demand", "", default=150.0, min=20, max=600,
                       help="Litres per capita per day."),
                 Param("max_day", "Max-day factor", "", default=1.8, min=1, max=3),
                 Param("peak_hour", "Peak-hour factor (on max day)", "", default=1.5, min=1, max=3),
                 Param("fire", "Fire flow (optional)", "L/s", optional=True, min=0)],
                water_demand, "Water supply engineering practice"),
    Calculation("sewage", "Sewage design flow", "Average and peak flow with Harmon peaking factor",
                [Param("pop", "Design population", "", min=1),
                 Param("lpcd", "Water use", "", default=150.0, min=20, max=600, help="Litres per capita per day."),
                 Param("ret", "Fraction returned to sewer (0-1, % ok)", "", default=0.8, min=0.5, max=1),
                 Param("infil", "Infiltration allowance", "L/s", default=0.0, min=0)],
                sewage, "Harmon (1918) peaking factor"),
    Calculation("clarifier", "Sedimentation tank", "Diameter and detention time of a circular clarifier",
                [Param("q", "Design flow", "m3/day", min=0, min_exclusive=True),
                 Param("sor", "Surface overflow rate", "m/day", default=30.0, min=5, max=100),
                 Param("depth", "Side water depth", "m", default=3.5, min=2, max=6)],
                clarifier, "Overflow-rate design (Metcalf & Eddy)"),
]

CASES = [
    Case("population", {"p1": 100000, "p2": 120000}, {"arith": 160000.0, "geom": 172800.0, "design": 166400.0}, "10-yr census"),
    Case("water_demand", {"pop": 50000}, {"avg_ls": 86.81, "max_ls": 156.25}, "50,000 x 150 L/c/d", rel=0.002),
    Case("sewage", {"pop": 10000, "lpcd": 200}, {"avg": 18.52, "m": 2.955, "peak": 54.7}, "Harmon", rel=0.005),
    Case("clarifier", {"q": 7500}, {"area": 250.0, "dia": 17.84, "dt": 2.8}, "SOR 30 m/d, 3.5 m deep", rel=0.003),
    Case("population", {"p1": 0, "p2": 100}, expect_error="Earlier census"),
]

DISCIPLINE = Discipline("environmental", "Environmental / Public Health",
                        "Population, water demand, sewage flow, clarifier sizing", CALCS, CASES, order=100)
