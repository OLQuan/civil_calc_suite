"""Independent verification of civilcalc.

Every expected number here is a literal taken from a textbook table, a published
conversion factor, or a hand calculation - NOT recomputed with the module's own
formula.  (The worked examples shipped inside each discipline module, run by
`python -m civilcalc test`, are the quick user-facing check; this file is the
engineering audit of them.)

Run:   python -m unittest discover -s tests -v      (pytest also works)
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from civilcalc import cli, registry, selftest, units          # noqa: E402
from civilcalc.core import InputError                         # noqa: E402


def run(disc, calc, **inputs):
    for d in registry.load():
        if d.key == disc:
            return d.get(calc).run({k: str(v) for k, v in inputs.items()})
    raise KeyError(disc)


class Approx(unittest.TestCase):
    def close(self, got, want, rel=0.002, msg=""):
        self.assertAlmostEqual(got, want, delta=abs(want) * rel + 1e-12, msg=msg)


# ---------------------------------------------------------------- units
class TestUnits(Approx):
    def test_published_factors(self):
        c = units.convert
        self.close(c(1, "in", "mm"), 25.4, 1e-9)
        self.close(c(1, "kip", "kN"), 4.4482216, 1e-6)
        self.close(c(1, "psi", "kPa"), 6.894757, 1e-6)
        self.close(c(4000, "psi", "MPa"), 27.579, 1e-4)
        self.close(c(1, "ft3", "L"), 28.316847, 1e-6)
        self.close(c(1, "acre", "ha"), 0.404686, 1e-5)
        self.close(c(1, "mgd", "L/s"), 43.8126, 1e-5)
        self.close(c(1, "gal", "L"), 3.785412, 1e-6)
        self.close(c(1, "kip-ft", "kN-m"), 1.355818, 1e-6)
        self.close(c(1, "pcf", "kN/m3"), 0.157087, 1e-5)
        self.close(c(60, "mph", "km/h"), 96.56064, 1e-7)

    def test_temperature_offsets(self):
        self.close(units.convert(100, "degF", "degC"), 37.7778, 1e-5)
        self.close(units.convert(0, "degC", "K"), 273.15, 1e-9)
        self.close(units.convert(-40, "degC", "degF"), -40.0, 1e-9)

    def test_round_trip(self):
        for u, v in (("ft", "m"), ("psi", "kPa"), ("cfs", "L/s"), ("lbf", "kN"), ("yd3", "m3")):
            self.close(units.convert(units.convert(123.456, u, v), v, u), 123.456, 1e-12)

    def test_incompatible_and_unknown(self):
        with self.assertRaises(units.UnitError):
            units.convert(1, "ft", "MPa")
        with self.assertRaises(units.UnitError):
            units.convert(1, "cubit", "m")

    def test_text_parsing(self):
        self.close(units.parse_quantity("30 ft", "m"), 9.144, 1e-9)
        self.close(units.parse_quantity("5'6\"", "m"), 1.6764, 1e-9)
        self.close(units.parse_quantity("4,000 psi", "MPa"), 27.579, 1e-4)
        self.close(units.parse_quantity("6%", "-"), 0.06, 1e-12)
        self.close(units.parse_quantity("45-30-15", "deg"), 45.504167, 1e-6)
        self.close(units.parse_quantity("12", "m"), 12.0, 1e-12)     # bare number = target unit
        with self.assertRaises(units.UnitError):
            units.parse_quantity("abc", "m")
        with self.assertRaises(units.UnitError):
            units.parse_quantity("45-75-10", "deg")                  # minutes >= 60


# ---------------------------------------------------------------- input validation
class TestValidation(unittest.TestCase):
    def test_non_physical_rejected_not_computed(self):
        with self.assertRaisesRegex(InputError, "greater than 0"):
            run("concrete", "volume", length=5, width=-1)
        with self.assertRaisesRegex(InputError, "at least"):
            run("concrete", "beam", b=300, d=500, h=560, as_=1500, fc=5)
        with self.assertRaisesRegex(InputError, "whole number"):
            run("concrete", "volume", length=5, width=4, count=2.5)

    def test_all_problems_reported_together(self):
        with self.assertRaisesRegex(InputError, "2 input problems"):
            run("concrete", "volume", length=-1, width=-1)

    def test_missing_required(self):
        with self.assertRaisesRegex(InputError, "required"):
            run("earthwork", "trench", width=1, depth=1)

    def test_unknown_input_name(self):
        with self.assertRaisesRegex(InputError, "Unknown input"):
            run("earthwork", "trench", length=1, width=1, depth=1, bogus=3)

    def test_soft_range_warns_but_computes(self):
        r = run("earthwork", "compaction", rho_wet=2000, w=45, rho_dmax=1900)
        self.assertTrue(any("typical range" in w for w in r.warnings))

    def test_defaults_are_declared(self):
        r = run("concrete", "volume", length=5, width=4)
        self.assertTrue(any("Default used" in a for a in r.assumptions))

    def test_every_result_states_its_basis(self):
        """Each calculation must show equation(s) and at least one reference."""
        for d in registry.load():
            for case in d.cases:
                if case.expect_error:
                    continue
                r = d.get(case.calc).run(case.inputs)
                self.assertTrue(r.equations, f"{d.key}.{case.calc}: no governing equation shown")
                self.assertTrue(r.references, f"{d.key}.{case.calc}: no standard/reference shown")


# ---------------------------------------------------------------- hand-calculated answers
class TestConcrete(Approx):
    def test_slab_volume(self):
        r = run("concrete", "volume", length="20 ft", width=5, thickness="150 mm", wastage=0)
        self.close(r["v_total"], 6.096 * 5 * 0.15)                     # 4.572 m3

    def test_beam_aci(self):
        # a = 1500*420/(0.85*25*300) = 98.82 ; Mn = 1500*420*(500-49.41) = 283.9 kN-m ; eps_t>0.005 => phi 0.9
        r = run("concrete", "beam", b=300, d=500, h=560, as_=1500, fc=25, fy=420)
        self.close(r["a"], 98.82, 0.001)
        self.close(r["mn"], 283.9, 0.001)
        self.close(r["phimn"], 255.5, 0.001)
        self.assertEqual(r["section"], "tension-controlled")

    def test_beam_over_reinforced_rejected(self):
        with self.assertRaises(InputError):
            run("concrete", "beam", b=200, d=300, h=350, as_=9000, fc=20, fy=420)

    def test_beta1_high_strength(self):
        # f'c = 56 MPa -> beta1 = 0.85 - 0.05*(56-28)/7 = 0.65
        r = run("concrete", "beam", b=300, d=500, h=560, as_=1500, fc=56, fy=420)
        self.assertIn("beta1 = 0.650", " ".join(r.assumptions))

    def test_mix_1_2_4(self):
        # 1 m3 wet: dry 1.54 m3 ; cement 1.54/7 = 0.22 m3 x 1440 = 316.8 kg
        r = run("concrete", "mix", volume=1)
        self.close(r["cement_kg"], 316.8, 1e-4)
        self.close(r["sand"], 0.44, 1e-3)
        self.close(r["agg"], 0.88, 1e-3)

    def test_ec_and_fr(self):
        # Ec = 4700 sqrt(f'c) is the usual shorthand; 0.043 wc^1.5 sqrt(fc) at 2320 -> 4796 MPa for 30 MPa
        r = run("concrete", "properties", fc=30)
        self.close(r["ec"], 0.043 * 2320 ** 1.5 * 30 ** 0.5, 1e-6)
        self.close(r["ec"], 4700 * 30 ** 0.5, 0.03)                    # within 3% of the familiar 4700 sqrt(f'c)
        self.close(r["fr"], 3.396, 0.001)                              # 0.62 sqrt(30)
        self.close(r["fcr"], 38.3, 1e-3)                               # f'c + 8.3 (ACI Table 26.4.2.1b)

    def test_fcr_with_standard_deviation(self):
        # f'c 30, s 4: max(30+1.34*4, 30+2.33*4-3.5) = max(35.36, 35.82)
        r = run("concrete", "properties", fc=30, sd=4)
        self.close(r["fcr"], 35.82, 1e-3)

    def test_brick_count_per_m2(self):
        r = run("concrete", "masonry", area=10, brick_waste=0)
        self.close(r["per_m2"], 59.26, 0.001)                          # 215x65 brick, 10 mm joints: ~60/m2 textbook


class TestEarthwork(Approx):
    def test_trench(self):
        r = run("earthwork", "trench", length=100, width=1, depth=2, slope=1, swell=25, truck=10)
        self.close(r["area"], 6.0, 1e-9)
        self.close(r["bank"], 600.0, 1e-9)
        self.close(r["loose"], 750.0, 1e-9)
        self.assertEqual(r["trucks"], 75)

    def test_end_area_unequal(self):
        r = run("earthwork", "end_area", areas="0, 30, 50, 20", spacing=20)
        self.close(r["total"], 20 * (15 + 40 + 35), 1e-9)              # 1800 m3

    def test_balance_borrow(self):
        r = run("earthwork", "balance", cut=500, fill=900, shrink=10)
        self.close(r["borrow"], 500.0, 1e-9)                           # need 900 compacted, cut gives 450 -> 450/0.9


class TestSurveying(Approx):
    def test_levelling_arithmetic_check(self):
        r = run("surveying", "levelling", rl0=100, bs="1.5, 1.2", fs="0.9, 2.1")
        self.close(r["final"], 99.7, 1e-9)
        self.assertTrue(all(ok for _l, ok, _d in r.checks))

    def test_levelling_misclosure_tolerance(self):
        r = run("surveying", "levelling", rl0=100, bs="1.5, 1.2", fs="0.9, 2.1", closing_rl=99.69, dist_km=4, k=12)
        self.close(r["misclosure"], 10.0, 1e-6)
        self.close(r["tolerance"], 24.0, 1e-9)                         # 12 sqrt(4)

    def test_traverse_bowditch_with_error(self):
        # hand calc in the test notes: closure error 2 m on a 398 m perimeter, adjusted area 9899.5 m2
        r = run("surveying", "traverse", bearings="0,90,180,270", dists="100,100,98,100")
        self.close(r["sum_lat"], 2.0, 1e-9)
        self.close(r["misclosure"], 2.0, 1e-9)
        self.close(r["precision"], 199.0, 1e-9)
        self.close(r["area"], 9899.5, 1e-5)

    def test_inverse_quadrants(self):
        self.close(run("surveying", "inverse", x1=0, y1=0, x2=-30, y2=-40)["az"], 216.8699, 1e-6)
        self.close(run("surveying", "inverse", x1=0, y1=0, x2=-40, y2=30)["az"], 306.8699, 1e-6)

    def test_dms_never_prints_60_seconds(self):
        self.assertEqual(run("surveying", "inverse", x1=0, y1=0, x2=0, y2=1)["az_dms"], "0°00'00.0\"")
        from civilcalc.disciplines.surveying import _dms
        self.assertNotIn("60.0", _dms(44.99999999))


class TestStructural(Approx):
    def test_udl_beam(self):
        # w=10 kN/m, L=6 m, EI = 2e5*5e8 : M = 45, V = 30, y = 5wL^4/384EI = 1.6875 mm
        r = run("structural", "beam", span=6, w=10, i=5e8)
        self.close(r["mmax"], 45.0, 1e-4)
        self.close(r["vmax"], 30.0, 1e-4)
        self.close(r["dmax"], 1.6875, 1e-3)

    def test_point_load_off_centre(self):
        # P=30 kN at a=2 m on L=6: Ra = 20, Rb = 10, Mmax = 40 kN-m under the load (exact)
        r = run("structural", "beam", span=6, p=30, a=2, i=5e8)
        self.close(r["ra"], 20.0, 1e-9)
        self.close(r["rb"], 10.0, 1e-9)
        self.close(r["mmax"], 40.0, 1e-9)

    def test_point_load_between_grid_samples(self):
        # a = 1.3337 m is not on the sampling grid; Mmax = P a b / L must still be exact
        a, L, P = 1.3337, 6.0, 30.0
        r = run("structural", "beam", span=L, p=P, a=a, i=5e8)
        self.close(r["mmax"], 30.0 * 1.3337 * (6 - 1.3337) / 6.0, 1e-9)

    def test_column(self):
        # P0 = 0.85*30*(160000-1600)+420*1600 = 4,711,200 N ; 0.65*0.8*P0 = 2449.8 kN
        r = run("structural", "column", b=400, h=400, ast=1600, fc=30)
        self.close(r["phipn"], 2449.8, 1e-3)

    def test_load_combinations_asce7(self):
        r = run("structural", "combos", d=10, l=5, s=4, w=20)
        self.close(r["c1"], 14.0, 1e-9)
        self.close(r["c2"], 12 + 8 + 2, 1e-9)                          # 1.2D+1.6L+0.5S
        self.close(r["c3"], 12 + 6.4 + 10, 1e-9)                       # 1.2D+1.6S+max(L,0.5W) -> 0.5W = 10 governs
        self.close(r["c4"], 12 + 20 + 5 + 2, 1e-9)                     # 1.2D+W+L+0.5S
        self.close(r["c6"], 9 + 20, 1e-9)                              # 0.9D+W

    def test_uplift_reported(self):
        r = run("structural", "combos", d=10, w=-30)
        self.close(r["low"], -21.0, 1e-9)
        self.assertTrue(any("uplift" in w for w in r.warnings))

    def test_min_thickness(self):
        self.close(run("structural", "min_h", span=6, member="beam", support="both_ends")["h"], 6000 / 21, 1e-6)

    def test_steel_beam(self):
        r = run("structural", "steel_beam", zx=1.6e6, ry=30, aw=3000, lb=1.0, fy=345)
        self.close(r["mp"], 552.0, 1e-9)
        self.close(r["phimn"], 496.8, 1e-9)
        self.close(r["phivn"], 621.0, 1e-9)                            # 1.0*0.6*345*3000


class TestTransport(Approx):
    def test_horizontal_curve(self):
        # R=300, D=40 deg: T=109.19, L=209.44, LC=205.28, E=R(sec20-1)=19.2 ... PC = 1000-109.19
        r = run("transport", "hcurve", radius=300, delta=40, pi_chainage=1000)
        self.close(r["t"], 109.191, 1e-4)
        self.close(r["l"], 209.440, 1e-4)
        self.close(r["lc"], 205.212, 1e-4)
        self.assertEqual(r["pc"], "0+890.81")
        self.assertEqual(r["pt"], "1+100.25")

    def test_ssd_aashto_80kmh(self):
        # 0.278*80*2.5 = 55.6 ; 80^2/(254*(3.4/9.81)) = 72.7 ; AASHTO Table 3-1 gives ~130 m
        r = run("transport", "ssd", v=80)
        self.close(r["ssd"], 128.3, 0.005)

    def test_ssd_downhill_longer_uphill_shorter(self):
        self.assertGreater(run("transport", "ssd", v=80, grade=-6)["ssd"], run("transport", "ssd", v=80)["ssd"])
        self.assertLess(run("transport", "ssd", v=80, grade=6)["ssd"], run("transport", "ssd", v=80)["ssd"])

    def test_min_radius(self):
        self.close(run("transport", "min_radius", v=80, e="6%", f=0.14)["rmin"], 6400 / (127 * 0.20), 1e-6)

    def test_vertical_curve(self):
        r = run("transport", "vcurve", pvi_sta=1000, pvi_elev=100, g1=3, g2=-2, length=200, query=1000)
        self.close(r["k"], 40.0, 1e-9)
        self.close(r["e"], 1.25, 1e-9)
        self.close(r["q"], 98.75, 1e-9)
        self.assertIn("0+900.00", r["pvc"])
        self.assertIn("97.000", r["pvc"])
        # high point x = -g1 L/A = 120 m past the PVC (chainage 900) -> 1+020 ; y = 97 + 3.6 - 1.8 = 98.80
        self.assertEqual(r["turn"], "1+020.00  /  98.800 m")

    def test_esal_growth_factor(self):
        # g=3%, n=20: GF = (1.03^20 - 1)/0.03 = 26.870
        r = run("transport", "esal", aadt=10000, pct_trucks=10, truck_factor=1.0, growth=3, years=20, ldf=1, ddf=0.5)
        self.close(r["gf"], 26.870, 1e-4)
        self.close(r["w18"], 10000 * 365 * 0.1 * 0.5 * 26.870374, 1e-5)

    def test_aashto93_sn_roundtrip(self):
        """Feed the solved SN back into the AASHTO equation: must give back log10(W18)."""
        import math
        r = run("transport", "flexible", w18=5e6, mr=34.47, zr=-1.282, s0=0.45, dpsi=2.0)
        sn, mr = r["sn"], 34.47 * 145.0377
        lhs = (-1.282 * 0.45 + 9.36 * math.log10(sn + 1) - 0.2
               + math.log10(2.0 / 2.7) / (0.4 + 1094 / (sn + 1) ** 5.19) + 2.32 * math.log10(mr) - 8.07)
        self.close(lhs, math.log10(5e6), 1e-4)
        self.assertTrue(3.5 < sn < 6.5)                                # sane for 5M ESAL on a 5 ksi subgrade


class TestHydraulics(Approx):
    def test_manning_rectangular(self):
        # R = 2/(2+2)=0.5 ; Q = (1/0.013)*2*0.5^(2/3)*sqrt(0.001) = 3.0647 m3/s
        r = run("hydraulics", "manning", shape="rect", width=2, n=0.013, slope=0.001, depth=1)
        self.close(r["q"], 3.0647, 1e-4)
        self.close(r["v"], 1.5324, 1e-4)

    def test_manning_normal_depth_roundtrip(self):
        r = run("hydraulics", "manning", shape="trap", width=3, z=2, n=0.025, slope="0.05%", q=5)
        back = run("hydraulics", "manning", shape="trap", width=3, z=2, n=0.025, slope="0.05%", depth=r["y"])
        self.close(back["q"], 5.0, 1e-6)

    def test_circular_pipe_half_full_is_half_of_full(self):
        # classic result: Q(y/D = 0.5) = Q_full / 2 ;  D=1 m, n=.013, S=.001 -> Qfull = 0.7582 m3/s
        r = run("hydraulics", "manning", shape="circ", dia=1, n=0.013, slope=0.001, depth=0.5)
        self.close(r["qfull"], 0.7582, 1e-3)
        self.close(r["q"], 0.3791, 1e-3)

    def test_full_pipe_has_no_froude_crash(self):
        r = run("hydraulics", "manning", shape="circ", dia=1, n=0.013, slope=0.001, depth=1)
        self.assertIn("n/a", r["fr"])

    def test_pipe_loss_hazen_williams(self):
        # 10.67*1000*0.1^1.852/(120^1.852*0.3^4.87) = 7.45 m
        self.close(run("hydraulics", "pipe_loss", length=1000, dia=0.3, q=0.1)["hf"], 7.45, 0.005)

    def test_darcy_laminar_rejected(self):
        with self.assertRaisesRegex(InputError, "turbulent"):
            run("hydraulics", "pipe_loss", method="dw", length=100, dia=0.05, q=0.00001)

    def test_rational(self):
        # Cw = (2*0.9+3*0.5)/5 = 0.66 ; Q = 0.66*100*5/360 = 0.9167 m3/s
        r = run("hydraulics", "rational", areas="2,3", cs="0.9,0.5", intensity=100)
        self.close(r["cw"], 0.66, 1e-9)
        self.close(r["q"], 0.9167, 1e-4)

    def test_rational_zero_area_rejected(self):
        with self.assertRaises(InputError):
            run("hydraulics", "rational", areas="0", cs="0.5", intensity=100)

    def test_weir_orifice_pump(self):
        self.close(run("hydraulics", "weir", length=2, head=0.3)["q"], 0.6016, 1e-3)
        self.close(run("hydraulics", "orifice", area=0.05, head=2)["q"], 0.1910, 1e-3)
        self.close(run("hydraulics", "pump", q=0.05, head=30, eff="70%")["shaft"], 21.01, 1e-3)

    def test_kirpich(self):
        self.close(run("hydraulics", "kirpich", length=1000, slope="1%")["tc"], 23.45, 0.005)


class TestFoundations(Approx):
    def test_terzaghi_factors_vs_published_table(self):
        """Das, Principles of Foundation Engineering, Table 3.x (Terzaghi)."""
        table = {0: (5.70, 1.00), 20: (17.69, 7.44), 30: (37.16, 22.46), 35: (57.75, 41.44), 40: (95.66, 81.27)}
        for phi, (nc, nq) in table.items():
            r = run("foundations", "bearing", b=2, df=1, phi=phi, ng_input=1)
            self.close(r["nc"], nc, 0.003, f"Nc at phi={phi}")
            self.close(r["nq"], nq, 0.003, f"Nq at phi={phi}")

    def test_strip_footing_sand(self):
        # q = 18*1.5 = 27 ; qu = 27*22.46 + 0.5*18*2*19.13 = 950.7 kPa ; /3 = 316.9
        r = run("foundations", "bearing", shape="strip", b=2, df=1.5, c=0, phi=30, gamma=18, ng_input=19.13)
        self.close(r["qu"], 950.7, 0.003)
        self.close(r["qall"], 316.9, 0.003)
        self.close(r["qnet"], (950.7 - 27) / 3, 0.003)

    def test_square_footing_shape_factors(self):
        # c=25, phi=0, square: 1.3*25*5.7 + 18*1 = 203.25 kPa
        r = run("foundations", "bearing", shape="square", b=1.5, df=1.0, c=25, phi=0, gamma=18)
        self.close(r["qu"], 1.3 * 25 * 5.7 + 18.0, 1e-6)

    def test_water_table_reduces_capacity(self):
        dry = run("foundations", "bearing", b=2, df=1.5, phi=30, gamma=18, ng_input=19.13)["qu"]
        wet = run("foundations", "bearing", b=2, df=1.5, phi=30, gamma=18, gamma_sat=20, dw=0.5, ng_input=19.13)["qu"]
        self.assertLess(wet, dry)

    def test_footing_kern_and_liftoff(self):
        r = run("foundations", "footing", p=900, m=120, bx=3, ly=3, thick=0.5, df=0.5, qall=300)
        # N = 900 + 9*0.5*24 = 1008 ; e = 120/1008 ; qmax = N/9 (1+6e/3)
        e = 120 / 1008
        self.close(r["qmax"], 1008 / 9 * (1 + 6 * e / 3), 1e-6)
        r2 = run("foundations", "footing", p=500, m=400, bx=2, ly=2, thick=0.4, df=0.4, qall=300)
        self.assertEqual(r2["qmin"], 0.0)                              # e > L/6 -> partial contact
        self.assertTrue(r2.warnings)

    def test_nc_clay_settlement(self):
        # 0.3*4/1.9*log10(150/100) = 0.1112 m
        self.close(run("foundations", "settlement", cc=0.3, h=4, e0=0.9, s0=100, ds=50)["sc"], 111.2, 0.003)

    def test_immediate_settlement_units(self):
        """Regression: Es is entered in MPa; q in kPa -> answer must be ~15 mm, not ~15,000 mm."""
        r = run("foundations", "settlement", q=100, b=2, es=10, nu=0.3, iw=0.82)
        self.close(r["si"], 14.92, 0.002)                              # 100*2*0.91*0.82/10,000 kPa = 0.01492 m

    def test_oc_clay_cr_only(self):
        """Regression: OC clay whose final stress stays below s'c needs only Cr (was silently 0)."""
        r = run("foundations", "settlement", cr=0.05, h=4, e0=0.9, s0=100, ds=50, sc=200)
        self.close(r["sc"], 18.54, 0.003)                              # 0.05*4/1.9*log10(1.5)
        self.assertGreater(r["sc"], 0)

    def test_oc_clay_crossing_preconsolidation(self):
        # Cr part: 0.05*4/1.9*log10(150/100)... here s'c=120: Cr*H/(1+e0)*log10(120/100) + Cc*H/(1+e0)*log10(150/120)
        r = run("foundations", "settlement", cc=0.3, cr=0.05, h=4, e0=0.9, s0=100, ds=50, sc=120)
        want = (0.05 * 4 / 1.9 * 0.0791812 + 0.3 * 4 / 1.9 * 0.0969100) * 1000
        self.close(r["sc"], want, 0.003)

    def test_pile_alpha(self):
        r = run("foundations", "pile_clay", d=0.5, length=15, cu=50, alpha=0.5, nc=9, fs=2.5)
        self.close(r["qp"], 88.4, 0.002)
        self.close(r["qs"], 589.0, 0.002)
        self.close(r["qall"], 270.9, 0.002)


