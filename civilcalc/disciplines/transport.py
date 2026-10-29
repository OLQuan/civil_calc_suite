"""5. Transportation and Pavement."""
from __future__ import annotations

import math

from ..core import Calculation, Case, Discipline, Param, Result, need

MPA_TO_PSI = 145.0377377


def _sta(m: float) -> str:
    """Chainage 1234.5 -> '1+234.50' (rounded to 0.01 m first so 999.999 does not print as 0+1000.00)."""
    m = round(m, 2)
    return f"{int(m // 1000)}+{m % 1000:06.2f}"


def hcurve(radius, delta, pi_chainage):
    need(delta < 180, "Deflection angle must be below 180 degrees.")
    r = Result("Simple horizontal circular curve")
    d = math.radians(delta)
    t = radius * math.tan(d / 2)
    length = radius * d
    lc = 2 * radius * math.sin(d / 2)
    e = radius * (1 / math.cos(d / 2) - 1)
    m = radius * (1 - math.cos(d / 2))
    r.eq("T = R tan(D/2);  L = R D;  LC = 2R sin(D/2);  E = R (sec(D/2) - 1);  M = R (1 - cos(D/2))")
    r.add("t", "Tangent length T", t, "m", 3)
    r.add("l", "Curve length L", length, "m", 3, primary=True)
    r.add("lc", "Long chord LC", lc, "m", 3)
    r.add("e", "External distance E", e, "m", 3)
    r.add("m", "Middle ordinate M", m, "m", 3)
    r.add("pc", "PC chainage", _sta(pi_chainage - t), "")
    r.add("pt", "PT chainage", _sta(pi_chainage - t + length), "")
    if pi_chainage < t:
        r.warn("PI chainage is less than T, so the PC falls before chainage zero.")
    return r


def min_radius(v, e, f):
    r = Result("Minimum horizontal curve radius")
    rmin = v ** 2 / (127 * (e + f))
    r.eq("R_min = V^2 / [127 (e + f)]   (V km/h, R m)  - AASHTO Green Book Eq. 3-8")
    r.add("rmin", "Minimum radius", rmin, "m", 0, primary=True)
    r.assume(f"Superelevation e = {e:g} and side-friction factor f = {f:g}. AASHTO limits depend on design speed "
             "(f ~ 0.17 at 50, 0.14 at 80, 0.12 at 100 km/h; e_max 4-12%) - enter the values from your agency's table.")
    if e > 0.12:
        r.warn("e above 0.12 exceeds the maximum used by AASHTO (12%).")
    return r


def ssd(v, t, a, grade):
    g = 9.81
    r = Result("Stopping sight distance")
    need(a / g + grade / 100 > 0, "Downhill grade is so steep that the vehicle cannot decelerate at this rate (a/g + G <= 0).")
    brake = v ** 2 / (254 * (a / g + grade / 100))
    react = 0.278 * v * t
    r.eq("SSD = 0.278 V t + V^2 / [254 (a/9.81 +/- G)]   (V km/h, G in m/m: 4% = 0.04, + uphill)  - AASHTO Green Book Eq. 3-2")
    r.add("react", "Reaction distance", react, "m", 1)
    r.add("brake", "Braking distance", brake, "m", 1)
    r.add("ssd", "Stopping sight distance", react + brake, "m", 1, primary=True)
    r.assume(f"Perception-reaction time {t:g} s and deceleration {a:g} m/s2 (AASHTO uses 2.5 s and 3.4 m/s2).")
    return r


def vcurve(pvi_sta, pvi_elev, g1, g2, length, query):
    need(g1 != g2, "Grades g1 and g2 are equal - no vertical curve is needed.")
    r = Result("Parabolic vertical curve")
    a = g2 - g1
    k = length / abs(a)
    pvc_sta = pvi_sta - length / 2
    pvc = pvi_elev - g1 / 100 * length / 2
    pvt = pvi_elev + g2 / 100 * length / 2

    def elev(x):
        return pvc + g1 / 100 * x + a / (200 * length) * x * x

    r.eq("A = g2 - g1;  K = L/|A|;  y = y_PVC + (g1/100) x + [A / (200 L)] x^2;  E = A L / 800;  x_turn = -g1 L / A")
    r.add("a", "Algebraic grade difference A", a, "%", 3)
    r.add("k", "Rate of vertical curvature K", k, "m/%", 2, primary=True)
    r.add("pvc", "PVC chainage / elevation", f"{_sta(pvc_sta)}  /  {pvc:.3f} m", "")
    r.add("pvt", "PVT chainage / elevation", f"{_sta(pvc_sta + length)}  /  {pvt:.3f} m", "")
    r.add("e", "Offset at PVI (E)", abs(a) * length / 800, "m", 3)
    xt = -g1 * length / a
    if 0 < xt < length:
        r.add("turn", "High/low point chainage / elevation", f"{_sta(pvc_sta + xt)}  /  {elev(xt):.3f} m", "")
    if query is not None:
        x = query - pvc_sta
        if 0 <= x <= length:
            r.add("q", f"Elevation at chainage {_sta(query)}", elev(x), "m", 3)
        else:
            r.warn("Query chainage lies outside the vertical curve.")
    r.assume("Equal-tangent parabola. Compare K with your agency's minimum K for stopping/passing sight distance (code table - not hardcoded).")
    return r


