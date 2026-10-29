"""7. Foundation Engineering."""
from __future__ import annotations

import math

from ..core import Calculation, Case, Discipline, Param, Result, need
from ..units import GAMMA_W


def _terzaghi_n(phi_deg: float):
    """Terzaghi (1943) Nc, Nq from phi. Nc at phi=0 is the limit value 5.7."""
    if phi_deg < 1e-6:
        return 5.7, 1.0
    p = math.radians(phi_deg)
    a = math.exp((0.75 * math.pi - p / 2) * math.tan(p))
    nq = a * a / (2 * math.cos(math.pi / 4 + p / 2) ** 2)
    return (nq - 1) / math.tan(p), nq


def bearing(shape, b, df, c, phi, gamma, gamma_sat, dw, shear, ng_input, fs):
    r = Result("Ultimate and allowable bearing capacity (Terzaghi)")
    if shear == "local":
        c = 2 / 3 * c
        phi = math.degrees(math.atan(2 / 3 * math.tan(math.radians(phi))))
        r.assume(f"Local shear failure: c' = 2/3 c, phi' = {phi:.2f} deg (Terzaghi) for loose/soft soil.")
    nc, nq = _terzaghi_n(phi)
    if ng_input is not None:
        ng, ng_src = ng_input, "user value (Terzaghi table / lab-correlated)"
    else:
        ng = 0.0 if phi < 1e-6 else (nq_prandtl(phi) - 1) * math.tan(math.radians(1.4 * phi))
        ng_src = "Meyerhof (Nq-1)tan(1.4 phi) - conservative vs Terzaghi's chart value"
    gsub = None if gamma_sat is None else gamma_sat - GAMMA_W
    # overburden q and unit weight in the gamma-term
    if dw is None or dw >= df + b:
        q, g_term = gamma * df, gamma
    elif dw >= df:
        need(gsub is not None, "Saturated unit weight is required when the water table is within B below the footing.")
        g_term = gsub + (dw - df) / b * (gamma - gsub)
        q = gamma * df
    else:
        need(gsub is not None, "Saturated unit weight is required when the water table is above the footing base.")
        q = gamma * dw + gsub * (df - dw)
        g_term = gsub
    sc, sg = {"strip": (1.0, 0.5), "square": (1.3, 0.4), "circle": (1.3, 0.3)}[shape]
    qu = sc * c * nc + q * nq + sg * g_term * b * ng
    qall = qu / fs
    qnet = (qu - q) / fs
    r.eq("Strip: qu = c Nc + q Nq + 0.5 g B Ng;  Square: 1.3 c Nc + q Nq + 0.4 g B Ng;  Circular: 1.3 c Nc + q Nq + 0.3 g B Ng")
    r.eq("Nq = a^2 / [2 cos^2(45 + phi/2)],  a = exp[(0.75 pi - phi/2) tan(phi)];  Nc = (Nq - 1) cot(phi);  q = g Df")
    r.add("nc", "Bearing factor Nc", nc, "", 2)
    r.add("nq", "Bearing factor Nq", nq, "", 2)
    r.add("ng", "Bearing factor N-gamma", ng, "", 2, note=ng_src)
    r.add("q", "Effective overburden q at base", q, "kPa", 1)
    r.add("qu", "Ultimate bearing capacity qu", qu, "kPa", 0)
    r.add("qall", "Allowable (gross) bearing pressure", qall, "kPa", 0, primary=True, note=f"FS = {fs:g}")
    r.add("qnet", "Allowable (net) bearing pressure", qnet, "kPa", 0)
    r.assume("Terzaghi factors Nc, Nq computed analytically (match Terzaghi's tables); N-gamma depends on a chart value Kp-gamma "
             "and is therefore a user input with the default above. Depth/inclination factors ignored; vertical centric load; "
             "no sloping ground. Add settlement check separately.")
    if fs < 2.5:
        r.warn("FS below 2.5 is lower than usual practice (typically 2.5-3.0 on gross capacity).")
    r.ref("Terzaghi, K. (1943) Theoretical Soil Mechanics; Das, Principles of Foundation Engineering")
    return r


def nq_prandtl(phi_deg: float) -> float:
    p = math.radians(phi_deg)
    return math.exp(math.pi * math.tan(p)) * math.tan(math.pi / 4 + p / 2) ** 2


