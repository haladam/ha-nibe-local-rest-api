import sys, asyncio, importlib.util, importlib, logging, types, json, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import SRC, REST_413, REST_414, FIXTURES, CARD_BUILD, PREV_082, PREV_083, version_at_least
import harness
harness.install()

spec = importlib.util.spec_from_file_location(
    "nibe_local_api", SRC + "/__init__.py",
    submodule_search_locations=[SRC])
pkg = importlib.util.module_from_spec(spec); sys.modules["nibe_local_api"] = pkg; spec.loader.exec_module(pkg)

from nibe_local_api import api as napi, catalog, fastpoll, const
from harness import ConfigEntryAuthFailed

results = []
def check(name, cond, detail=""):
    results.append(bool(cond)); print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))

REST = REST_413
DATA = catalog.load_data(SRC + "/data.json")

# ------------------------------------------------------------------ A: ranges
def meta(mn, mx, rtype="MODBUS_HOLDING_REGISTER", reg=100):
    return {"minValue": mn, "maxValue": mx, "modbusRegisterType": rtype, "modbusRegisterID": reg}
TABLE = {"H100": [50, 600], "I100": [0, 10]}
check("register_key: holding and input registers", napi.register_key(meta(0, 1)) == "H100" and napi.register_key(meta(0, 1, "MODBUS_INPUT_REGISTER")) == "I100")
check("register_key: missing or unknown type -> None", napi.register_key({}) is None and napi.register_key({"modbusRegisterType": "X", "modbusRegisterID": 1}) is None)
check("bounds: pump range wider -> table narrows it", napi.bounds(1, meta(50, 700), TABLE) == (50, 600))
check("bounds: pump range narrower -> pump range kept", napi.bounds(1, meta(100, 300), TABLE) == (100, 300))
check("bounds: both limits narrowed independently", napi.bounds(1, meta(0, 700), {"H100": [50, 600]}) == (50, 600))
check("bounds: no table / unknown register -> unchanged", napi.bounds(1, meta(50, 700)) == (50, 700) and napi.bounds(1, meta(50, 700, reg=7), TABLE) == (50, 700))
check("bounds: pump reports empty range -> table cannot widen it", napi.bounds(1, meta(0, 0), TABLE) == (0, 0))
check("bounds: disjoint ranges -> pump range kept", napi.bounds(1, meta(700, 800), TABLE) == (700, 800))
check("bounds: firmware override applied before the table (3702)", napi.bounds(3702, meta(55, 700, reg=100), {"H100": [550, 700]}) == (550, 700))
check("bounds: override range for a point the table says is empty (4564)", napi.bounds(4564, meta(0, 0, reg=100), {"H100": [0, 0]}) == (0, 127))
check("reported_bounds: ignores the table", napi.reported_bounds(1, meta(50, 700)) == (50, 700))

# ------------------------------------------------------------------ B: option filtering
O = {0: "Zones", 1: "Climate system", 2: "Profile"}
check("options_in_range: label above the range is dropped", catalog.options_in_range(O, 0, 1, 1) == {0: "Zones", 1: "Climate system"})
check("options_in_range: divisor applied (raw = key x divisor)", catalog.options_in_range({1: "a", 2: "b", 3: "c"}, 10, 20, 10) == {1: "a", 2: "b"})
check("options_in_range: empty pump range -> nothing dropped", catalog.options_in_range(O, 0, 0, 1) == O)
check("options_in_range: fewer than two would remain -> nothing dropped", catalog.options_in_range(O, 0, 0 + 0, 1) == O and catalog.options_in_range(O, 5, 9, 1) == O)
check("options_in_range: the value the pump holds now stays selectable", catalog.options_in_range(O, 0, 1, 1, current_raw=2) == O)
check("options_in_range: all inside the range -> unchanged", catalog.options_in_range(O, 0, 2, 1) == O)

