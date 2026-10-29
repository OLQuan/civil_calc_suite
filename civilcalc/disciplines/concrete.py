"""1. Concrete and Masonry.  Calculation functions are UI-free; units per Param."""
from __future__ import annotations

import math

from ..core import Calculation, Case, Discipline, Param, Result, need


# ---------------------------------------------------------------- volume
def concrete_volume(shape, length, width, thickness, count, wastage):
    r = Result("Concrete volume")
    if shape == "rect":
        v = length * width * thickness
        r.eq("V = L x B x D   (rectangular member: slab, beam, footing, wall)")
    else:
        v = math.pi / 4 * width ** 2 * length
        r.eq("V = pi/4 x d^2 x H   (circular column / pile; 'width' = diameter, 'length' = height)")
    total = v * count
    order = total * (1 + wastage / 100)
    r.add("v_each", "Volume of one member", v, "m3", 3)
    r.add("v_total", "Net volume (all members)", total, "m3", 3)
    r.add("v_order", "Volume to order incl. wastage", order, "m3", 3, primary=True)
    r.assume(f"Wastage/spillage allowance {wastage:g}% (site practice 3-7%); reinforcement volume not deducted.")
    return r


# ---------------------------------------------------------------- mix
def mix_materials(volume, cement_part, sand_part, agg_part, dry_factor,
                  cement_density, bag_mass, wc):
    r = Result("Nominal-mix material quantities")
    s = cement_part + sand_part + agg_part
    dry = volume * dry_factor
    cem_m3 = dry * cement_part / s
    sand_m3 = dry * sand_part / s
    agg_m3 = dry * agg_part / s
    cem_kg = cem_m3 * cement_density
    r.eq("Dry volume = wet volume x dry factor;  material = dry volume x part / sum of parts")
    r.eq("Cement mass = cement volume x bulk density;  water = w/c x cement mass")
    r.add("cement_kg", "Cement", cem_kg, "kg", 1, primary=True)
    r.add("cement_bags", "Cement bags", cem_kg / bag_mass, "bags", 1,
          note=f"{bag_mass:g} kg bags")
    r.add("sand", "Fine aggregate (loose volume)", sand_m3, "m3", 3)
    r.add("agg", "Coarse aggregate (loose volume)", agg_m3, "m3", 3)
    r.add("water", "Mixing water", wc * cem_kg, "L", 0, note=f"w/c = {wc:g}")
    r.assume(f"Dry-volume factor {dry_factor:g} (typical 1.52-1.57); cement bulk density {cement_density:g} kg/m3.")
    r.assume("Aggregates by loose volume, no bulking correction; adjust for moist sand on site.")
    if wc > 0.65:
        r.warn("w/c above 0.65 gives poor durability and strength.")
    return r


# ---------------------------------------------------------------- Ec, fcr
def concrete_properties(fc, wc_density, sd):
    r = Result("Concrete strength and stiffness")
    ec = 0.043 * wc_density ** 1.5 * math.sqrt(fc)
    fr = 0.62 * math.sqrt(fc)
    if sd is not None:
        a = fc + 1.34 * sd
        b = fc + 2.33 * sd - 3.5 if fc <= 35 else fc + 2.33 * sd
        c = 0.9 * fc + 2.33 * sd if fc > 35 else None
        fcr = max(a, b) if fc <= 35 else max(a, c)
        r.eq("f'cr = max(f'c + 1.34 s, f'c + 2.33 s - 3.5)  for f'c <= 35 MPa  (ACI 318-19 Table 26.4.2.1a)")
        basis = f"standard deviation s = {sd:g} MPa"
    else:
        fcr = fc + 7.0 if fc < 21 else (fc + 8.3 if fc <= 35 else 1.10 * fc + 5.0)
        r.eq("No s data: f'cr = f'c+7.0 (<21), f'c+8.3 (21-35), 1.10 f'c+5.0 (>35) MPa  (ACI 318-19 Table 26.4.2.1b)")
        basis = "no site standard-deviation data"
    r.eq("Ec = 0.043 wc^1.5 sqrt(f'c)  [MPa, wc in kg/m3]   fr = 0.62 sqrt(f'c)  (ACI 318-19 19.2.2, 19.2.3)")
    r.add("ec", "Modulus of elasticity Ec", ec, "MPa", 0)
    r.add("fr", "Modulus of rupture fr", fr, "MPa", 2)
    r.add("fcr", "Required average strength f'cr", fcr, "MPa", 1, primary=True, note=basis)
    r.ref("ACI 318-19 Sec. 19.2 and 26.4.2")
    return r