def footing_pressure(p, m, bx, ly, thick, gamma_c, gamma_s, df, qall):
    r = Result("Footing contact pressure with moment")
    w_self = bx * ly * thick * gamma_c + bx * ly * (df - thick) * gamma_s if df > thick else bx * ly * thick * gamma_c
    n = p + w_self
    e = m / n
    area = bx * ly
    r.eq("e = M / N;  q = N/(B L) [1 +/- 6e/L] for e <= L/6;  q_max = 2N / [3B(L/2 - e)] for e > L/6")
    r.add("w", "Self-weight of footing + backfill", w_self, "kN", 1)
    r.add("n", "Total vertical load N", n, "kN", 1)
    r.add("e", "Eccentricity e", e, "m", 3, note=f"kern limit L/6 = {ly/6:.3f} m")
    if e <= ly / 6:
        qmax = n / area * (1 + 6 * e / ly)
        qmin = n / area * (1 - 6 * e / ly)
    else:
        need(e < ly / 2, "Eccentricity exceeds half the footing length - the footing would overturn.")
        qmax = 2 * n / (3 * bx * (ly / 2 - e))
        qmin = 0.0
        r.warn("Resultant is outside the middle third: part of the base lifts off (no tension). Enlarge the footing.")
    r.add("qmax", "Maximum contact pressure", qmax, "kPa", 1, primary=True)
    r.add("qmin", "Minimum contact pressure", qmin, "kPa", 1)
    r.check("q_max <= allowable bearing pressure", qmax <= qall, f"q_allow = {qall:g} kPa")
    r.check("Resultant within middle third (e <= L/6)", e <= ly / 6)
    r.assume(f"Moment acts about the axis parallel to B so it varies along L; concrete {gamma_c:g} kN/m3, soil {gamma_s:g} kN/m3 over the base.")
    return r


def settlement(cc, cr, h, e0, s0, ds, sc, q, b, es, nu, iw):
    r = Result("Settlement - consolidation + immediate (elastic)")
    sf = s0 + ds
    need(cc is not None or cr is not None or q is not None,
         "Give Cc (and Cr if over-consolidated) for consolidation settlement and/or q, B, Es for immediate settlement.")
    if cc is None and cr is None:
        sc_m = 0.0
    elif sc is None or sc <= s0:
        need(cc is not None, "Compression index Cc is required for a normally consolidated clay.")
        sc_m = cc * h / (1 + e0) * math.log10(sf / s0)
        r.eq("Normally consolidated:  Sc = Cc H / (1 + e0) log10[(s'0 + ds) / s'0]")
    elif sf <= sc:
        need(cr is not None, "Recompression index Cr is required for an over-consolidated clay.")
        sc_m = cr * h / (1 + e0) * math.log10(sf / s0)
        r.eq("Over-consolidated, s'0 + ds <= s'c:  Sc = Cr H / (1 + e0) log10[(s'0 + ds) / s'0]")
    else:
        need(cr is not None and cc is not None,
             "Both Cr and Cc are required when the final stress exceeds the preconsolidation pressure.")
        sc_m = (cr * h / (1 + e0) * math.log10(sc / s0) + cc * h / (1 + e0) * math.log10(sf / sc))
        r.eq("Over-consolidated, s'0 + ds > s'c:  Sc = Cr H/(1+e0) log10(s'c/s'0) + Cc H/(1+e0) log10[(s'0+ds)/s'c]")
    si = 0.0
    if q is not None:
        need(b is not None and es is not None, "Footing width B and soil modulus Es are needed for immediate settlement.")
        # q [kPa] x B [m] / Es [kPa]  ->  m   (Es is supplied in MPa, so x1000 to kPa)
        si = q * b * (1 - nu ** 2) / (es * 1000.0) * iw
        r.eq("Immediate:  Si = q B (1 - nu^2) Iw / Es")
    r.add("sc", "Consolidation settlement", sc_m * 1000, "mm", 1)
    r.add("si", "Immediate settlement", si * 1000, "mm", 1)
    r.add("total", "Total settlement (primary)", (sc_m + si) * 1000, "mm", 1, primary=True)
    r.assume(f"Layer mid-depth stresses s'0 = {s0:g} kPa and ds = {ds:g} kPa are supplied by you (use 2:1 or Boussinesq for ds); "
             f"Iw = {iw:g} (rigid square 0.82, flexible centre square 1.12, rigid circle 0.79); secondary compression ignored.")
    if sum([sc_m * 1000, si * 1000]) > 50:
        r.warn("Total settlement exceeds 50 mm - check differential settlement against the structure's tolerance.")
    return r


