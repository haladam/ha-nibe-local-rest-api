"""Module names inside the package must not break what __init__.py imports from the standard library.

The package has a time.py (the platform for time-of-day settings). When Home Assistant loads that platform
it imports `nibe_local_api.time`, and Python then binds the name `time` in the package namespace (that is
`__init__.py`'s globals) to the platform module. A plain `import time` in __init__.py would stop being the
standard library module from then on: the COP calculation called `time.monotonic()` on every update, worked
for the first one (before the platform was loaded) and failed on every later one. The stand-in clock of the
other suites hid it, so this one uses the real clock and the real platform import.
"""
import sys, asyncio, importlib.util, importlib, logging, types, ast, os, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import SRC
import harness
harness.install()

spec = importlib.util.spec_from_file_location("nibe_local_api", SRC + "/__init__.py", submodule_search_locations=[SRC])
pkg = importlib.util.module_from_spec(spec); sys.modules["nibe_local_api"] = pkg; spec.loader.exec_module(pkg)

results = []
def check(name, cond, detail=""):
    results.append(bool(cond)); print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))

# ------------------------------------------------------------------ static: no import in __init__.py can be shadowed
stems = sorted(os.path.splitext(os.path.basename(f))[0] for f in glob.glob(SRC + "/*.py") if not f.endswith("__init__.py"))
tree = ast.parse(open(SRC + "/__init__.py", encoding="utf-8").read())
shadowable = []
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        shadowable += [a.name for a in node.names if a.asname is None and a.name.split(".")[0] in stems]
    elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module and node.module.split(".")[0] in stems:
        pass  # `from time import monotonic` binds the function, not the module name
check("__init__.py: no `import <name>` of a module that has the same name as a file in the package",
      not shadowable, f"{shadowable} would be replaced by the package's own submodule once that is imported")
check("the package really has a time.py platform (this suite is about it)", "time" in stems, stems)

# ------------------------------------------------------------------ dynamic: the real clock, the real platform import
sys.modules["homeassistant.components.time"] = types.SimpleNamespace(TimeEntity=type("TimeEntity", (), {}))
platform = importlib.import_module("nibe_local_api.time")
check("the time platform is imported as a submodule and takes the name `time` in the package",
      pkg.time is platform and sys.modules["nibe_local_api.time"] is platform)
clock = getattr(pkg, "monotonic", None) or getattr(pkg.time, "monotonic", None)   # the function itself, or what `time.` now points at
check("the clock the coordinator uses is still the real one", clock is not None and clock.__module__ == "time" and clock() > 0)

def point(pid, value, divisor=1, size="s16"):
    return {"metadata": {"variableId": pid, "variableType": "integer", "variableSize": size, "divisor": divisor},
            "value": {"isOk": True, "integerValue": round(value * divisor)}}

class Api:
    async def get_points(self):
        # the pump's real operating point (export of 2026-10-24 13:5x): 22 Hz, 188 W, 15.1 L/min, 26.1 / 24.0 degC
        return {2509: point(2509, 1038), 1758: point(1758, 30), 2002: point(2002, 0), 2556: point(2556, 60), 1973: point(1973, 1),
                1799: point(1799, 22.0, 10, "u16"), 1801: point(1801, 188, 1, "u16"), 1932: point(1932, 188), 58: point(58, 15.1, 10),
                15: point(15, 26.1, 10), 10: point(10, 24.0, 10), 3126: point(3126, 0)}
    async def get_device(self): return {}
    async def get_notifications(self): return []

class Cap(logging.Handler):
    def __init__(self): super().__init__(); self.recs = []
    def emit(self, r): self.recs.append(r)
cap = Cap(); lg = logging.getLogger("nibe_local_api"); lg.addHandler(cap); lg.setLevel(logging.DEBUG)
pkg.dr = types.SimpleNamespace(async_get=lambda hass: types.SimpleNamespace(
    async_get_device=lambda identifiers=None, connections=None: None, async_update_device=lambda *a, **k: None))

harness.Store.files.clear()
c = pkg.NibeCoordinator("HASS", types.SimpleNamespace(options={}), Api(), {"serial": "S", "name": "N", "manufacturer": "NIBE", "firmware": ""})
c._today = lambda: "2026-10-24"
for _ in range(5):
    c.data = asyncio.run(c._async_update_data())
check("five updates with the real clock after the platform import: the COP calculation keeps running", not c._kpi_failed,
      [r.getMessage() for r in cap.recs if r.levelno >= logging.ERROR])
check("every update reached the tracker (the first reading is only settling)", c.kpi is not None and c.kpi.last is not None and c.kpi.last.status == "settling", c.kpi and c.kpi.last)
check("no error was logged", not [r for r in cap.recs if r.levelno >= logging.WARNING], [r.getMessage() for r in cap.recs])

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