class TestGeotechAndEnvironmental(Approx):
    def test_phase(self):
        r = run("geotech", "phase", gs=2.7, e=0.7, w=20)
        self.close(r["s"], 77.14, 0.002)
        self.close(r["gd"], 15.58, 0.002)
        self.close(r["g"], 18.70, 0.002)

    def test_oversaturated_flagged(self):
        self.assertTrue(run("geotech", "phase", gs=2.7, e=0.5, w=30).warnings)

    def test_wall_rankine(self):
        r = run("geotech", "wall", h=3, b=2)
        self.close(r["ka"], 1 / 3, 1e-4)
        self.close(r["pa"], 27.0, 1e-4)
        self.close(r["fso"], 144 / 27, 1e-4)
        self.close(r["qmax"], 112.5, 1e-4)

    def test_infinite_slope(self):
        self.close(run("geotech", "slope", beta=20, h=3)["fs"], 1.5862, 1e-3)    # tan30/tan20

    def test_water_and_sewer(self):
        self.close(run("environmental", "water_demand", pop=50000)["avg_ls"], 86.81, 0.002)
        r = run("environmental", "sewage", pop=10000, lpcd=200)
        self.close(r["m"], 1 + 14 / (4 + 10 ** 0.5), 1e-9)

    def test_clarifier(self):
        r = run("environmental", "clarifier", q=7500)
        self.close(r["area"], 250.0, 1e-9)
        self.close(r["dia"], 17.842, 1e-3)