# ---------------------------------------------------------------- beam
def beam_flexure(b, d, h, as_, fc, fy, phi_tc, es):
    r = Result("RC rectangular beam flexure (singly reinforced)")
    b1 = 0.85 if fc <= 28 else max(0.65, 0.85 - 0.05 * (fc - 28) / 7)
    a = as_ * fy / (0.85 * fc * b)
    need(a < d, "Steel area is so large that the stress block exceeds the effective depth; section is not valid.")
    c = a / b1
    need(c < d, "Neutral axis lies below the tension steel (c >= d): the section is over-reinforced beyond the valid range. "
                "Increase the section or reduce As.")
    eps_t = 0.003 * (d - c) / c
    mn = as_ * fy * (d - a / 2) / 1e6
    ey = fy / es
    if eps_t >= ey + 0.003:
        phi, cls = phi_tc, "tension-controlled"
    elif eps_t <= ey:
        phi, cls = 0.65, "compression-controlled"
    else:
        phi = 0.65 + (eps_t - ey) * (phi_tc - 0.65) / 0.003
        cls = "transition"
    rho = as_ / (b * d)
    as_min = max(0.25 * math.sqrt(fc) / fy, 1.4 / fy) * b * d
    r.eq("a = As fy / (0.85 f'c b);  c = a / beta1;  Mn = As fy (d - a/2)")
    r.eq("eps_t = 0.003 (d - c) / c;  phi Mn  (ACI 318-19 Table 21.2.2);  As,min = max(0.25 sqrt(f'c), 1.4) bw d / fy")
    r.add("a", "Stress-block depth a", a, "mm", 1)
    r.add("c", "Neutral axis depth c", c, "mm", 1)
    r.add("eps_t", "Net tensile strain", eps_t, "", 5)
    r.add("section", "Section class", cls, "")
    r.add("phi", "Strength reduction factor phi", phi, "", 3)
    r.add("mn", "Nominal moment Mn", mn, "kN-m", 1)
    r.add("phimn", "Design moment phi Mn", phi * mn, "kN-m", 1, primary=True)
    r.add("rho", "Steel ratio rho", rho, "", 5)
    r.check("As >= As,min", as_ >= as_min, f"As,min = {as_min:.0f} mm2")
    r.check("Tension-controlled (eps_t >= 0.005)", eps_t >= 0.005,
            "ACI 318 beams should satisfy this" if eps_t < 0.005 else "")
    r.check("Depth d < overall depth h", d < h)
    r.assume(f"beta1 = {b1:.3f}; Es = {es:g} MPa; no compression steel; flexure only (shear not checked).")
    r.ref("ACI 318-19 Ch. 9, 21.2, 22.2")
    return r


# ---------------------------------------------------------------- masonry
def masonry_wall(area, openings, bl, bh, bt, joint, mortar_waste, brick_waste):
    net = area - openings
    need(net > 0, "Openings must be smaller than the gross wall area.")
    r = Result("Brick / block masonry quantities")
    per_m2 = 1 / ((bl + joint) * (bh + joint))
    n = net * per_m2 * (1 + brick_waste / 100)
    vol_wall = net * bt
    vol_units = net * per_m2 * bl * bh * bt
    mortar = (vol_wall - vol_units) * (1 + mortar_waste / 100)
    r.eq("Units per m2 = 1 / [(L + j)(H + j)];  Mortar = wall volume - unit volume (+ waste)")
    r.add("per_m2", "Units per m2 of wall face", per_m2, "no./m2", 1)
    r.add("units", "Units required incl. wastage", n, "no.", 0, primary=True)
    r.add("mortar", "Mortar volume incl. wastage", mortar, "m3", 3)
    r.add("net_area", "Net wall area", net, "m2", 2)
    r.assume(f"Single-wythe wall of thickness = unit width; joint {joint*1000:g} mm; "
             f"waste: units {brick_waste:g}%, mortar {mortar_waste:g}%.")
    if mortar_waste < 10:
        r.warn("Mortar wastage below 10% is optimistic; frogged bricks and hollow blocks absorb more mortar.")
    return r