def pile_clay(d, length, cu, alpha, nc, fs):
    r = Result("Bored/driven pile in clay - static capacity (alpha method)")
    ap = math.pi * d * d / 4
    asurf = math.pi * d * length
    qp = ap * cu * nc
    qs = alpha * cu * asurf
    qu = qp + qs
    r.eq("Qu = Qp + Qs = Ap cu Nc + alpha cu As   (cu = undrained shear strength)")
    r.add("qp", "End bearing Qp", qp, "kN", 0)
    r.add("qs", "Shaft resistance Qs", qs, "kN", 0)
    r.add("qu", "Ultimate capacity Qu", qu, "kN", 0)
    r.add("qall", "Allowable capacity", qu / fs, "kN", 0, primary=True, note=f"FS = {fs:g}")
    r.assume(f"Adhesion factor alpha = {alpha:g} (0.3-1.0 depends on cu and pile type - API/FHWA charts), Nc = {nc:g} (9 deep). "
             "Uniform cu along the shaft; group effects, negative skin friction and settlement not checked.")
    if length / d < 10:
        r.warn("L/D below 10: this is a short pile; the alpha method is best for slender piles. Confirm by load test.")
    return r


CALCS = [
    Calculation("bearing", "Bearing capacity (Terzaghi)", "Ultimate and allowable bearing pressure of shallow footings",
                [Param("shape", "Footing shape", "", "choice", default="strip",
                       choices=[("strip", "Strip"), ("square", "Square"), ("circle", "Circular")]),
                 Param("b", "Footing width (or diameter) B", "m", min=0.2, max=50, typical=(0.5, 10)),
                 Param("df", "Founding depth Df", "m", min=0, max=30, typical=(0.3, 6)),
                 Param("c", "Cohesion c", "kPa", default=0.0, min=0, max=500),
                 Param("phi", "Friction angle phi", "deg", default=30.0, min=0, max=45, typical=(0, 42)),
                 Param("gamma", "Unit weight of soil g (moist)", "kN/m3", default=18.0, min=10, max=25, typical=(14, 22)),
                 Param("gamma_sat", "Saturated unit weight", "kN/m3", optional=True, min=12, max=25),
                 Param("dw", "Water table depth below ground", "m", optional=True, min=0),
                 Param("shear", "Failure mode", "", "choice", default="general",
                       choices=[("general", "General shear (dense/stiff)"), ("local", "Local shear (loose/soft)")]),
                 Param("ng_input", "N-gamma (from Terzaghi table, optional)", "", optional=True, min=0, max=500,
                       help="Blank = Meyerhof expression. Terzaghi table: phi 30 -> about 19."),
                 Param("fs", "Factor of safety", "", default=3.0, min=1.5, max=6)],
                bearing, "Terzaghi (1943)"),
    Calculation("footing", "Footing pressure", "Contact pressure with eccentricity and kern check",
                [Param("p", "Column axial load P", "kN", min=0, min_exclusive=True),
                 Param("m", "Column moment M", "kN-m", default=0.0, min=0),
                 Param("bx", "Footing width B", "m", min=0.3, max=30),
                 Param("ly", "Footing length L (in moment direction)", "m", min=0.3, max=30),
                 Param("thick", "Footing thickness", "m", default=0.5, min=0.1, max=5),
                 Param("gamma_c", "Concrete unit weight", "kN/m3", default=24.0, min=20, max=26),
                 Param("gamma_s", "Backfill unit weight", "kN/m3", default=18.0, min=10, max=24),
                 Param("df", "Founding depth", "m", default=1.5, min=0.1, max=30),
                 Param("qall", "Allowable bearing pressure", "kPa", min=10, max=5000)],
                footing_pressure, "Rigid-footing statics (no tension)"),
    Calculation("settlement", "Settlement", "Consolidation (NC/OC clay) and immediate elastic settlement",
                [Param("cc", "Compression index Cc (blank = skip)", "", optional=True, min=0, max=3),
                 Param("cr", "Recompression index Cr (OC clay)", "", optional=True, min=0, max=1),
                 Param("h", "Clay layer thickness H", "m", default=1.0, min=0, max=100),
                 Param("e0", "Initial void ratio e0", "", default=1.0, min=0.2, max=5),
                 Param("s0", "Effective stress at mid-layer s'0", "kPa", default=100.0, min=1, max=5000),
                 Param("ds", "Stress increase at mid-layer ds", "kPa", default=0.0, min=0, max=5000),
                 Param("sc", "Preconsolidation pressure s'c (blank = NC)", "kPa", optional=True, min=1),
                 Param("q", "Net footing pressure q (immediate)", "kPa", optional=True, min=0),
                 Param("b", "Footing width B (immediate)", "m", optional=True, min=0.2),
                 Param("es", "Soil modulus Es (immediate)", "MPa", optional=True, min=0.1, max=1000),
                 Param("nu", "Poisson's ratio", "", default=0.3, min=0, max=0.5),
                 Param("iw", "Influence factor Iw", "", default=0.82, min=0.3, max=3)],
                settlement, "Terzaghi consolidation theory; elastic settlement (Das)"),
    Calculation("pile_clay", "Pile capacity (clay)", "Alpha-method end bearing + shaft resistance",
                [Param("d", "Pile diameter", "m", min=0.1, max=3),
                 Param("length", "Embedded length", "m", min=1, max=100, typical=(5, 60)),
                 Param("cu", "Undrained shear strength cu", "kPa", min=5, max=400, typical=(10, 200)),
                 Param("alpha", "Adhesion factor alpha", "", default=0.5, min=0.1, max=1.2),
                 Param("nc", "End-bearing factor Nc", "", default=9.0, min=6, max=10),
                 Param("fs", "Factor of safety", "", default=2.5, min=1.5, max=5)],
                pile_clay, "Static alpha method (API RP2A / FHWA)"),
]

