"""Auto-discovery of discipline modules.

Every module in ``civilcalc.disciplines`` that defines a module-level
``DISCIPLINE`` (a core.Discipline) is registered.  Adding a discipline is just
adding a file - no other edits required.
"""
from __future__ import annotations

import importlib
import pkgutil

from . import disciplines
from .core import Discipline, CivilCalcError


def load() -> list[Discipline]:
    found: list[Discipline] = []
    for mod in pkgutil.iter_modules(disciplines.__path__):
        if mod.name.startswith("_"):
            continue
        m = importlib.import_module(f"{disciplines.__name__}.{mod.name}")
        d = getattr(m, "DISCIPLINE", None)
        if isinstance(d, Discipline):
            found.append(d)
    found.sort(key=lambda d: (d.order, d.key))
    keys = [d.key for d in found]
    if len(keys) != len(set(keys)):
        raise CivilCalcError("Duplicate discipline keys: " + ", ".join(keys))
    return found