# ------------------------------------------------------------------ real REST export
if os.path.exists(REST):
    points = {int(k): v for k, v in json.load(open(REST, encoding="utf-8")).items()}
    infos = catalog.build_infos(points, DATA)
    new = lambda pid: infos[pid]
    check("real: 1176 points build", len(points) == 1176 and len(infos) == 1176)
    check("A real: hot water start/stop ranges follow NIBE's register list",
          [(new(p).min_raw, new(p).max_raw) for p in (3700, 3701, 3704, 3705)] == [(50, 600), (50, 550), (50, 650), (50, 600)])
    check("A real: zone 1 room temperature 5-30 C", (new(32341).min_raw, new(32341).max_raw) == (50, 300))
    check("A real: 3702 keeps the corrected 55-70 C", (new(3702).min_raw, new(3702).max_raw) == (550, 700))
    check("A real: 3931 (pump narrower than the list) keeps the pump range", (new(3931).min_raw, new(3931).max_raw) == (100, 300))
    check("A real: tariff prices capped at 10000", all(new(p).max_raw == 10000 for p in (5271, 5286, 5293)))
    check("A real: 4564 keeps its override", (new(4564).min_raw, new(4564).max_raw) == (0, 127))
    b = new(4030)
    check("boost: 4030 is a read-only sensor in minutes (the pump answers a REST write with HTTP 400)",
          (b.kind, b.unit) == ("sensor", "min") and not points[4030]["metadata"]["isWritable"], (b.kind, b.unit))
    check("boost: 4030 is enabled by default and not hidden among the configuration entities (the card reads it)",
          b.enabled and b.category is None and b.name == "More hot water, minutes remaining", (b.enabled, b.category, b.name))
    check("boost: 4564 is the writable one, a number that is created disabled; 1942 (status) is an enabled sensor",
          not new(4564).enabled and new(4564).kind == "number" and new(1942).kind == "sensor" and new(1942).enabled, (new(4564).enabled, new(1942).kind))
    check("boost: 4564 says that writing 2 starts the increase and that the pump counts 120 minutes",
          "Write 2" in new(4564).description and "120 minutes" in new(4564).description, new(4564).description)
    check("boost: 4030 says it is read-only and points to More hot water",
          "Read-only" in b.description and "More hot water" in b.description, b.description)
    check("A real: range note explains the change", new(3700).range_note == "Range limited to 5-60 °C using NIBE's register list; the pump reports 5-70 °C.", new(3700).range_note)
    check("A real: range note is part of the description", "Range limited to" in new(3700).description)
    check("A real: no note where nothing changed", new(3931).range_note == "" and "Range limited" not in new(3667).description)
    check("A real: every number has min < max", all(i.min_raw < i.max_raw for i in infos.values() if i.kind == "number"))
    check("A real: every number's range sits inside the pump's own range",
          all(napi.reported_bounds(p, points[p]["metadata"])[0] <= i.min_raw and i.max_raw <= napi.reported_bounds(p, points[p]["metadata"])[1]
              for p, i in infos.items() if i.kind == "number"))
    check("A real: PV power keeps its 0-655350 W range through the x10 multiplier",
          (new(14314).min_raw, new(14314).max_raw) == (0, 65535))
    ecs = [14318 + k for k in range(8)]
    check("B real: ECS1-8 offer Zones and Climate system only", all(new(p).options == {0: "Zones", 1: "Climate system"} for p in ecs))
    sel = {p: i.options for p, i in infos.items() if i.kind == "select"}
    check("B real: every select keeps at least two options", all(len(o) >= 2 for o in sel.values()))
    check("B real: current value of every select is among its options",
          all(napi.raw_value(points[p]) is None or any(k * napi.divisor(p, points[p]) == napi.raw_value(points[p]) for k in o) for p, o in sel.items()))
    check("C real: PV switches and More hot water status enabled",
          all(new(p).enabled for p in (14312, 14313, 1942)))
    check("C real: PV switches are ordinary settings, 1942 stays a diagnostic",
          new(14312).category is None and new(14313).category is None and new(1942).category == "diagnostic")
    check("C real: 14312 and 14313 are switches", new(14312).kind == "switch" and new(14313).kind == "switch")
    check("C real: 32824 power limitation stays disabled", not new(32824).enabled)
    check("C real: 14314 description names the prerequisite", "7.5.12" in new(14314).description)
    # brine pump delta T is a temperature difference: kelvin, not degrees (a temperature device class would convert it)
    check("D real: brine pump dT (current and set point) are measurements in K, without a temperature device class",
          all((new(p).unit, new(p).device_class, new(p).state_class, new(p).kind) == ("K", None, "measurement", "sensor") for p in (3294, 3295)),
          [(new(p).unit, new(p).device_class, new(p).state_class) for p in (3294, 3295)])
    check("D real: no other enabled sensor with a decimal divisor lacks a unit",
          not [p for p, i in infos.items() if i.kind == "sensor" and i.enabled and not i.unit and not i.options and points[p]["metadata"].get("divisor", 1) > 1],
          [p for p, i in infos.items() if i.kind == "sensor" and i.enabled and not i.unit and not i.options and points[p]["metadata"].get("divisor", 1) > 1])

    # CSV rows match the header
    rows = [pkg._csv_row(p, i, points[p]) for p, i in sorted(infos.items())]
    check("csv: every row has one cell per header column", all(len(r) == len(pkg.CSV_HEADER) for r in rows) and len(rows) == 1176)
    row = {h: c for h, c in zip(pkg.CSV_HEADER, pkg._csv_row(3700, infos[3700], points[3700]))}
    check("csv: effective range columns", (row["effective_min_raw"], row["effective_max_raw"]) == (50, 600) and row["min_raw"] == 50 and row["max_raw"] == 700 and "Range limited" in row["range_note"])

    # nothing else changes versus the 0.8.2 catalog beyond the intended items
    import types as _t
    OLD = PREV_082
    if OLD and os.path.isdir(OLD):
        sys.modules["old082pkg"] = _t.ModuleType("old082pkg"); sys.modules["old082pkg"].__path__ = [OLD]
        oldcat = importlib.import_module("old082pkg.catalog")
        old = oldcat.build_infos(points, oldcat.load_data(OLD + "/data.json"))
        changed = {}
        for p in points:
            for f in ("name", "kind", "unit", "device_class", "state_class", "category", "enabled", "live", "options", "reason"):
                if getattr(old[p], f) != getattr(infos[p], f): changed.setdefault(p, []).append(f)
        PRESSURE0 = {2885, 2913, 2941, 2969, 2997, 3025, 3053, 3081, 3108, 3109, 3122, 3123}   # 0.8.6: 0 bar = no sensor
        expected = {1942, 14312, 14313, 2509} | set(ecs) | PRESSURE0       # 2509: renamed and enabled in 0.8.4
        check("diff vs 0.8.2: only the intended points changed", set(changed) == expected, sorted(set(changed) ^ expected))
        check("diff vs 0.8.2: the zero-pressure points only changed live/reason, never enabled",
              all(set(changed[p]) == {"live", "reason"} for p in PRESSURE0), {p: changed[p] for p in PRESSURE0})
        check("diff vs 0.8.2: names, kinds and units untouched (except the 0.8.4 version sensor)",
              not any(f in ("name", "kind", "unit", "device_class", "state_class") for p, fs in changed.items() if p != 2509 for f in fs))
    else:
        print("SKIP comparison with release 0.8.2 (set NIBE_TEST_PREV_082 to its unpacked nibe_local_api folder)")