CASES = [
    Case("bearing", {"shape": "strip", "b": 2, "df": 1.5, "c": 0, "phi": 30, "gamma": 18, "ng_input": 19.13},
         {"nc": 37.16, "nq": 22.46, "qu": 27 * 22.46 + 0.5 * 18 * 2 * 19.13, "qall": 316.9},
         "Terzaghi tables phi=30 (Das)", rel=0.003),
    Case("bearing", {"b": 1.5, "df": 1.0, "c": 25, "phi": 0, "gamma": 18}, {"qu": 25 * 5.7 + 18.0},
         "phi = 0 clay: qu = 5.7c + gDf"),
    Case("bearing", {"b": 1.5, "df": 1.0, "dw": 0.5}, expect_error="Saturated unit weight"),
    Case("footing", {"p": 1000, "bx": 3, "ly": 3, "thick": 0.5, "df": 0.5, "qall": 400},
         {"n": 1000 + 3 * 3 * 0.5 * 24, "e": 0.0}, "concentric"),
    Case("footing", {"p": 1000, "m": 3000, "bx": 3, "ly": 3, "qall": 400}, expect_error="overturn"),
    Case("settlement", {"cc": 0.3, "h": 4, "e0": 0.9, "s0": 100, "ds": 50}, {"sc": 111.2}, "NC clay", rel=0.003),
    Case("settlement", {"q": 100, "b": 2, "es": 10, "nu": 0.3, "iw": 0.82}, {"si": 14.92, "total": 14.92},
         "immediate: 100x2x0.91x0.82/10,000 kPa = 14.9 mm", rel=0.002),
    Case("settlement", {"cc": 0.3, "cr": 0.05, "h": 4, "e0": 0.9, "s0": 100, "ds": 50, "sc": 200}, {"sc": 18.54},
         "OC clay, final stress below preconsolidation: Cr only", rel=0.003),
    Case("settlement", {"h": 4}, expect_error="Give Cc"),
    Case("pile_clay", {"d": 0.5, "length": 15, "cu": 50}, {"qp": 88.4, "qs": 589.0, "qall": 270.9},
         "alpha 0.5, Nc 9, FS 2.5", rel=0.003),
]

DISCIPLINE = Discipline("foundations", "Foundation Engineering",
                        "Bearing capacity, footing pressure, settlement, piles", CALCS, CASES, order=70)
