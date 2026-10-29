"""4. Structural Engineering.  Beam analysis works in N and mm internally."""
from __future__ import annotations

import math

from ..core import Calculation, Case, Discipline, Param, Result, need

N_PTS = 2000


def simple_beam(span, w, p, a, e, i):
    r = Result("Simply supported beam - reactions, M, V, deflection")
    if p == 0:
        a = 0.0
    need(0 <= a <= span, f"Point-load position ({a:g} m) must lie within the span (0 to {span:g} m).")
    L = span * 1000.0                    # mm
    W = w                                # kN/m == N/mm
    P = p * 1000.0                       # N
    A = a * 1000.0
    B = L - A
    EI = e * i                           # N-mm2
    ra = W * L / 2 + P * B / L
    rb = W * L / 2 + P * A / L
    m_max = v_max = d_max = 0.0
    x_m = x_d = 0.0
    # uniform grid plus the exact load point (moment peak) so the maximum is not missed between samples
    xs = [L * k / N_PTS for k in range(N_PTS + 1)] + ([A] if P else [])
    for x in xs:
        v = ra - W * x - (P if (P and x > A) else 0.0)
        m = ra * x - W * x * x / 2 - (P * (x - A) if (P and x > A) else 0.0)
        y = W * x * (L ** 3 - 2 * L * x * x + x ** 3) / (24 * EI)
        if P:
            if x <= A:
                y += P * B * x * (L * L - B * B - x * x) / (6 * L * EI)
            else:
                xr = L - x
                y += P * A * xr * (L * L - A * A - xr * xr) / (6 * L * EI)
        if abs(m) > abs(m_max):
            m_max, x_m = m, x
        if abs(v) > abs(v_max):
            v_max = v
        if abs(y) > abs(d_max):
            d_max, x_d = y, x
    r.eq("Reactions by statics; UDL: M = wL^2/8, y = 5wL^4/(384EI);  point load: y piecewise (Roark / AISC beam diagrams)")
    r.eq("Superposition of UDL and point load; extremes found by sampling the exact y(x), M(x), V(x) expressions")
    r.add("ra", "Reaction at left support", ra / 1000, "kN", 2)
    r.add("rb", "Reaction at right support", rb / 1000, "kN", 2)
    r.add("mmax", "Maximum bending moment", m_max / 1e6, "kN-m", 2, primary=True, note=f"at x = {x_m/1000:.2f} m")
    r.add("vmax", "Maximum shear", abs(v_max) / 1000, "kN", 2)
    r.add("dmax", "Maximum deflection", d_max, "mm", 2, note=f"at x = {x_d/1000:.2f} m")
    r.add("ratio", "Span / deflection", L / d_max if d_max else float("inf"), "", 0)
    for lim in (240, 360, 480):
        r.check(f"Deflection <= L/{lim}", d_max <= L / lim)
    r.assume("Self-weight is NOT included - add it to the UDL. Loads are service (unfactored) for deflection. Linear elastic, prismatic section.")
    return r


def rc_column(b, h, ast, fc, fy, phi, k_lu_r, braced, m1_m2):
    ag = b * h
    need(ast < ag, "Steel area exceeds the gross section area.")
    r = Result("RC short tied column - axial capacity")
    rho = ast / ag
    p0 = 0.85 * fc * (ag - ast) + fy * ast
    pn_max = 0.80 * p0
    r.eq("P0 = 0.85 f'c (Ag - Ast) + fy Ast;  Pn,max = 0.80 P0 (tied);  phi Pn,max  (ACI 318-19 Eq. 22.4.2.2, Table 22.4.2.1)")
    r.add("rho", "Steel ratio Ast/Ag", rho * 100, "%", 2)
    r.add("p0", "Nominal axial capacity P0", p0 / 1000, "kN", 0)
    r.add("phipn", "Design axial capacity phi Pn,max", phi * pn_max / 1000, "kN", 0, primary=True)
    r.check("1% <= rho <= 8% (ACI 10.6.1.1)", 0.01 <= rho <= 0.08)
    lim = min(40.0, 34.0 + 12.0 * m1_m2) if braced else 22.0
    r.check("Short-column limit kLu/r", k_lu_r <= lim,
            f"kLu/r = {k_lu_r:g}; limit {lim:g} (braced: min(34 + 12 M1/M2, 40); sway: 22)  ACI 6.2.5")
    if k_lu_r > lim:
        r.warn("Column is slender: moment magnification / second-order analysis is mandatory; the axial capacity above is not sufficient.")
    r.assume(f"phi = {phi:g} (compression-controlled tied); minimum eccentricity assumed covered by the 0.80 factor; no bending.")
    return r