else:
    print("SKIP real-data checks (export not found)")

# ------------------------------------------------------------------ version label
check("version_label: product line id is not a version", napi.version_label("nibe-n") is None and napi.version_label("") is None and napi.version_label(None) is None)
check("version_label: real version kept", napi.version_label("4.14.6") == "4.14.6" and napi.version_label("v2.4.3-rc1") == "v2.4.3-rc1")

# ------------------------------------------------------------------ fastpoll helpers
check("selected_point_ids: strings, junk, duplicates and unknown ids handled",
      fastpoll.selected_point_ids({"fast_points": ["4", 8, "x", None, 4, 999]}, {4, 8, 10}) == [4, 8])
check("selected_point_ids: capped at the maximum", len(fastpoll.selected_point_ids({"fast_points": list(range(30))}, set(range(30)))) == const.MAX_FAST_POINTS)
check("selected_point_ids: nothing saved -> empty", fastpoll.selected_point_ids({}, {1}) == [] and fastpoll.selected_point_ids({"fast_points": None}, {1}) == [])
good_payload = {"title": "t", "metadata": {"variableId": 4}, "value": {"integerValue": 1}}
check("is_point_payload: table-entry shaped payloads accepted", fastpoll.is_point_payload(good_payload, 4) and fastpoll.is_point_payload({"metadata": {}, "datavalue": {}}, 4))
check("is_point_payload: wrong id, list, text, missing value rejected",
      not fastpoll.is_point_payload(good_payload, 5) and not fastpoll.is_point_payload([good_payload], 4)
      and not fastpoll.is_point_payload("<html>", 4) and not fastpoll.is_point_payload({"metadata": {"variableId": 4}}, 4)
      and not fastpoll.is_point_payload(None, 4))