def esal(aadt, pct_trucks, truck_factor, growth, years, ldf, ddf):
    r = Result("Design ESALs (W18)")
    gf = years if growth == 0 else ((1 + growth / 100) ** years - 1) / (growth / 100)
    w18 = aadt * 365 * pct_trucks / 100 * truck_factor * ddf * ldf * gf
    r.eq("W18 = AADT x 365 x %T x TF x D_D x D_L x GF;   GF = [(1 + g)^n - 1] / g   (AASHTO 1993, Part II)")
    r.add("gf", "Growth factor", gf, "", 2)
    r.add("w18", "Design 18-kip ESALs", w18, "ESAL", 0, primary=True)
    r.assume(f"Directional split D_D = {ddf:g}, lane distribution D_L = {ldf:g}; truck factor must come from your traffic study/WIM data.")
    return r


def flexible(w18, zr, s0, dpsi, mr, a1, a2, m2, d2, a3, m3, d3):
    r = Result("Flexible pavement structural number (AASHTO 1993)")
    mr_psi = mr * MPA_TO_PSI

    def f(sn):
        return (zr * s0 + 9.36 * math.log10(sn + 1) - 0.20
                + math.log10(dpsi / 2.7) / (0.40 + 1094 / (sn + 1) ** 5.19)
                + 2.32 * math.log10(mr_psi) - 8.07)

    target = math.log10(w18)
    lo, hi = 0.5, 15.0
    need(f(hi) >= target, "Required SN exceeds 15 - inputs are outside the equation's practical range.")
    need(f(lo) <= target, "Required SN is below 0.5 (very strong subgrade for this traffic) - the AASHTO equation is not "
                          "meaningful here; use the agency's minimum section.")
    for _ in range(100):
        mid = (lo + hi) / 2
        if f(mid) < target:
            lo = mid
        else:
            hi = mid
    sn = (lo + hi) / 2
    support = a2 * m2 * d2 / 25.4 + a3 * m3 * d3 / 25.4
    d1_in = (sn - support) / a1
    r.eq("log10(W18) = Zr S0 + 9.36 log10(SN+1) - 0.20 + log10[dPSI/(4.2-1.5)] / [0.40 + 1094/(SN+1)^5.19] + 2.32 log10(MR) - 8.07")
    r.eq("SN = a1 D1 + a2 m2 D2 + a3 m3 D3  (D in inches);  solved for SN by bisection")
    r.add("sn", "Required structural number SN", sn, "", 2, primary=True)
    r.add("support", "SN provided by base/subbase", support, "", 2)
    r.add("d1", "Required asphalt thickness D1", max(d1_in, 0) * 25.4, "mm", 0)
    r.check("Base/subbase alone do not exceed required SN", d1_in > 0, "reduce base thickness if not")
    if 0 < d1_in * 25.4 < 75:
        r.warn("Calculated AC thickness is below ~75 mm; check minimum thickness in AASHTO Table 2.4.")
    r.assume(f"Zr = {zr:g}, S0 = {s0:g}, delta-PSI = {dpsi:g}, layer coefficients a1={a1:g}, a2={a2:g}, a3={a3:g}, "
             f"drainage m2={m2:g}, m3={m3:g}. These come from charts/tables - confirm for your materials.")
    r.ref("AASHTO Guide for Design of Pavement Structures (1993), Sec. II.3")
    return r