def steel_beam(zx, fy, lb, ry, e, aw, phi_b, phi_v):
    r = Result("Steel I-beam - yielding moment and shear (AISC 360 F2/G2)")
    mp = fy * zx / 1e6
    lp = 1.76 * ry * math.sqrt(e / fy) / 1000
    vn = 0.6 * fy * aw / 1000
    r.eq("Mn = Mp = Fy Zx  (compact, Lb <= Lp);  Lp = 1.76 ry sqrt(E/Fy);  Vn = 0.6 Fy Aw Cv (Cv = 1.0 rolled I, h/tw <= 2.24 sqrt(E/Fy))")
    r.add("mp", "Plastic moment Mp", mp, "kN-m", 1)
    r.add("phimn", "Design moment phi Mn", phi_b * mp, "kN-m", 1, primary=True)
    r.add("lp", "Limiting unbraced length Lp", lp, "m", 2)
    r.add("phivn", "Design shear phi Vn", phi_v * vn, "kN", 1)
    r.check("Lb <= Lp (yielding governs)", lb <= lp,
            "" if lb <= lp else "Lateral-torsional buckling governs; Mn is NOT valid - use AISC F2.2 / F2.3")
    r.assume(f"phi_b = {phi_b:g}, phi_v = {phi_v:g}. Compact flange/web assumed (verify width-thickness limits in AISC Table B4.1b). Section properties are user inputs from the steel table.")
    return r


def load_combos(d, l, lr, s, w, e):
    r = Result("Factored load combinations (LRFD)")
    roof = max(lr, s)
    combos = [
        ("1.4D", 1.4 * d),
        ("1.2D + 1.6L + 0.5(Lr or S)", 1.2 * d + 1.6 * l + 0.5 * roof),
        ("1.2D + 1.6(Lr or S) + (L or 0.5W)", 1.2 * d + 1.6 * roof + max(l, 0.5 * w)),
        ("1.2D + 1.0W + L + 0.5(Lr or S)", 1.2 * d + w + l + 0.5 * roof),
        ("1.2D + 1.0E + L + 0.2S", 1.2 * d + e + l + 0.2 * s),
        ("0.9D + 1.0W", 0.9 * d + w),
        ("0.9D + 1.0E", 0.9 * d + e),
    ]
    r.eq("ASCE 7-16 Sec. 2.3.1 basic LRFD combinations (all load effects entered in the same unit, signed)")
    for i, (name, v) in enumerate(combos, 1):
        r.add(f"c{i}", name, v, "", 2)
    gov = max(combos, key=lambda c: c[1])
    low = min(combos, key=lambda c: c[1])
    r.add("gov", "Governing (maximum) combination", gov[1], "", 2, primary=True, note=gov[0])
    r.add("low", "Minimum combination (uplift / reversal check)", low[1], "", 2, note=low[0])
    if low[1] < 0:
        r.warn("A combination is negative: the member sees uplift or load reversal. Design for it separately.")
    r.assume("Enter each load effect in one consistent unit (kN, kN/m, kPa ...) with its sign (uplift negative); the maximum and "
             "minimum over all combinations are reported. Roof term uses the larger of Lr and S (R, rain, is not included). "
             "Check ASCE 7 exceptions (L factor 0.5 for light occupancies) for your project.")
    return r


def min_thickness(span, member, support, fy):
    r = Result("Minimum thickness to skip deflection check (ACI 318-19)")
    table = {
        ("slab", "simple"): 20, ("slab", "one_end"): 24, ("slab", "both_ends"): 28, ("slab", "cantilever"): 10,
        ("beam", "simple"): 16, ("beam", "one_end"): 18.5, ("beam", "both_ends"): 21, ("beam", "cantilever"): 8,
    }
    div = table[(member, support)]
    corr = 0.4 + fy / 700 if fy != 420 else 1.0
    h = span * 1000 / div * corr
    r.eq("h_min = L / n x (0.4 + fy/700)   n: one-way slab 20/24/28/10, beam 16/18.5/21/8  (ACI 318-19 Tables 7.3.1.1, 9.3.1.1)")
    r.add("h", "Minimum thickness", h, "mm", 0, primary=True)
    r.add("n", "Span divisor n", div, "", 1)
    r.assume("Normal-weight concrete, members not supporting partitions likely to be damaged by large deflection; fy correction applied for fy != 420 MPa.")
    return r


SUPPORT = [("simple", "Simply supported"), ("one_end", "One end continuous"),
           ("both_ends", "Both ends continuous"), ("cantilever", "Cantilever")]