class TestQuantitiesAndUtilities(Approx):
    def test_rebar_unit_weights(self):
        # d^2/162 rule of thumb: 12 mm 0.888, 16 mm 1.578, 25 mm 3.853 kg/m
        for d, w in ((12, 0.888), (16, 1.578), (25, 3.853)):
            self.close(run("quantities", "rebar", dia=d, length=1)["per_m"], w, 0.002)

    def test_boq_markup_order(self):
        r = run("quantities", "boq", qty="10,20", rate="5,2", contingency=5, overhead=10, tax=7.5)
        self.close(r["total"], 90 * 1.05 * 1.10 * 1.075, 1e-9)

    def test_tiles_round_up(self):
        self.assertEqual(run("quantities", "tiles", area=20, joint=0, waste=5)["n"], 59)

    def test_angle_dms_rounding(self):
        self.assertIn("1° 0' 0.00", run("utilities", "angle", value="0.99999999")["dms"])

    def test_slope_converter(self):
        r = run("utilities", "slope", mode="ratio", value=2)
        self.close(r["pct"], 50.0, 1e-9)
        self.close(r["deg"], 26.565, 1e-4)


# ---------------------------------------------------------------- architecture / CLI
class TestArchitecture(unittest.TestCase):
    def test_builtin_selftest_passes(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(selftest.run_all(), 0)

    def test_all_ten_areas_present(self):
        keys = {d.key for d in registry.load()}
        self.assertTrue({"concrete", "earthwork", "surveying", "structural", "transport", "hydraulics",
                         "foundations", "quantities", "utilities"} <= keys)
        self.assertGreaterEqual(len(keys), 11)                         # + geotech, environmental as "other" domains

    def test_calc_modules_do_not_do_io(self):
        """UI/calculation separation: discipline modules must not print or read input."""
        import civilcalc.disciplines as pkg
        base = os.path.dirname(pkg.__file__)
        for fn in os.listdir(base):
            if fn.endswith(".py"):
                with open(os.path.join(base, fn), encoding="utf-8") as fh:
                    src = fh.read()
                self.assertNotIn("print(", src, fn)
                self.assertNotIn("input(", src, fn)

    def test_new_discipline_is_picked_up_without_other_edits(self):
        import civilcalc.disciplines as pkg
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "demo_extra.py"), "w") as fh:
                fh.write(textwrap.dedent('''
                    from civilcalc.core import Calculation, Case, Discipline, Param, Result
                    def area(b, h):
                        return Result("Triangle").add("a", "Area", 0.5 * b * h, "m2", 2, primary=True).eq("A = b h / 2")
                    DISCIPLINE = Discipline("demo", "Demo", "demo", [
                        Calculation("tri", "Triangle", "area", [Param("b", "Base", "m", min=0, min_exclusive=True),
                                                                Param("h", "Height", "m", min=0, min_exclusive=True)], area)],
                        [Case("tri", {"b": 4, "h": 3}, {"a": 6.0})], order=999)
                '''))
            pkg.__path__.append(tmp)
            try:
                self.assertIn("demo", [d.key for d in registry.load()])
                self.assertEqual(run("demo", "tri", b="2 ft", h="1 m")["a"], 0.5 * 0.6096 * 1)
            finally:
                pkg.__path__.remove(tmp)
                sys.modules.pop("civilcalc.disciplines.demo_extra", None)