PI = lambda name, kind: types.SimpleNamespace(name=name, kind=kind)
INF = {1: PI("Zebra", "sensor"), 2: PI("apple", "number"), 3: PI("Button", "button"), 4: PI("Skipped", "skip"), 5: PI("Hidden", "sensor")}
check("choice_pairs: usable and selected points, buttons and skips left out, sorted by label",
      fastpoll.choice_pairs(INF, {1, 2, 3, 4}, [5]) == [(2, "apple [2]"), (5, "Hidden [5]"), (1, "Zebra [1]")])

# ------------------------------------------------------------------ E: coordinator fast poll
class Cap(logging.Handler):
    def __init__(self): super().__init__(); self.records = []
    def emit(self, r): self.records.append((r.levelno, r.getMessage()))
cap = Cap(); lg = logging.getLogger("nibe_local_api"); lg.addHandler(cap); lg.setLevel(logging.DEBUG)

def mk_point(raw, pid):
    return {"title": "T", "metadata": {"variableId": pid, "variableType": "integer", "variableSize": "s16", "divisor": 10},
            "value": {"isOk": True, "integerValue": raw}}

class FApi:
    def __init__(self, values=None, fail_on=None, exc=None, delay=0, bad=()):
        self.values, self.fail_on, self.exc, self.delay, self.bad = values or {}, fail_on, exc, delay, set(bad)
        self.single, self.table, self.events = [], 0, []
    async def get_point(self, pid):
        self.events.append(("start", pid)); self.single.append(pid)
        if self.delay: await asyncio.sleep(self.delay)
        if self.exc and (self.fail_on is None or pid == self.fail_on): raise self.exc
        self.events.append(("end", pid))
        if pid in self.bad: return {"unexpected": True}
        return mk_point(self.values.get(pid, 0), pid)
    async def get_points(self):
        self.table += 1; self.events.append(("table-start", 0))
        await asyncio.sleep(self.delay); self.events.append(("table-end", 0))
        return {4: mk_point(111, 4), 8: mk_point(222, 8), 10: mk_point(333, 10)}
    async def get_device(self): return {}
    async def get_notifications(self): return []