CALCS = [
    Calculation("beam", "Simply supported beam", "Reactions, max moment/shear, deflection under UDL + point load",
                [Param("span", "Span L", "m", min=0, min_exclusive=True, max=200, typical=(1, 40)),
                 Param("w", "Uniform load w (service)", "kN/m", default=0.0, min=0),
                 Param("p", "Point load P (service)", "kN", default=0.0, min=0),
                 Param("a", "Point load distance from left support", "m", default=0.0, min=0),
                 Param("e", "Modulus E", "MPa", default=200000, min=1000, max=300000,
                       help="Steel 200,000; concrete ~25,000; timber ~10,000"),
                 Param("i", "Second moment of area I", "mm4", min=0, min_exclusive=True)],
                simple_beam, "Statics; elastic beam theory (Euler-Bernoulli)"),
    Calculation("column", "RC tied column", "Axial capacity phi*Pn,max and slenderness screen",
                [Param("b", "Width b", "mm", min=150, max=3000, typical=(200, 1000)),
                 Param("h", "Depth h", "mm", min=150, max=3000, typical=(200, 1000)),
                 Param("ast", "Total longitudinal steel Ast", "mm2", min=0, min_exclusive=True),
                 Param("fc", "Concrete f'c", "MPa", min=17, max=100, typical=(20, 60)),
                 Param("fy", "Steel fy", "MPa", default=420, min=240, max=690),
                 Param("phi", "Strength reduction factor", "", default=0.65, min=0.5, max=0.9),
                 Param("k_lu_r", "Slenderness k*lu/r", "", default=20.0, min=0, max=200),
                 Param("m1_m2", "End-moment ratio M1/M2 (braced only)", "", default=-1.0, min=-1, max=1,
                       help="ACI sign: negative = single curvature, positive = double. -1 is the conservative default."),
                 Param("braced", "Frame", "", "choice", default="braced",
                       choices=[("braced", "Braced against sidesway"), ("sway", "Unbraced (sway)")])],
                rc_column, "ACI 318-19 Sec. 22.4.2, 10.6.1, 6.2.5"),
    Calculation("steel_beam", "Steel I-beam capacity", "Design moment and shear for a compact rolled I-section",
                [Param("zx", "Plastic section modulus Zx", "mm3", min=1000, typical=(1e5, 1e8),
                       help="From the steel section table; units may be typed, e.g. W16x40 has Zx = 73 in3."),
                 Param("fy", "Yield stress Fy", "MPa", default=345, min=200, max=700),
                 Param("lb", "Unbraced length Lb", "m", default=0.0, min=0),
                 Param("ry", "Radius of gyration ry", "mm", min=5, max=300),
                 Param("e", "Modulus E", "MPa", default=200000, min=190000, max=210000),
                 Param("aw", "Web area Aw = d x tw", "mm2", min=100),
                 Param("phi_b", "phi flexure", "", default=0.9, min=0.5, max=1.0),
                 Param("phi_v", "phi shear", "", default=1.0, min=0.5, max=1.0)],
                steel_beam, "AISC 360-16 Sec. F2.1, G2.1"),
    Calculation("combos", "Load combinations", "ASCE 7-16 LRFD factored combinations and governing value",
                [Param("d", "Dead load D", "", default=0.0),
                 Param("l", "Live load L", "", default=0.0),
                 Param("lr", "Roof live load Lr", "", default=0.0),
                 Param("s", "Snow load S", "", default=0.0),
                 Param("w", "Wind load W", "", default=0.0),
                 Param("e", "Earthquake load E", "", default=0.0)],
                load_combos, "ASCE 7-16 Sec. 2.3.1"),
    Calculation("min_h", "Min. slab/beam thickness", "ACI one-way member thickness where deflections need not be checked",
                [Param("span", "Span length", "m", min=0, min_exclusive=True, max=40),
                 Param("member", "Member", "", "choice", default="slab",
                       choices=[("slab", "One-way slab"), ("beam", "Beam")]),
                 Param("support", "Support condition", "", "choice", default="simple", choices=SUPPORT),
                 Param("fy", "Steel fy", "MPa", default=420, min=240, max=690)],
                min_thickness, "ACI 318-19 Tables 7.3.1.1 and 9.3.1.1"),
]

CASES = [
    Case("beam", {"span": 6, "w": 10, "i": 5e8}, {"ra": 30.0, "mmax": 45.0, "vmax": 30.0, "dmax": 1.6875},
         "wL^2/8 = 45; 5wL^4/384EI", rel=0.002),
    Case("beam", {"span": 6, "p": 20, "a": 3, "i": 5e8}, {"mmax": 30.0, "dmax": 20e3 * 6000 ** 3 / (48 * 2e5 * 5e8)},
         "PL/4 and PL^3/48EI", rel=0.002),
    Case("beam", {"span": 6, "p": 20, "a": 8, "i": 5e8}, expect_error="within the span"),
    Case("column", {"b": 400, "h": 400, "ast": 1600, "fc": 30}, {"phipn": 2449.8}, "0.8 x 0.65 x 4711 kN", rel=0.002),
    Case("steel_beam", {"zx": 1.6e6, "ry": 30, "aw": 3000, "lb": 1.0},
         {"mp": 552.0, "phimn": 496.8, "phivn": 621.0}, "Mp = 345 x 1.6e6", rel=0.002),
    Case("combos", {"d": 10, "l": 5}, {"gov": 20.0, "c1": 14.0}, "1.2(10)+1.6(5)=20"),
    Case("combos", {"d": 10, "w": -30}, {"gov": 14.0, "low": -21.0}, "uplift: 0.9(10) - 30 = -21"),
    Case("combos", {"d": 10, "l": 5, "s": 4, "w": 20},
         {"c3": 1.2 * 10 + 1.6 * 4 + max(5, 10), "c4": 1.2 * 10 + 20 + 5 + 0.5 * 4},
         "ASCE 7 eq. 3 takes the larger of L and 0.5W"),
    Case("min_h", {"span": 6}, {"h": 300.0}, "simple slab L/20"),
]

DISCIPLINE = Discipline("structural", "Structural Engineering",
                        "Beam analysis, RC column, steel beam, load combinations", CALCS, CASES, order=40)