class TestCLI(unittest.TestCase):
    def call(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_run_mixed_units(self):
        code, out, _ = self.call("run", "concrete.volume", "shape=rect", "length=20 ft", "width=5", "thickness=150mm")
        self.assertEqual(code, 0)
        self.assertIn("4.572 m3", out)
        self.assertIn("GOVERNING EQUATIONS", out)

    def test_run_json(self):
        code, out, _ = self.call("run", "earthwork.trench", "length=100", "width=1", "depth=2", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["title"], "Trench / excavation volume and haulage")

    def test_bad_input_gives_message_and_nonzero_exit(self):
        code, _, err = self.call("run", "concrete.volume", "length=-5", "width=3")
        self.assertEqual(code, 1)
        self.assertIn("Length", err)

    def test_unknown_calc(self):
        code, _, err = self.call("run", "nope.nothing")
        self.assertEqual(code, 1)
        self.assertIn("Unknown calculation", err)

    def test_convert_and_units_and_list(self):
        code, out, _ = self.call("convert", "4000", "psi", "MPa")
        self.assertEqual(code, 0)
        self.assertIn("27.579", out)
        self.assertIn("pressure", self.call("units")[1])
        self.assertIn("hydraulics.manning", self.call("list")[1])

    def test_interactive_session_scripted(self):
        """Drive the real menu: Concrete -> Concrete volume with defaults -> back -> quit."""
        answers = iter(["1", "1", "rect", "6 m", "4 m", "", "", "", "", "0", "0"])
        import builtins
        real = builtins.input
        builtins.input = lambda prompt="": next(answers)
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                cli.interactive()
        finally:
            builtins.input = real
        text = out.getvalue()
        self.assertIn("CONCRETE VOLUME", text)
        self.assertIn("3.600 m3", text)                                # 6 x 4 x 0.15


if __name__ == "__main__":
    unittest.main(verbosity=2)
