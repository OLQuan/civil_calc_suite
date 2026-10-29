# CivilCalc - civil engineering calculator suite

Menu-driven calculators for everyday civil engineering work. No documentation needed to use it:
each calculation asks for exactly the inputs it needs, with units, rejects impossible values, and
prints the result together with the equation, the standard it comes from, and every assumption.

Pure Python standard library, nothing to install. Needs Python 3.10+ (tested on 3.11, 3.12 and 3.13).

## Run it

```bash
cd civil_calc_suite
python -m civilcalc            # interactive menu (start here)
```

Pick a discipline, pick a calculation, answer the prompts. At any prompt:

| Type              | Effect                                                                 |
|-------------------|------------------------------------------------------------------------|
| a number          | taken in the unit shown in `[brackets]` (SI by default)                |
| `30 ft`, `4000 psi`, `150mm`, `2%` | any recognised unit; it is converted for you      |
| `5'6"`            | feet-inches (lengths)                                                  |
| `45-30-15`        | degrees-minutes-seconds (angles)                                       |
| Enter             | use the default shown in `(Enter = ...)`; defaults are listed in the report |
| `?`               | one-line help for the field                                            |
| `0`               | back / quit                                                            |

Non-interactive use (scripts, spreadsheets, quick checks):

```bash
python -m civilcalc list                              # every calculation id
python -m civilcalc show foundations.bearing          # the inputs it needs
python -m civilcalc run concrete.volume shape=rect length="20 ft" width=5 thickness=150mm
python -m civilcalc run hydraulics.manning shape=rect width=2 slope=0.1% depth=1 --json
python -m civilcalc convert 4000 psi MPa
python -m civilcalc units                             # every recognised unit
python -m civilcalc test                              # worked examples (see below)
```

## What is in it

| #  | Discipline (`key`)                   | Calculations |
|----|--------------------------------------|--------------|
| 1  | Concrete and Masonry (`concrete`)    | member volume, nominal mix, Ec / fr / f'cr, RC beam flexure, brick/block wall |
| 2  | Earthwork (`earthwork`)              | trench/pit volume and trucks, average end-area, cut/fill balance, compaction |
| 3  | Surveying (`surveying`)              | level book with misclosure, Bowditch traverse + area, coordinate join, stadia |
| 4  | Structural (`structural`)            | beam reactions/M/V/deflection, RC column, steel beam, ASCE 7 combinations, min. thickness |
| 5  | Transportation (`transport`)         | horizontal and vertical curves, min. radius, SSD, ESALs, AASHTO-93 flexible pavement |
| 6  | Hydraulics (`hydraulics`)            | Manning (rect/trap/circular), pipe loss (H-W, D-W), rational method, Kirpich, weir, orifice, pump |
| 7  | Foundations (`foundations`)          | Terzaghi bearing, footing pressure with eccentricity, settlement, pile (alpha) |
| 8  | Quantities (`quantities`)            | rebar weight, plaster, tiles, paint, road layers, BOQ cost roll-up |
| 9  | Unit conversion and utilities (`utilities`) | converter, angle formats, slope formats, typical unit weights |
| 10 | Other domains: Geotechnical (`geotech`), Environmental / public health (`environmental`) | phase relations, Atterberg limits, retaining wall, infinite slope; population, water demand, sewage flow, clarifier |

## How to read a result

Every report has the same sections: **Inputs** (defaults tagged `[default]`), **Assumptions**,
**Governing equations** (with the standard), **Results** (the headline value is starred, SI with an
imperial companion), **Checks** (PASS/FAIL against limits), **Warnings**, **References**.

Two rules the suite follows, so you can trust what you see:

* **Impossible inputs are refused, unusual ones are flagged.** A negative width or f'c = 5 MPa stops with a
  message naming the field; a value outside the usual range (but possible) computes and adds a warning.
* **Nothing from a code table is hidden.** Values that come from a chart or table you must look up
  (Manning n, AASHTO layer coefficients and ZR, Hazen-Williams C, adhesion factor alpha, truck factor,
  runoff C, Terzaghi N-gamma, steel section properties, ...) are inputs with a documented default,
  listed under Assumptions in the report. Confirm them against your project's code edition.

Results are for preliminary design and checking. The engineer of record remains responsible for the design.

## Verify it works

```bash
python -m civilcalc test                      # 81 worked examples with known answers (each run twice: numbers and typed text)
python -m unittest discover -s tests -v       # 84 independent checks against textbook values and hand calculations
```

`python -m civilcalc test` is the quick confidence check you can run on any machine. The `tests/` folder
is the audit: expected values there are published constants (NIST unit factors, Terzaghi factors from
Das's tables) or hand calculations, not recomputed with the program's own formulas.

## Project layout

```
civilcalc/
  units.py          unit registry + converter + text parser (the single source of unit truth)
  core.py           Param (validation), Result, Calculation, Discipline, Case (worked example)
  report.py         turns a Result into text
  cli.py            the ONLY module that prints or reads input
  registry.py       auto-discovers disciplines
  selftest.py       runs every Case
  disciplines/      one file per discipline: concrete.py, earthwork.py, ... each with its own CASES
tests/test_suite.py independent verification
```

Unit convention: each `Param` declares the unit its function receives (mostly SI: m, mm, kN, kPa, MPa,
kg, m3/s). Whatever the user types is converted to that unit before the function runs, so calculation
functions never deal with mixed units.

## Add a new discipline (5 minutes)

1. Create `civilcalc/disciplines/mytopic.py`. Nothing else needs editing; it is discovered automatically.
2. Write plain functions that take validated values and return a `Result` (no `print`, no `input`).
3. Describe the inputs with `Param`, group them in `Calculation`s, add a worked example as a `Case`.

```python
"""Timber: bending capacity of a rectangular beam."""
from ..core import Calculation, Case, Discipline, Param, Result

def timber_bending(b, d, fb):
    s = b * d ** 2 / 6                                   # mm3
    r = Result("Timber beam bending capacity")
    r.eq("S = b d^2 / 6;  M = Fb S")
    r.add("m", "Moment capacity", fb * s / 1e6, "kN-m", 2, primary=True)
    r.assume("Fb is the adjusted allowable bending stress from your timber code - not hardcoded.")
    r.ref("Your national timber design standard")
    return r

CALCS = [Calculation(
    "bending", "Timber beam bending", "Allowable moment of a rectangular section",
    [Param("b", "Width b", "mm", min=0, min_exclusive=True),
     Param("d", "Depth d", "mm", min=0, min_exclusive=True),
     Param("fb", "Allowable bending stress Fb", "MPa", default=10.0, min=1, max=60,
           help="From your timber code, adjusted for duration and moisture.")],
    timber_bending, "Beam theory; timber code for Fb")]

CASES = [Case("bending", {"b": 100, "d": 200, "fb": 10}, {"m": 6.667}, "100x200, 10 MPa", rel=0.001)]

DISCIPLINE = Discipline("timber", "Timber Design", "Timber members", CALCS, CASES, order=110)
```

Then `python -m civilcalc test` runs your example, and the menu lists the new discipline.

Param options you will use most: `min` / `max` (hard limits, value rejected), `min_exclusive`,
`typical=(lo, hi)` (soft range, warning only), `default`, `optional=True` (blank passes `None`),
`kind="choice"` with `choices=[(value, label), ...]`, `kind="floatlist"` for comma-separated values,
`kind="int"`.

To add a unit, add one line to `_DEFS` in `civilcalc/units.py`
(`(("name", "alias"), factor_to_base_unit)`); aliases that clash with an existing unit fail at import.
