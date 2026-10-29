"""2. Earthwork and Excavation."""
from __future__ import annotations

import math

from ..core import Calculation, Case, Discipline, Param, Result, need


def trench(length, width, depth, slope, swell, truck):
    r = Result("Trench / excavation volume and haulage")
    top = width + 2 * slope * depth
    area = (width + slope * depth) * depth
    bank = area * length
    loose = bank * (1 + swell / 100)
    r.eq("A = (b + z d) d   (z = horizontal run per 1 vertical);  V_bank = A x L;  V_loose = V_bank (1 + swell)")
    r.add("top_width", "Top width at ground level", top, "m", 2)
    r.add("area", "Cross-section area", area, "m2", 2)
    r.add("bank", "Bank (in-situ) volume", bank, "m3", 1, primary=True)
    r.add("loose", "Loose volume to haul", loose, "m3", 1)
    r.add("trucks", "Truck loads", math.ceil(loose / truck - 1e-9), "loads", 0, note=f"{truck:g} m3 trucks")
    r.assume(f"Constant section, swell {swell:g}% (clay 20-40%, sand 10-15%, rock 30-60%); truck loose capacity {truck:g} m3.")
    if depth > 1.5:
        r.warn("Excavation deeper than ~1.5 m needs shoring or sloping per local safety regulations (e.g. OSHA 29 CFR 1926 Subpart P).")
    if slope == 0 and depth > 1.2:
        r.warn("Vertical sides at this depth are only valid in competent rock or with trench support.")
    return r


def end_area(areas, spacing):
    need(len(areas) >= 2, "Give at least two cross-section areas.")
    r = Result("Earthwork volume - average end-area method")
    vols = [spacing * (a + b) / 2 for a, b in zip(areas, areas[1:])]
    r.eq("V = sum[ L/2 x (A_i + A_i+1) ]  per station interval (average end area)")
    for i, v in enumerate(vols, 1):
        r.add(f"v{i}", f"Interval {i}", v, "m3", 1)
    r.add("total", "Total volume", sum(vols), "m3", 1, primary=True)
    r.add("length", "Length covered", spacing * (len(areas) - 1), "m", 1)
    r.assume("Equal station spacing; average end area overestimates slightly vs. prismoidal formula when areas differ greatly.")
    return r


def balance(cut, fill, shrink, swell):
    r = Result("Cut / fill balance")
    cut_avail = cut * (1 - shrink / 100)
    net = cut_avail - fill
    r.eq("Compacted volume from cut = V_cut (1 - shrinkage);  surplus/deficit = that - V_fill")
    r.add("cut_comp", "Compacted volume available from cut", cut_avail, "m3", 1)
    if net >= 0:
        bank = net / (1 - shrink / 100)
        r.add("surplus_bank", "Surplus to waste (bank volume)", bank, "m3", 1, primary=True)
        r.add("surplus_loose", "Surplus to haul (loose volume)", bank * (1 + swell / 100), "m3", 1)
        r.add("borrow", "Borrow required (bank volume)", 0.0, "m3", 1)
    else:
        r.add("surplus_bank", "Surplus to waste (bank volume)", 0.0, "m3", 1)
        r.add("surplus_loose", "Surplus to haul (loose volume)", 0.0, "m3", 1)
        r.add("borrow", "Borrow required (bank volume)", -net / (1 - shrink / 100), "m3", 1, primary=True)
    r.assume(f"Shrinkage {shrink:g}% (bank to compacted), swell {swell:g}% (bank to loose); typical soil values vary - use site data.")
    return r