def fcoord(api, fast=(4, 8), ok=True):
    entry = types.SimpleNamespace(options={})
    co = pkg.NibeCoordinator(None, entry, api, {"serial": "S", "name": "N", "manufacturer": "NIBE", "firmware": ""})
    co.data = {4: mk_point(1, 4), 8: mk_point(2, 8), 10: mk_point(3, 10)}
    co.last_update_success = ok; co.fast_points = list(fast)
    co.reauth = []; co.hass = "HASS"
    co.config_entry = types.SimpleNamespace(async_start_reauth=lambda hass: co.reauth.append(hass))
    co.point_updates = []
    co.async_update_point_listeners = lambda ids: co.point_updates.append(sorted(ids))   # since 0.8.5: targeted
    return co

api = FApi({4: 40, 8: 80, 10: 100}); co = fcoord(api)
asyncio.run(co.async_fast_poll())
check("fast: chosen points updated, others untouched, no table fetch",
      co.data[4]["value"]["integerValue"] == 40 and co.data[8]["value"]["integerValue"] == 80 and co.data[10]["value"]["integerValue"] == 3
      and api.table == 0 and api.single == [4, 8])
check("fast: listeners of the polled points notified once for the whole round", co.point_updates == [[4, 8]] and co.listener_updates == 0, co.point_updates)
check("fast: round scheduled by HA gets the time argument", asyncio.run(co.async_fast_poll("now")) is None)

api = FApi(); co = fcoord(api, fast=())
asyncio.run(co.async_fast_poll())
check("fast: nothing chosen -> no requests", api.single == [] and co.listener_updates == 0)
api = FApi(); co = fcoord(api, ok=False)
asyncio.run(co.async_fast_poll())
check("fast: skipped while the last full update failed", api.single == [])
api = FApi(); co = fcoord(api); co.data = None
asyncio.run(co.async_fast_poll())
check("fast: skipped before the first table exists", api.single == [])

async def locked_round():
    api = FApi({4: 40}); co = fcoord(api)
    async with co._poll_lock:
        try: await asyncio.wait_for(co.async_fast_poll(), 1)      # a queued tick would wait for ever
        except asyncio.TimeoutError: return api, True
    return api, False
api, hung = asyncio.run(locked_round())
check("fast: skipped (not queued) while a full update holds the lock", api.single == [] and not hung)

async def overlap():
    api = FApi({4: 40, 8: 80}, delay=0.05); co = fcoord(api)
    await asyncio.gather(co._async_update_data(), asyncio.sleep(0.01))      # table in flight...
    return api, co
async def table_then_fast():
    api = FApi({4: 40, 8: 80}, delay=0.05); co = fcoord(api)
    full = asyncio.create_task(co._async_update_data()); await asyncio.sleep(0.01)
    await co.async_fast_poll()                                               # ...fast tick arrives mid-table
    table = await full
    return api, co, table
api, co, table = asyncio.run(table_then_fast())
check("fast+full: tick during a table read is skipped, so the table is never overwritten by older data",
      api.single == [] and table[4]["value"]["integerValue"] == 111)

async def fast_then_table():
    api = FApi({4: 40, 8: 80}, delay=0.03); co = fcoord(api)
    fast = asyncio.create_task(co.async_fast_poll()); await asyncio.sleep(0.01)
    table = await co._async_update_data(); await fast
    return api, co
api, co = asyncio.run(fast_then_table())
ev = [e[0] for e in api.events]
check("fast+full: a table read waits for a running fast round instead of overlapping",
      ev.index("table-start") > max(i for i, e in enumerate(ev) if e == "end"), ev)

api = FApi({4: 40, 8: 80}, bad=(8,)); co = fcoord(api)
asyncio.run(co.async_fast_poll())
check("fast: payload of the wrong shape is ignored, the good one applied",
      co.data[4]["value"]["integerValue"] == 40 and co.data[8]["value"]["integerValue"] == 2)

