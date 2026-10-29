"""3. Surveying and Levelling.  Bearings are whole-circle azimuths (0-360 deg from north)."""
from __future__ import annotations

import math

from ..core import Calculation, Case, Discipline, Param, Result, need


def _dms(deg: float) -> str:
    tenths = round((deg % 360) * 36000)          # work in 0.1" so rounding can never print 60.0"
    tenths %= 360 * 36000
    d, rest = divmod(tenths, 36000)
    m, s10 = divmod(rest, 600)
    return f"{d}°{m:02d}'{s10 / 10:04.1f}\""


def level_reduction(rl0, bs, fs, closing_rl, dist_km, k):
    need(len(bs) == len(fs), f"Backsight count ({len(bs)}) must equal foresight count ({len(fs)}).")
    r = Result("Differential levelling - rise and fall")
    rl = rl0
    rise_sum = 0.0
    for i, (b, f) in enumerate(zip(bs, fs), 1):
        diff = b - f
        rl += diff
        rise_sum += diff
        r.add(f"rl{i}", f"RL after setup {i}  (BS {b:g}, FS {f:g})", rl, "m", 3)
    r.eq("Rise/fall = BS - FS;  RL_new = RL_old + (BS - FS);  Arithmetic check: sum(BS) - sum(FS) = RL_last - RL_first")
    r.add("final", "Final reduced level", rl, "m", 3, primary=True)
    r.check("Arithmetic check sum(BS)-sum(FS) = RL_last-RL_first",
            abs((sum(bs) - sum(fs)) - (rl - rl0)) < 1e-9)
    if closing_rl is not None:
        mis = rl - closing_rl
        r.add("misclosure", "Misclosure (computed - known)", mis * 1000, "mm", 1)
        if dist_km is not None:
            tol = k * math.sqrt(dist_km)
            r.add("tolerance", "Allowable misclosure", tol, "mm", 1, note=f"{k:g} sqrt(K)")
            r.check("Misclosure within allowable", abs(mis * 1000) <= tol)
            r.assume(f"Allowable misclosure = {k:g} mm x sqrt(K km): 12 ordinary, 6 precise, 24 for rough levelling.")
        else:
            r.warn("Give the levelled distance to compare with the allowable misclosure.")
    return r


def traverse(x0, y0, bearings, dists):
    need(len(bearings) == len(dists), f"{len(bearings)} bearings but {len(dists)} distances.")
    need(len(dists) >= 3, "A closed traverse needs at least 3 legs.")
    r = Result("Traverse computation (latitudes/departures, Bowditch adjustment)")
    lat = [d * math.cos(math.radians(b)) for b, d in zip(bearings, dists)]
    dep = [d * math.sin(math.radians(b)) for b, d in zip(bearings, dists)]
    perim = sum(dists)
    el, ed = sum(lat), sum(dep)
    lin = math.hypot(el, ed)
    r.eq("Lat = L cos(az); Dep = L sin(az);  linear misclosure = sqrt(sum Lat^2 + sum Dep^2);  relative precision = P / misclosure")
    r.eq("Bowditch: correction_i = -(misclosure component) x L_i / perimeter;  Area = 1/2 |sum(x_i y_i+1 - x_i+1 y_i)|")
    r.add("perimeter", "Perimeter", perim, "m", 3)
    r.add("sum_lat", "Misclosure in latitude", el, "m", 4)
    r.add("sum_dep", "Misclosure in departure", ed, "m", 4)
    r.add("misclosure", "Linear misclosure", lin, "m", 4)
    ratio = perim / lin if lin > 1e-12 else float("inf")
    r.add("precision", "Relative precision (1 in ...)", ratio if math.isfinite(ratio) else 0.0, "", 0, primary=True)
    r.check("Precision 1:5000 or better (typical land survey)", ratio >= 5000,
            "adjust only if within your specification")
    x, y, pts = x0, y0, [(x0, y0)]
    for i in range(len(dists)):
        x += dep[i] - ed * dists[i] / perim
        y += lat[i] - el * dists[i] / perim
        pts.append((x, y))
        r.add(f"pt{i+1}", f"Adjusted point {i+1}  (E, N)", f"{x:.3f}, {y:.3f}", "m")
    area = 0.5 * abs(sum(pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1] for i in range(len(pts) - 1)))
    r.add("area", "Enclosed area (adjusted)", area, "m2", 2)
    r.add("area_ha", "Enclosed area", area / 1e4, "ha", 4)
    r.assume("Leg i runs from point i-1 to point i; the last leg should return to the start. Angles are azimuths from grid north.")
    return r