def field_density(rho_wet, w, rho_dmax, min_rc):
    r = Result("Field compaction check")
    rho_d = rho_wet / (1 + w / 100)
    rc = 100 * rho_d / rho_dmax
    r.eq("rho_d = rho_wet / (1 + w);  RC = rho_d / rho_d,max x 100   (ASTM D698/D1557 reference)")
    r.add("rho_d", "Dry density", rho_d, "kg/m3", 0)
    r.add("rc", "Relative compaction", rc, "%", 1, primary=True)
    r.check(f"RC >= {min_rc:g}% specified", rc >= min_rc)
    if rc > 105:
        r.warn("RC above 105% is unusual - verify the Proctor maximum and the field test.")
    r.assume(f"Specified minimum relative compaction {min_rc:g}% (typically 90-98%; check the contract spec).")
    return r


CALCS = [
    Calculation("trench", "Trench / pit volume", "Excavation volume, loose volume and truck loads",
                [Param("length", "Length", "m", min=0, min_exclusive=True),
                 Param("width", "Bottom width", "m", min=0, min_exclusive=True, typical=(0.3, 30)),
                 Param("depth", "Depth", "m", min=0, min_exclusive=True, max=60, typical=(0.2, 6)),
                 Param("slope", "Side slope z (H per 1 V; 0 = vertical)", "", default=0.0, min=0, max=5),
                 Param("swell", "Swell factor", "%", default=25.0, min=0, max=100),
                 Param("truck", "Truck capacity (loose)", "m3", default=10.0, min=1, max=60)],
                trench, "Geometry; OSHA 29 CFR 1926 Subpart P for safety"),
    Calculation("end_area", "Average end-area volume", "Volume from successive cross-section areas",
                [Param("areas", "Cross-section areas (comma separated)", "m2", "floatlist", min=0, min_items=2),
                 Param("spacing", "Station spacing", "m", default=20.0, min=0, min_exclusive=True)],
                end_area, "Average end-area method (road/canal earthwork)"),
    Calculation("balance", "Cut / fill balance", "Surplus to waste or borrow needed, with swell and shrink",
                [Param("cut", "Total cut (bank volume)", "m3", min=0),
                 Param("fill", "Total fill (compacted volume)", "m3", min=0),
                 Param("shrink", "Shrinkage (bank -> compacted)", "%", default=10.0, min=0, max=40),
                 Param("swell", "Swell (bank -> loose)", "%", default=25.0, min=0, max=100)],
                balance, "Mass-haul practice"),
    Calculation("compaction", "Field compaction check", "Dry density and % compaction vs Proctor maximum",
                [Param("rho_wet", "Field wet (bulk) density", "kg/m3", min=1000, max=3000, typical=(1600, 2400)),
                 Param("w", "Field moisture content", "%", min=0, max=60, typical=(3, 25)),
                 Param("rho_dmax", "Proctor max dry density", "kg/m3", min=1000, max=2800, typical=(1500, 2300)),
                 Param("min_rc", "Specified minimum compaction", "%", default=95.0, min=80, max=100)],
                field_density, "ASTM D698 / D1557, D1556 / D6938"),
]

CASES = [
    Case("trench", {"length": 100, "width": 1, "depth": 2, "slope": 1},
         {"area": 6.0, "bank": 600.0, "loose": 750.0, "trucks": 75}, "(1+1x2)x2 = 6 m2"),
    Case("trench", {"length": 100, "width": 1, "depth": -2}, expect_error="Depth"),
    Case("end_area", {"areas": "10,12,14", "spacing": 20}, {"total": 480.0}, "220 + 260"),
    Case("balance", {"cut": 1000, "fill": 800},
         {"cut_comp": 900.0, "surplus_bank": 100 / 0.9, "surplus_loose": 100 / 0.9 * 1.25}, "surplus case"),
    Case("balance", {"cut": 500, "fill": 900}, {"borrow": 450 / 0.9}, "borrow case: 500x0.9=450 vs 900 fill"),
    Case("compaction", {"rho_wet": 2000, "w": 10, "rho_dmax": 1900}, {"rho_d": 1818.18, "rc": 95.69}, "RC check"),
]

DISCIPLINE = Discipline("earthwork", "Earthwork and Excavation",
                        "Trench volumes, end-area, cut/fill balance, compaction", CALCS, CASES, order=20)