cap.records.clear()
api = FApi({4: 40, 8: 80}, fail_on=8, exc=napi.NibeApiError("slow")); co = fcoord(api)
asyncio.run(co.async_fast_poll())
check("fast: points read before a failure are still applied", co.data[4]["value"]["integerValue"] == 40 and co.data[8]["value"]["integerValue"] == 2 and co.point_updates == [[4]])
check("fast: first failure is only a debug line", [l for l, _ in cap.records if l >= logging.WARNING] == [])
for _ in range(4): asyncio.run(co.async_fast_poll())
warns = [m for l, m in cap.records if l == logging.WARNING]
check("fast: exactly one warning after three failures in a row, no spam", len(warns) == 1 and "3 times" in warns[0], warns)
co.api.exc = None
asyncio.run(co.async_fast_poll())
check("fast: recovery logged once and counter reset", co._fast_failures == 0 and any("works again" in m for _, m in cap.records))

api = FApi(exc=napi.NibeAuthError("401")); co = fcoord(api)
asyncio.run(co.async_fast_poll())
check("fast: 401 starts reauth and changes nothing", co.reauth == ["HASS"] and co.data[4]["value"]["integerValue"] == 1 and co.point_updates == [])

pkg.FAST_POLL_TIMEOUT = 0.05
api = FApi({4: 40}, delay=0.2); co = fcoord(api)
asyncio.run(co.async_fast_poll())
check("fast: a hanging pump times the round out without raising", co._fast_failures == 1 and not co._poll_lock.locked())
pkg.FAST_POLL_TIMEOUT = const.FAST_POLL_TIMEOUT

co = fcoord(FApi({4: 40}))
check("coordinator: poll lock exists and starts free", isinstance(co._poll_lock, asyncio.Lock) and not co._poll_lock.locked())

# ------------------------------------------------------------------ E: scheduling from the options
class Entry:
    def __init__(self, options): self.options, self.unloads = options, []
    def async_on_unload(self, fn): self.unloads.append(fn)
sched = []
pkg.async_track_time_interval = lambda hass, action, interval, name=None: (sched.append((action, interval.total_seconds(), name)), "CANCEL")[1]

co = fcoord(FApi()); e = Entry({})
pkg._start_fast_polling("HASS", e, co)
check("options: nothing chosen -> no timer", sched == [] and e.unloads == [] and co.fast_points == [])
e = Entry({"fast_points": [4, "8", 999], "fast_interval": 20})
pkg._start_fast_polling("HASS", e, co)
check("options: timer at the chosen interval, unknown ids dropped, cancel handed to HA",
      co.fast_points == [4, 8] and sched[-1][1] == 20 and sched[-1][0] == co.async_fast_poll and e.unloads == ["CANCEL"])
e = Entry({"fast_points": [4], "fast_interval": 1}); pkg._start_fast_polling("HASS", e, co)
check("options: interval below 5 s is raised to 5 s", sched[-1][1] == 5)
e = Entry({"fast_points": [4], "fast_interval": 99999}); pkg._start_fast_polling("HASS", e, co)
check("options: interval above 300 s is lowered to 300 s", sched[-1][1] == 300)
e = Entry({"fast_points": [4]}); pkg._start_fast_polling("HASS", e, co)
check("options: no interval saved -> default 10 s", sched[-1][1] == const.DEFAULT_FAST_INTERVAL)

# ------------------------------------------------------------------ E: options flow (with small stand-ins for HA and voluptuous)
class Marker:
    def __init__(self, schema, default=None): self.schema, self.default = schema, default
    def __hash__(self): return hash(self.schema)
    def __eq__(self, o): return isinstance(o, Marker) and o.schema == self.schema
fake_vol = types.ModuleType("voluptuous")
fake_vol.Schema = lambda d: d
fake_vol.Required = lambda k, default=None: Marker(k, default)
fake_vol.Optional = lambda k, default=None: Marker(k, default)
fake_vol.All = lambda *a: ("All", a)
fake_vol.Range = lambda **k: ("Range", k)
sys.modules["voluptuous"] = fake_vol
class OptionsFlow:
    def async_create_entry(self, data=None, **kw): return {"type": "create_entry", "data": data}
    def async_show_form(self, step_id=None, data_schema=None, errors=None, **kw): return {"type": "form", "schema": data_schema, "errors": errors or {}}
