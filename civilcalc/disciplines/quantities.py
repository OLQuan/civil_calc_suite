"""8. Quantity Estimation (take-off helpers and cost roll-up)."""
from __future__ import annotations

import math

from ..core import Calculation, Case, Discipline, Param, Result, need

STEEL_DENSITY = 7850.0   # kg/m3


def rebar(dia, length, count, concrete_vol):
    r = Result("Reinforcement weight")
    per_m = math.pi / 4 * (dia / 1000) ** 2 * STEEL_DENSITY
    total_len = length * count
    wt = per_m * total_len
    r.eq("w = (pi/4) d^2 rho_s = d^2 / 162.2 kg/m  (d in mm, rho_s = 7850 kg/m3);  W = w x length x number")
    r.add("per_m", "Unit weight", per_m, "kg/m", 3)
    r.add("len", "Total length", total_len, "m", 1)
    r.add("weight", "Total weight", wt, "kg", 1, primary=True)
    r.add("weight_t", "Total weight", wt / 1000, "t", 3)
    if concrete_vol is not None:
        r.add("kg_m3", "Steel per m3 of concrete", wt / concrete_vol, "kg/m3", 1)
    r.assume("Nominal diameter; laps, hooks and wastage (add 3-5%) are NOT included - include them in 'total length'.")
    return r


def plaster(area, thick, cement_part, sand_part, dry_factor, waste):
    r = Result("Plaster / screed mortar quantities")
    wet = area * thick / 1000
    dry = wet * dry_factor * (1 + waste / 100)
    s = cement_part + sand_part
    cem = dry * cement_part / s
    r.eq("Dry volume = wet volume x dry factor x (1 + waste);  cement = dry x c/(c+s) x 1440 kg/m3")
    r.add("wet", "Wet mortar volume", wet, "m3", 3)
    r.add("cement_kg", "Cement", cem * 1440, "kg", 0, primary=True)
    r.add("cement_bags", "Cement (50 kg bags)", cem * 1440 / 50, "bags", 1)
    r.add("sand", "Sand", dry * sand_part / s, "m3", 3)
    r.assume(f"Dry-volume factor {dry_factor:g} (1.25-1.35 for mortar), waste {waste:g}%, cement bulk density 1440 kg/m3.")
    return r


def tiles(area, tl, tw, joint, waste):
    r = Result("Floor/wall tile count")
    each = (tl + joint) * (tw + joint)
    n = area / each * (1 + waste / 100)
    r.eq("N = A / [(L + j)(W + j)] x (1 + waste)")
    r.add("n", "Tiles required", math.ceil(n - 1e-9), "no.", 0, primary=True)
    r.add("net", "Tiles without waste", area / each, "no.", 1)
    r.assume(f"Waste/cutting allowance {waste:g}% (5% straight lay, 10-15% diagonal or patterned).")
    return r


def paint(area, coats, coverage, openings):
    net = area - openings
    need(net > 0, "Openings must be smaller than the painted area.")
    r = Result("Paint quantity")
    litres = net * coats / coverage
    r.eq("V = net area x coats / spreading rate")
    r.add("net", "Net painted area", net, "m2", 1)
    r.add("litres", "Paint required", litres, "L", 1, primary=True)
    r.assume(f"Spreading rate {coverage:g} m2/L per coat (take from the product data sheet; rough surfaces give less).")
    return r


def road_layer(length, width, thick, density, loose_factor, compaction):
    r = Result("Road layer quantity")
    vol = length * width * thick
    mass = vol * density
    r.eq("V = L x W x t;  mass = V x compacted density;  loose volume = V x (1 + compaction allowance) x loose-volume factor")
    r.add("vol", "Compacted volume", vol, "m3", 1)
    r.add("mass", "Mass required", mass, "t", 1, primary=True)
    r.add("loose", "Loose volume to deliver", vol * (1 + compaction / 100) * loose_factor, "m3", 1)
    r.assume(f"Compacted density {density:g} t/m3 (asphalt ~2.35, granular base ~2.1-2.3); compaction allowance {compaction:g}%.")
    return r


def boq(qty, rate, contingency, overhead, tax):
    need(len(qty) == len(rate), f"{len(qty)} quantities but {len(rate)} rates - give one rate per quantity.")
    r = Result("Cost roll-up")
    items = [q * p for q, p in zip(qty, rate)]
    sub = sum(items)
    c = sub * contingency / 100
    o = (sub + c) * overhead / 100
    t = (sub + c + o) * tax / 100
    r.eq("Subtotal = sum(Q x rate);  + contingency;  + overhead & profit on (sub + cont);  + tax on the total")
    for i, v in enumerate(items, 1):
        r.add(f"i{i}", f"Item {i}", v, "", 2)
    r.add("sub", "Direct cost subtotal", sub, "", 2)
    r.add("cont", "Contingency", c, "", 2)
    r.add("oh", "Overhead and profit", o, "", 2)
    r.add("tax", "Tax / VAT", t, "", 2)
    r.add("total", "TOTAL", sub + c + o + t, "", 2, primary=True)
    r.assume("Currency-neutral; quantities and rates must use matching units. Markups compound in the order shown.")
    return r