CALCS = [
    Calculation("volume", "Concrete volume", "Volume of slabs, beams, footings, columns incl. wastage",
                [Param("shape", "Shape", kind="choice", default="rect",
                       choices=[("rect", "Rectangular (L x B x D)"), ("circ", "Circular column (diameter x height)")]),
                 Param("length", "Length (or column height)", "m", min=0, min_exclusive=True, typical=(0.1, 100)),
                 Param("width", "Width (or column diameter)", "m", min=0, min_exclusive=True, typical=(0.05, 50)),
                 Param("thickness", "Depth / thickness (rect only)", "m", default=0.15, min=0,
                       min_exclusive=True, typical=(0.05, 5)),
                 Param("count", "Number of identical members", "", "int", default=1, min=1, max=100000),
                 Param("wastage", "Wastage allowance", "%", default=5.0, min=0, max=30)],
                concrete_volume, "Geometry (V = L x B x D)"),
    Calculation("mix", "Nominal mix materials", "Cement, sand, aggregate and water for a 1:m:n mix",
                [Param("volume", "Concrete volume (wet)", "m3", min=0, min_exclusive=True),
                 Param("cement_part", "Cement part", "", default=1.0, min=0, min_exclusive=True),
                 Param("sand_part", "Sand part", "", default=2.0, min=0, min_exclusive=True),
                 Param("agg_part", "Aggregate part", "", default=4.0, min=0, min_exclusive=True),
                 Param("dry_factor", "Dry volume factor", "", default=1.54, min=1.2, max=1.8,
                       help="Wet-to-dry volume factor; 1.52-1.57 typical."),
                 Param("cement_density", "Cement bulk density", "kg/m3", default=1440, min=1000, max=1700),
                 Param("bag_mass", "Cement bag mass", "kg", default=50, min=10, max=100),
                 Param("wc", "Water/cement ratio", "", default=0.5, min=0.25, max=0.9)],
                mix_materials, "Nominal mix proportioning (IS 456 / BS 8500 practice)"),
    Calculation("properties", "Strength & modulus", "Ec, modulus of rupture and required average strength f'cr",
                [Param("fc", "Specified strength f'c", "MPa", min=10, max=120, typical=(17, 70)),
                 Param("wc_density", "Concrete unit mass", "kg/m3", default=2320, min=1440, max=2560,
                       help="2320 = ACI normal-weight default"),
                 Param("sd", "Site standard deviation s", "MPa", optional=True, min=0, max=10,
                       help="Leave blank when no production records exist.")],
                concrete_properties, "ACI 318-19 Sec. 19.2, 26.4.2"),
    Calculation("beam", "RC beam flexure", "Mn and phi*Mn of a singly reinforced rectangular beam",
                [Param("b", "Beam width b", "mm", min=100, max=2000, typical=(150, 800)),
                 Param("d", "Effective depth d", "mm", min=100, max=3000, typical=(200, 1500)),
                 Param("h", "Overall depth h", "mm", min=100, max=3500),
                 Param("as_", "Tension steel area As", "mm2", min=0, min_exclusive=True),
                 Param("fc", "Concrete strength f'c", "MPa", min=17, max=100, typical=(20, 50)),
                 Param("fy", "Steel yield fy", "MPa", default=420, min=240, max=690, typical=(275, 550)),
                 Param("phi_tc", "phi for tension-controlled", "", default=0.9, min=0.65, max=0.9,
                       help="ACI 318-19 value is 0.90; lower it if your national code differs."),
                 Param("es", "Steel modulus Es", "MPa", default=200000, min=190000, max=210000)],
                beam_flexure, "ACI 318-19 Ch. 9, 22.2, 21.2"),
    Calculation("masonry", "Brick / block wall", "Number of units and mortar for a masonry wall",
                [Param("area", "Gross wall area", "m2", min=0, min_exclusive=True),
                 Param("openings", "Openings (doors/windows)", "m2", default=0.0, min=0),
                 Param("bl", "Unit length", "m", default=0.215, min=0.05, max=0.7),
                 Param("bh", "Unit height", "m", default=0.065, min=0.03, max=0.3),
                 Param("bt", "Unit width (wall thickness)", "m", default=0.1025, min=0.05, max=0.5),
                 Param("joint", "Mortar joint thickness", "m", default=0.01, min=0.005, max=0.02),
                 Param("mortar_waste", "Mortar wastage", "%", default=15.0, min=0, max=50),
                 Param("brick_waste", "Unit wastage/breakage", "%", default=5.0, min=0, max=30)],
                masonry_wall, "Geometric take-off"),
]

CASES = [
    Case("volume", {"shape": "rect", "length": 5, "width": 4, "thickness": 0.15},
         {"v_total": 3.0, "v_order": 3.15}, "5 x 4 x 0.15 m slab + 5%"),
    Case("volume", {"length": 5, "width": -1}, expect_error="Width"),
    Case("mix", {"volume": 1},
         {"cement_kg": 316.8, "cement_bags": 6.336, "sand": 0.4400, "agg": 0.8800},
         "1 m3 of 1:2:4, factor 1.54"),
    Case("beam", {"b": 300, "d": 500, "h": 560, "as_": 1500, "fc": 25, "fy": 420},
         {"a": 98.82, "mn": 283.9, "phimn": 255.5, "phi": 0.9}, "ACI hand calc, tension-controlled"),
    Case("beam", {"b": 300, "d": 500, "h": 560, "as_": 1500, "fc": 5, "fy": 420}, expect_error="f'c"),
    Case("properties", {"fc": 30}, {"fcr": 38.3, "ec": (0.043 * 2320 ** 1.5 * math.sqrt(30), 0.001)},
         "no-data f'cr table"),
    Case("masonry", {"area": 10}, {"per_m2": 1 / (0.225 * 0.075)}, "standard brick, 10 mm joints"),
]

DISCIPLINE = Discipline("concrete", "Concrete and Masonry",
                        "Volumes, mixes, RC beam capacity, strength, masonry", CALCS, CASES, order=10)