class ConfigFlow:
    def __init_subclass__(cls, domain=None, **kw): pass
ce = sys.modules["homeassistant.config_entries"]; ce.OptionsFlow, ce.ConfigFlow = OptionsFlow, ConfigFlow
sys.modules["homeassistant"].config_entries = ce
sel = sys.modules["homeassistant.helpers.selector"]
sel.SelectOptionDict = lambda value, label: {"value": value, "label": label}
sel.SelectSelectorConfig = lambda **k: k
sel.SelectSelector = lambda cfg: ("Select", cfg)
sel.SelectSelectorMode = types.SimpleNamespace(DROPDOWN="dropdown")
reg_entries = []
er = sys.modules["homeassistant.helpers.entity_registry"]
er.async_get = lambda hass: "REG"; er.async_entries_for_config_entry = lambda reg, eid: reg_entries
cf = importlib.import_module("nibe_local_api.config_flow")

class Ent:
    def __init__(self, uid, disabled=None): self.unique_id, self.disabled_by = uid, disabled
reg_entries[:] = [Ent("S_4"), Ent("S_8"), Ent("S_10", disabled="user"), Ent("S_smartmode"), Ent("OTHER_4")]
infos = {4: PI("Outdoor", "sensor"), 8: PI("Supply", "sensor"), 10: PI("Return", "sensor"), 3478: PI("Reset", "button")}

def flow(options, loaded=True):
    coord = types.SimpleNamespace(data={4: 1, 8: 1, 10: 1, 3478: 1}, infos=infos, serial="S") if loaded else None
    entry = types.SimpleNamespace(entry_id="e1", options=options)
    if loaded: entry.runtime_data = coord
    f = cf.NibeOptionsFlow(); f.config_entry = entry; f.hass = "HASS"
    return f
field = lambda form, name: next(m for m in form["schema"] if m.schema == name)
form = asyncio.run(flow({"scan_interval": 45, "fast_points": [8], "fast_interval": 7}).async_step_init())
sel_cfg = form["schema"][field(form, "fast_points")][1]
check("options flow: form lists scan interval, season start, fast points and fast interval",
      [m.schema for m in form["schema"]] == ["scan_interval", "season_start_month", "fast_points", "fast_interval"] and form["errors"] == {})
check("options flow: only points with an enabled entity are offered, buttons and derived entities left out",
      [o["value"] for o in sel_cfg["options"]] == ["4", "8"] and sel_cfg["multiple"] is True and sel_cfg["options"][0]["label"] == "Outdoor [4]", sel_cfg["options"])
check("options flow: saved choice and intervals are the defaults",
      field(form, "fast_points").default == ["8"] and field(form, "fast_interval").default == 7 and field(form, "scan_interval").default == 45)
form = asyncio.run(flow({}).async_step_init())
check("options flow: defaults without saved options", field(form, "fast_points").default == [] and field(form, "fast_interval").default == 10 and field(form, "scan_interval").default == 30)
check("options flow: the season starts in October unless chosen otherwise", field(form, "season_start_month").default == 10)
check("options flow: a saved season start is the default",
      field(asyncio.run(flow({"season_start_month": 9}).async_step_init()), "season_start_month").default == 9)

res = asyncio.run(flow({"other": 1, "fast_points": [8]}).async_step_init({"scan_interval": 60, "fast_points": ["4", "8"], "fast_interval": 12}))
check("options flow: saved with point ids as integers, other options kept",
      res["type"] == "create_entry" and res["data"] == {"other": 1, "scan_interval": 60, "fast_points": [4, 8], "fast_interval": 12}, res)