CALCS = [
    Calculation("hcurve", "Horizontal curve", "T, L, LC, E, M and PC/PT chainages",
                [Param("radius", "Radius R", "m", min=10, max=100000, typical=(30, 5000)),
                 Param("delta", "Deflection angle D (deg or d-m-s)", "deg", min=0, min_exclusive=True, max=180,
                       max_exclusive=True),
                 Param("pi_chainage", "PI chainage", "m", default=1000.0, min=0)],
                hcurve, "Circular curve geometry"),
    Calculation("min_radius", "Minimum curve radius", "Radius from design speed, superelevation and side friction",
                [Param("v", "Design speed V", "km/h", min=10, max=200, typical=(30, 130)),
                 Param("e", "Superelevation e (m/m, % ok)", "", default=0.06, min=0, max=0.2),
                 Param("f", "Side-friction factor f", "", default=0.14, min=0.01, max=0.5, typical=(0.08, 0.4))],
                min_radius, "AASHTO Green Book Eq. 3-8"),
    Calculation("ssd", "Stopping sight distance", "Reaction + braking distance",
                [Param("v", "Design speed V", "km/h", min=10, max=200, typical=(30, 130)),
                 Param("t", "Perception-reaction time", "s", default=2.5, min=0.5, max=5),
                 Param("a", "Deceleration rate", "m/s2", default=3.4, min=1, max=9),
                 Param("grade", "Grade G (+up, -down, in %)", "%", default=0.0, min=-15, max=15)],
                ssd, "AASHTO Green Book Eq. 3-2"),
    Calculation("vcurve", "Vertical curve", "Elevations, K value, high/low point of a parabolic curve",
                [Param("pvi_sta", "PVI chainage", "m", min=0),
                 Param("pvi_elev", "PVI elevation", "m"),
                 Param("g1", "Entry grade g1 (%)", "%", min=-20, max=20, typical=(-12, 12)),
                 Param("g2", "Exit grade g2 (%)", "%", min=-20, max=20, typical=(-12, 12)),
                 Param("length", "Curve length L", "m", min=1, max=5000),
                 Param("query", "Chainage to evaluate", "m", optional=True, min=0)],
                vcurve, "Parabolic vertical curve geometry (AASHTO Green Book Ch. 3)"),
    Calculation("esal", "Design traffic (ESAL)", "18-kip equivalent single axle loads over design life",
                [Param("aadt", "Initial two-way AADT", "veh/day", min=1, max=500000, typical=(100, 100000)),
                 Param("pct_trucks", "Trucks in traffic", "%", min=0, max=100),
                 Param("truck_factor", "Truck factor (ESAL per truck)", "", min=0, min_exclusive=True, max=10,
                       help="From axle-load survey / WIM data - no safe default."),
                 Param("growth", "Annual growth rate", "%", default=3.0, min=0, max=15),
                 Param("years", "Design period", "years", default=20.0, min=1, max=60),
                 Param("ldf", "Lane distribution factor", "", default=0.9, min=0.1, max=1),
                 Param("ddf", "Directional distribution factor", "", default=0.5, min=0.3, max=1)],
                esal, "AASHTO 1993 Guide, Part II"),
    Calculation("flexible", "Flexible pavement SN", "Structural number and asphalt thickness (AASHTO 93)",
                [Param("w18", "Design ESALs W18", "ESAL", min=1e4, max=1e9, typical=(1e5, 2e8)),
                 Param("zr", "Standard normal deviate ZR", "", default=-1.282, min=-3.5, max=0,
                       help="-1.282 = 90% reliability; -1.645 = 95%"),
                 Param("s0", "Overall standard deviation S0", "", default=0.45, min=0.3, max=0.5),
                 Param("dpsi", "Serviceability loss dPSI", "", default=2.0, min=0.5, max=3.5),
                 Param("mr", "Subgrade resilient modulus MR", "MPa", min=10, max=300, typical=(20, 150)),
                 Param("a1", "AC layer coefficient a1", "", default=0.44, min=0.1, max=0.6),
                 Param("a2", "Base layer coefficient a2", "", default=0.14, min=0.05, max=0.25),
                 Param("m2", "Base drainage coefficient m2", "", default=1.0, min=0.4, max=1.4),
                 Param("d2", "Base thickness D2", "mm", default=200.0, min=0, max=1000),
                 Param("a3", "Subbase layer coefficient a3", "", default=0.11, min=0.05, max=0.2),
                 Param("m3", "Subbase drainage coefficient m3", "", default=1.0, min=0.4, max=1.4),
                 Param("d3", "Subbase thickness D3", "mm", default=0.0, min=0, max=1000)],
                flexible, "AASHTO 1993 Eq. 3.1.1"),
]

_R, _D = 300.0, 40.0
CASES = [
    Case("hcurve", {"radius": 300, "delta": 40, "pi_chainage": 1000},
         {"t": 300 * math.tan(math.radians(20)), "l": 300 * math.radians(40),
          "lc": 600 * math.sin(math.radians(20))}, "R=300, D=40"),
    Case("hcurve", {"radius": 300, "delta": 190}, expect_error="Deflection angle"),
    Case("min_radius", {"v": 80, "e": 0.06, "f": 0.14}, {"rmin": 6400 / (127 * 0.20)}, "V^2/127(e+f) = 252 m"),
    Case("ssd", {"v": 80}, {"react": 55.6, "ssd": 128.3}, "80 km/h level, AASHTO params", rel=0.005),
    Case("vcurve", {"pvi_sta": 1000, "pvi_elev": 100, "g1": 3, "g2": -2, "length": 200, "query": 1000},
         {"a": -5.0, "k": 40.0, "e": 1.25, "q": 98.75}, "mid-curve offset E = AL/800"),
    Case("esal", {"aadt": 10000, "pct_trucks": 10, "truck_factor": 1.0, "growth": 0, "years": 20, "ldf": 1, "ddf": 0.5},
         {"w18": 10000 * 365 * 0.1 * 1.0 * 0.5 * 20}, "zero growth"),
    Case("flexible", {"w18": 5e6, "mr": 34.47},
         {"sn": 4.908}, "5M ESAL, MR 5000 psi, 90% rel.; hand back-substitution gives log10 W18 = 6.699", rel=0.005),
]

DISCIPLINE = Discipline("transport", "Transportation and Pavement",
                        "Curves, sight distance, traffic loading, flexible pavement", CALCS, CASES, order=50)
