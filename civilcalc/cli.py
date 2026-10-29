"""Menu-driven command line interface (the only module that prints/reads)."""
from __future__ import annotations

import sys

from . import __version__, registry, report, units
from .core import Calculation, CivilCalcError, InputError, Param

BACK = ("0", "b", "back")
QUIT = ("q", "quit", "exit")


def _ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        print()
        raise SystemExit(0)


def prompt_param(p: Param) -> object:
    """Ask for one parameter until valid; returns the raw accepted text."""
    unit = f" [{p.unit}]" if p.unit and p.unit != "-" else ""
    if p.kind == "choice":
        print(f"  {p.label}:")
        for i, (_v, lab) in enumerate(p.choices or [], 1):
            print(f"      {i}) {lab}")
    dflt = ""
    if p.default is not None:
        dflt = f" (Enter = {p.display(p.default)})"
    elif p.optional:
        dflt = " (Enter = skip)"
    rng = p.describe_range()
    rng = f" {{{rng}}}" if rng else ""
    label = "  Your choice" if p.kind == "choice" else f"  {p.label}"
    while True:
        raw = _ask(f"{label}{unit}{rng}{dflt}: ")
        if raw == "?":
            print(f"    {p.help or 'No extra help.'}  Units may be typed after the number (e.g. 30 ft); "
                  "'python -m civilcalc units' lists them all.")
            continue
        try:
            p.parse(raw)
            return raw
        except InputError as e:
            print(f"    x {e}")


def run_calc(calc: Calculation) -> None:
    print(f"\n--- {calc.name} ---\n{calc.summary}")
    if calc.standard:
        print(f"Basis: {calc.standard}")
    print("Type a value (units optional, e.g. '12 ft'), '?' for help on a field.\n")
    raw = {p.key: prompt_param(p) for p in calc.params}
    try:
        print("\n" + report.render(calc.run(raw)))
    except CivilCalcError as e:
        print(f"\nCannot calculate: {e}")


def _menu(title: str, items: list[str], allow_back=True) -> int | None:
    print(f"\n== {title} ==")
    for i, t in enumerate(items, 1):
        print(f" {i:>2}) {t}")
    print(f"  0) {'Back' if allow_back else 'Quit'}")
    while True:
        s = _ask("Select: ").lower()
        if s in BACK or s in QUIT:
            return None
        if s.isdigit() and 1 <= int(s) <= len(items):
            return int(s) - 1
        print("  Enter a number from the list.")


def interactive() -> None:
    discs = registry.load()
    print(f"CIVIL CALC SUITE v{__version__}  -  SI units by default; you may type any unit after a number.")
    while True:
        items = [f"{d.name}  ({len(d.calcs)} calcs)" for d in discs]
        items.append("Search all calculations")
        i = _menu("MAIN MENU", items, allow_back=False)
        if i is None:
            return
        if i == len(discs):
            _search(discs)
            continue
        d = discs[i]
        while True:
            j = _menu(d.name, [f"{c.name} - {c.summary}" for c in d.calcs])
            if j is None:
                break
            run_calc(d.calcs[j])
            _ask("\nPress Enter to continue...")


def _search(discs) -> None:
    q = _ask("Search words: ").lower()
    hits = [(d, c) for d in discs for c in d.calcs
            if q in f"{c.name} {c.summary} {c.standard} {c.key}".lower()]
    if not hits:
        print("  No match.")
        return
    j = _menu("Matches", [f"{c.name}  [{d.name}]" for d, c in hits])
    if j is not None:
        run_calc(hits[j][1])
        _ask("\nPress Enter to continue...")


# --------------------------------------------------------------------------
def cmd_list() -> int:
    for d in registry.load():
        print(f"\n{d.name}  [{d.key}]")
        for c in d.calcs:
            print(f"  {d.key}.{c.key:<22} {c.summary}")
    return 0


def cmd_show(cid: str) -> int:
    calc = _find(cid)
    print(f"{calc.name}  ({calc.full_id})\n{calc.summary}\nBasis: {calc.standard}\nInputs:")
    for p in calc.params:
        d = "" if p.default is None else f"  default={p.display(p.default)}"
        o = "  optional" if p.optional else ""
        print(f"  {p.key:<16} {p.label} [{p.unit or '-'}]{d}{o}")
    return 0


def _find(cid: str) -> Calculation:
    try:
        dk, ck = cid.split(".", 1)
        for d in registry.load():
            if d.key == dk:
                return d.get(ck)
    except (ValueError, KeyError):
        pass
    raise InputError(f"Unknown calculation '{cid}'. Run 'list' to see valid ids.")


def cmd_run(args: list[str]) -> int:
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    if not args:
        raise InputError("Usage: run <discipline.calc> key=value ... [--json]")
    calc = _find(args[0])
    raw = {}
    for a in args[1:]:
        if "=" not in a:
            raise InputError(f"Use key=value (got '{a}'). Run 'show {args[0]}' for inputs.")
        k, v = a.split("=", 1)
        raw[k] = v
    res = calc.run(raw)
    if as_json:
        import json
        print(json.dumps(res.to_dict(), indent=2, default=str))
    else:
        print(report.render(res))
    return 0


def cmd_units() -> int:
    print("Recognised units (type any of them after a number, e.g. '30 ft', '4000 psi', '2%'):\n")
    for dim, names in units.known_units().items():
        print(f"  {dim:<14} {', '.join(names)}")
    print("\nAliases such as 'sqft', 'cuyd', 'gpm', 'kip-ft', 'degF' are accepted; matching ignores case and spaces.")
    print("Feet-inches work for lengths (5'6\"); degrees-minutes-seconds work for angles (45-30-15).")
    return 0


def cmd_convert(args: list[str]) -> int:
    if len(args) != 3:
        raise InputError("Usage: convert <value> <from_unit> <to_unit>")
    v = units.convert(float(args[0]), args[1], args[2])
    print(f"{args[0]} {args[1]} = {v:.6g} {args[2]}")
    return 0


USAGE = """usage: python -m civilcalc [command]
  (no command)              interactive menu
  list                      list every calculation id
  show  <disc.calc>         show the inputs a calculation needs
  run   <disc.calc> k=v ..  run non-interactively (add --json for machine-readable output), e.g.
                            run concrete.volume shape=rect length="20 ft" width=5 thickness=150mm
  convert <val> <from> <to> quick unit conversion
  units                     list every recognised unit
  test [-v]                 run built-in worked examples
"""


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        if not argv:
            interactive()
            return 0
        cmd, rest = argv[0], argv[1:]
        if cmd == "list":
            return cmd_list()
        if cmd == "show" and rest:
            return cmd_show(rest[0])
        if cmd == "run" and rest:
            return cmd_run(rest)
        if cmd == "convert":
            return cmd_convert(rest)
        if cmd == "units":
            return cmd_units()
        if cmd == "test":
            from . import selftest
            return selftest.run_all(verbose="-v" in rest)
        print(USAGE)
        return 0 if cmd in ("-h", "--help", "help") else 2
    except (CivilCalcError, units.UnitError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print()
        return 130