res = asyncio.run(flow({"fast_points": [8]}).async_step_init({"scan_interval": 60, "fast_points": [], "fast_interval": 12}))
check("options flow: empty selection switches fast polling off", res["data"]["fast_points"] == [])
many = {100 + i: PI(f"Sensor {i}", "sensor") for i in range(12)}
reg_entries[:] = [Ent(f"S_{pid}") for pid in many]
def many_flow(options):
    f = flow(options); f.config_entry.runtime_data = types.SimpleNamespace(data={p: 1 for p in many}, infos=many, serial="S"); return f
typed = [str(100 + i) for i in range(11)]
res = asyncio.run(many_flow({}).async_step_init({"scan_interval": 60, "fast_points": typed, "fast_interval": 12}))
check("options flow: more than 10 points -> form with error, nothing saved",
      res["type"] == "form" and res["errors"] == {"fast_points": "too_many_points"})
check("options flow: after the error the form keeps what was typed", field(res, "fast_points").default == typed)
res = asyncio.run(many_flow({}).async_step_init({"scan_interval": 60, "fast_points": typed[:10], "fast_interval": 12}))
check("options flow: exactly 10 points is accepted", res["type"] == "create_entry" and res["data"]["fast_points"] == [int(v) for v in typed[:10]])
reg_entries[:] = [Ent("S_4"), Ent("S_8"), Ent("S_10", disabled="user"), Ent("S_smartmode"), Ent("OTHER_4")]
res = asyncio.run(flow({"scan_interval": 45, "fast_points": [8], "fast_interval": 7}, loaded=False).async_step_init())
check("options flow: entry not loaded -> only the update interval and the season start are offered", [m.schema for m in res["schema"]] == ["scan_interval", "season_start_month"])
res = asyncio.run(flow({"scan_interval": 45, "fast_points": [8], "fast_interval": 7}, loaded=False).async_step_init({"scan_interval": 90}))
check("options flow: entry not loaded -> saving keeps the fast-polling choice",
      res["data"] == {"scan_interval": 90, "fast_points": [8], "fast_interval": 7}, res)
reg_entries[:] = [Ent("S_4")]
form = asyncio.run(flow({"fast_points": [8]}).async_step_init())
check("options flow: a selected point whose entity is now disabled stays in the list",
      [o["value"] for o in form["schema"][field(form, "fast_points")][1]["options"]] == ["4", "8"])

# a saved id that no longer exists, or that has no usable entity kind, must not become an invalid default
reg_entries[:] = [Ent("S_4"), Ent("S_8")]
form = asyncio.run(flow({"fast_points": [999, 3478, 8]}).async_step_init())
check("options flow: stale or unusable saved ids are not offered as defaults (the selector would reject them)",
      field(form, "fast_points").default == ["8"], field(form, "fast_points").default)

# ------------------------------------------------------------------ translations and manifest
tr = json.load(open(SRC + "/translations/en.json", encoding="utf-8"))
step = tr["options"]["step"]["init"]
check("translations: every options field has a label and a description",
      {"scan_interval", "season_start_month", "fast_points", "fast_interval"} <= set(step["data"])
      and {"scan_interval", "season_start_month", "fast_points", "fast_interval"} <= set(step["data_description"]))
check("translations: error key used by the flow exists", "too_many_points" in tr["options"]["error"])
check("translations: config steps from 0.8.2 still there", {"user", "reauth_confirm", "reconfigure"} <= set(tr["config"]["step"]))
check("manifest: version is 0.8.3 or later", version_at_least(json.load(open(SRC + "/manifest.json"))["version"], "0.8.3"))
check("data.json: register table has no conflicting registers", not any(k in DATA["register_ranges"] for k in ("H0", "H1555", "H1556", "H1557", "H4100", "H4101")) and len(DATA["register_ranges"]) > 900)
check("data.json: every table entry is a [min, max] pair with min < max",
      all(isinstance(v, list) and len(v) == 2 and v[0] < v[1] for v in DATA["register_ranges"].values()))

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