def inverse(x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    need(abs(dx) + abs(dy) > 0, "The two points are identical.")
    r = Result("Coordinate inverse (join)")
    az = math.degrees(math.atan2(dx, dy)) % 360
    r.eq("D = sqrt(dE^2 + dN^2);  azimuth = atan2(dE, dN)")
    r.add("dist", "Horizontal distance", math.hypot(dx, dy), "m", 3, primary=True)
    r.add("az", "Azimuth (decimal)", az, "deg", 4)
    r.add("az_dms", "Azimuth (d-m-s)", _dms(az), "")
    return r


def stadia(s, theta, k, c):
    r = Result("Tacheometry (stadia, inclined sight)")
    t = math.radians(theta)
    h = k * s * math.cos(t) ** 2 + c * math.cos(t)
    v = 0.5 * k * s * math.sin(2 * t) + c * math.sin(t)
    r.eq("H = K s cos^2(a) + C cos(a);   V = (K s / 2) sin(2a) + C sin(a)")
    r.add("h", "Horizontal distance", h, "m", 3, primary=True)
    r.add("v", "Vertical component", v, "m", 3)
    r.assume(f"Multiplying constant K = {k:g} and additive constant C = {c:g} m (0 for internal-focusing instruments).")
    return r


CALCS = [
    Calculation("levelling", "Levelling book", "Reduced levels from BS/FS pairs with misclosure check",
                [Param("rl0", "Starting benchmark RL", "m", typical=(-500, 9000)),
                 Param("bs", "Backsights (comma separated)", "m", "floatlist", min=0, max=6, min_items=1),
                 Param("fs", "Foresights (comma separated, same count)", "m", "floatlist", min=0, max=6, min_items=1),
                 Param("closing_rl", "Known RL of closing benchmark", "m", optional=True),
                 Param("dist_km", "Total levelled distance", "km", optional=True, min=0, min_exclusive=True),
                 Param("k", "Misclosure constant", "mm", default=12.0, min=1, max=50)],
                level_reduction, "Rise-and-fall method; misclosure = k sqrt(K)"),
    Calculation("traverse", "Closed traverse", "Misclosure, Bowditch adjustment, coordinates and area",
                [Param("x0", "Start Easting", "m", default=1000.0),
                 Param("y0", "Start Northing", "m", default=1000.0),
                 Param("bearings", "Azimuth of each leg (deg or d-m-s, comma sep.)", "deg", "floatlist", min=0, max=360),
                 Param("dists", "Length of each leg (comma separated)", "m", "floatlist", min=0, min_exclusive=True, min_items=3)],
                traverse, "Bowditch (compass) rule; coordinate area formula"),
    Calculation("inverse", "Coordinate join", "Distance and azimuth between two points",
                [Param("x1", "Point 1 Easting", "m"), Param("y1", "Point 1 Northing", "m"),
                 Param("x2", "Point 2 Easting", "m"), Param("y2", "Point 2 Northing", "m")],
                inverse, "Plane coordinate geometry"),
    Calculation("stadia", "Stadia tacheometry", "Horizontal distance and height difference from staff intercept",
                [Param("s", "Staff intercept s", "m", min=0, min_exclusive=True, max=4),
                 Param("theta", "Vertical angle a (+up, -down)", "deg", default=0.0, min=-45, max=45),
                 Param("k", "Multiplying constant K", "", default=100.0, min=50, max=200),
                 Param("c", "Additive constant C", "m", default=0.0, min=0, max=1)],
                stadia, "Tacheometric surveying (inclined sight, vertical staff)"),
]

CASES = [
    Case("levelling", {"rl0": 100, "bs": "1.5, 1.2", "fs": "0.9, 2.1"}, {"final": 99.7},
         "100 + 0.6 - 0.9"),
    Case("levelling", {"rl0": 100, "bs": "1.5, 1.2", "fs": "0.9, 2.1", "closing_rl": 99.69, "dist_km": 1},
         {"misclosure": 10.0, "tolerance": 12.0}, "10 mm vs 12 sqrt(1)"),
    Case("levelling", {"rl0": 100, "bs": "1.5", "fs": "1, 2"}, expect_error="must equal"),
    Case("traverse", {"bearings": "0, 90, 180, 270", "dists": "100, 100, 100, 100"},
         {"misclosure": 0.0, "area": 10000.0, "perimeter": 400.0}, "100 m square"),
    Case("traverse", {"bearings": "0, 90, 180, 270", "dists": "100, 100, 100"}, expect_error="bearings"),
    Case("inverse", {"x1": 0, "y1": 0, "x2": 30, "y2": 40}, {"dist": 50.0, "az": 36.8699}, "3-4-5"),
    Case("stadia", {"s": 1.0, "theta": 0}, {"h": 100.0, "v": 0.0}, "level sight", rel=0.001),
]

DISCIPLINE = Discipline("surveying", "Surveying and Levelling",
                        "Level books, traverses, coordinate joins, tacheometry", CALCS, CASES, order=30)