CALCS = [
    Calculation("rebar", "Reinforcement weight", "Steel weight from bar diameter, length and count",
                [Param("dia", "Bar diameter", "mm", min=6, max=60, typical=(8, 40)),
                 Param("length", "Length per bar", "m", min=0, min_exclusive=True, max=100),
                 Param("count", "Number of bars", "", "int", default=1, min=1, max=1000000),
                 Param("concrete_vol", "Concrete volume (for kg/m3)", "m3", optional=True, min=0, min_exclusive=True)],
                rebar, "w = d^2/162.2 kg/m"),
    Calculation("plaster", "Plaster / screed", "Cement and sand for plaster or screed",
                [Param("area", "Area", "m2", min=0, min_exclusive=True),
                 Param("thick", "Thickness", "mm", default=12.0, min=3, max=100),
                 Param("cement_part", "Cement part", "", default=1.0, min=0, min_exclusive=True),
                 Param("sand_part", "Sand part", "", default=4.0, min=0, min_exclusive=True),
                 Param("dry_factor", "Dry volume factor", "", default=1.27, min=1.1, max=1.5),
                 Param("waste", "Wastage", "%", default=10.0, min=0, max=40)],
                plaster, "Standard take-off practice"),
    Calculation("tiles", "Tiles", "Number of tiles for an area",
                [Param("area", "Area to tile", "m2", min=0, min_exclusive=True),
                 Param("tl", "Tile length", "m", default=0.6, min=0.05, max=3),
                 Param("tw", "Tile width", "m", default=0.6, min=0.05, max=3),
                 Param("joint", "Joint width", "m", default=0.003, min=0, max=0.02),
                 Param("waste", "Wastage", "%", default=7.0, min=0, max=30)],
                tiles, "Standard take-off practice"),
    Calculation("paint", "Paint", "Litres of paint for an area and number of coats",
                [Param("area", "Surface area", "m2", min=0, min_exclusive=True),
                 Param("openings", "Openings to deduct", "m2", default=0.0, min=0),
                 Param("coats", "Number of coats", "", "int", default=2, min=1, max=6),
                 Param("coverage", "Spreading rate per coat", "", default=10.0, min=2, max=30,
                       help="Spreading rate in m2 per litre per coat, from the data sheet.")],
                paint, "Manufacturer coverage"),
    Calculation("road_layer", "Road layer material", "Volume and tonnage of a pavement layer",
                [Param("length", "Length", "m", min=0, min_exclusive=True),
                 Param("width", "Width", "m", min=0, min_exclusive=True, max=100),
                 Param("thick", "Compacted thickness", "m", min=0.01, max=2, typical=(0.03, 0.6)),
                 Param("density", "Compacted density", "", default=2.35, min=1.2, max=3.0,
                       help="Compacted density in tonnes per m3."),
                 Param("loose_factor", "Loose-volume factor", "", default=1.0, min=0.8, max=1.5),
                 Param("compaction", "Compaction allowance", "%", default=20.0, min=0, max=50)],
                road_layer, "Pavement take-off practice"),
    Calculation("boq", "Cost roll-up (BOQ)", "Quantities x rates with contingency, overhead and tax",
                [Param("qty", "Item quantities (comma separated)", "", "floatlist", min=0, min_items=1),
                 Param("rate", "Unit rates (same order)", "", "floatlist", min=0, min_items=1),
                 Param("contingency", "Contingency", "%", default=5.0, min=0, max=50),
                 Param("overhead", "Overhead and profit", "%", default=10.0, min=0, max=60),
                 Param("tax", "Tax / VAT", "%", default=0.0, min=0, max=40)],
                boq, "Cost estimating practice"),
]

CASES = [
    Case("rebar", {"dia": 16, "length": 12, "count": 10}, {"per_m": 1.578, "weight": 189.4}, "16 mm bars", rel=0.002),
    Case("plaster", {"area": 100, "thick": 12, "waste": 0}, {"wet": 1.2, "cement_kg": 1.2 * 1.27 / 5 * 1440},
         "1:4, 12 mm"),
    Case("tiles", {"area": 20, "tl": 0.6, "tw": 0.6, "joint": 0, "waste": 5}, {"n": 59}, "20/0.36 x 1.05 = 58.3"),
    Case("paint", {"area": 100, "openings": 10, "coats": 2}, {"litres": 18.0}, "90 x 2 / 10"),
    Case("road_layer", {"length": 1000, "width": 7, "thick": 0.05}, {"vol": 350.0, "mass": 822.5}, "AC wearing course"),
    Case("boq", {"qty": "10, 20", "rate": "5, 2", "contingency": 5, "overhead": 10, "tax": 7.5},
         {"sub": 90.0, "total": 111.746}, "compounded markups", rel=0.0005),
    Case("boq", {"qty": "10, 20", "rate": "5"}, expect_error="one rate"),
]

DISCIPLINE = Discipline("quantities", "Quantity Estimation",
                        "Rebar, finishes, road layers, cost roll-up", CALCS, CASES, order=80)
