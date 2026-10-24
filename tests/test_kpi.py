import sys, asyncio, importlib.util, importlib, logging, types, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import SRC
import harness
harness.install()

spec = importlib.util.spec_from_file_location("nibe_local_api", SRC + "/__init__.py", submodule_search_locations=[SRC])
pkg = importlib.util.module_from_spec(spec); sys.modules["nibe_local_api"] = pkg; spec.loader.exec_module(pkg)

from nibe_local_api import kpi, const

results = []
def check(name, cond, detail=""):
    results.append(bool(cond)); print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))

def close(a, b, tol=1e-9):
    return a is not None and b is not None and abs(a - b) <= tol

# Steady heating: 20 L/min through a 6 K temperature rise = 8.3 kW of heat for 2 kW of electricity
STEADY = dict(priority=30, valve_hot_water=0, compressor_state=60, compressor_on=1, frequency_hz=60,
              power_w=2000, flow_lpm=20, supply_c=36, return_c=30)
IDLE = dict(priority=10, valve_hot_water=0, compressor_state=20, compressor_on=0, frequency_hz=0,
            power_w=0, flow_lpm=0, supply_c=30, return_c=30)
Q_STEADY, COP_STEADY = 8.3, 4.15

class Run:
    """Feeds a tracker one reading every 30 s, like the coordinator does."""
    def __init__(self, tracker=None, t0=1000.0, step=30.0):
        self.tr, self.t, self.step = tracker or kpi.CopTracker(), t0, step
        self.log = []
    def feed(self, seconds=None, **fields):
        r = self.tr.update(kpi.Sample(time=self.t, **fields))
        self.log.append((self.t, r)); self.t += self.step; return r
    def hold(self, seconds, **fields):
        out = None
        for _ in range(int(seconds / self.step)):
            out = self.feed(**fields)
        return out
    def skip(self, seconds): self.t += seconds

# ------------------------------------------------------------------ the calculation itself
run = Run()
r = run.feed(**IDLE)
check("idle pump: status idle, no heat, no COP", r.status == "idle" and r.heat_kw == 0.0 and r.cop is None and r.mode is None, r)
check("idle pump: nothing to show for either mode", run.tr.live_cop("heating") is None and run.tr.live_cop("hot_water") is None
      and run.tr.long_cop("heating") is None)
r = run.feed(**{**IDLE, "compressor_state": 40, "power_w": 400, "frequency_hz": 30})
check("compressor starting (state 40): still idle", r.status == "idle" and r.heat_kw == 0.0, r)
r = run.feed(**{**IDLE, "compressor_state": 100, "frequency_hz": 20, "flow_lpm": 20, "supply_c": 36, "return_c": 30})
check("compressor stopping (state 100): idle, heat output 0 even though the circulation pump still moves water", r.status == "idle" and r.heat_kw == 0.0, r)

run = Run()
statuses = [run.feed(**STEADY).status for _ in range(12)]
check("steady heating: settles for 300 s, then counts",
      statuses[:10] == ["settling"] * 10 and statuses[10] == "ok", statuses)
check("steady heating: a reading that settles reports the time left", run.log[0][1].settle_left_s == 300 and run.log[5][1].settle_left_s == 150, [round(r.settle_left_s) for _, r in run.log[:7]])
check("steady heating: heat output is shown from the first reading, also while settling", close(run.log[0][1].heat_kw, Q_STEADY), run.log[0][1].heat_kw)
check("steady heating: single-reading COP", close(run.log[10][1].cop, COP_STEADY), run.log[10][1].cop)
run.hold(600, **STEADY)
check("live COP: heat over electricity of the counted readings", close(run.tr.live_cop("heating"), COP_STEADY), run.tr.live_cop("heating"))
check("24 h COP agrees while nothing else happened", close(run.tr.long_cop("heating"), COP_STEADY))
check("hot water COP stays empty during a heating run", run.tr.live_cop("hot_water") is None and run.tr.long_cop("hot_water") is None)
valid, heat, power = run.tr.window("heating", 900)
check("window sums: kWh of heat and electricity of the counted seconds", close(heat / power, COP_STEADY) and close(power, 2.0 * valid / 3600, 1e-6), (valid, heat, power))

# live COP is only given when the first counted reading is in; 4 counted readings = 120 s
run = Run(); run.hold(300, **STEADY)
vals = []
for _ in range(6):
    run.feed(**STEADY); vals.append(run.tr.live_cop("heating"))
check("live COP appears once 2 minutes were counted (readings 1-3 are too little)",
      vals[:3] == [None, None, None] and close(vals[3], COP_STEADY), vals)

# ------------------------------------------------------------------ pump goes idle: live empties, 24 h stays
run.hold(600, **STEADY)
run.hold(120, **IDLE)
check("pump idle after a run: live COP is empty", run.tr.live_cop("heating") is None)
check("pump idle after a run: the 24 h COP stays", close(run.tr.long_cop("heating"), COP_STEADY))
check("pump idle after a run: heat output back to 0", run.tr.last.heat_kw == 0.0)

# ------------------------------------------------------------------ switching between modes
run = Run(); run.hold(900, **STEADY)
r = run.feed(**{**STEADY, "priority": 20})                 # priority moved, the valve has not
check("priority says hot water, valve still on heating: nothing counts (valve is moving)", r.status == "other operation" and r.mode is None, r)
check("... and the live heating COP is gone for now", run.tr.live_cop("heating") is None)
r = run.feed(**{**STEADY, "priority": 20, "valve_hot_water": 1})
check("both agree on hot water: settling starts from zero", r.status == "settling" and r.settle_left_s == 300, r)
run.hold(240, **{**STEADY, "priority": 20, "valve_hot_water": 1})
check("hot water: no COP before the 300 s are over", run.tr.live_cop("hot_water") is None and run.tr.long_cop("hot_water") is None)
run.hold(300, **{**STEADY, "priority": 20, "valve_hot_water": 1})
check("hot water: COP after settling, with its own counted data", close(run.tr.live_cop("hot_water"), COP_STEADY))
check("hot water readings did not leak into the heating COP", run.tr.window("heating", 86400)[0] < run.tr.window("hot_water", 86400)[0] + 700
      and run.tr.live_cop("heating") is None)
check("heating keeps its 24 h value from before the switch", close(run.tr.long_cop("heating"), COP_STEADY))
r = run.feed(**{**STEADY, "priority": 30, "valve_hot_water": 1})
check("priority back to heating but valve still on hot water: not counted", r.status == "other operation", r)
r = run.feed(**STEADY)
check("heating again: settling restarts from zero", r.status == "settling" and r.settle_left_s == 300, r)

other = {}
for name, fields in {"off": dict(priority=10), "pool": dict(priority=40), "cooling": dict(priority=60)}.items():
    rr = Run(); rr.hold(600, **STEADY); other[name] = rr.feed(**{**STEADY, **fields})
check("off, pool and cooling are not heating or hot water: not counted",
      all(v.status == "other operation" and v.mode is None for v in other.values()), other)
rr = Run(); rr.hold(600, **{**STEADY, "priority": 20, "valve_hot_water": None})
check("a pump without the valve point: the priority alone decides", rr.log[-1][1].status == "ok" and rr.log[-1][1].mode == "hot_water", rr.log[-1][1])

# ------------------------------------------------------------------ spikes and transitions
run = Run(); run.hold(900, **STEADY)
r = run.feed(**{**STEADY, "return_c": 20})                 # BT3 spikes: temperature rise jumps by 10 K
check("spike in the return temperature: reading dropped (step in the temperature difference)", r.status == "unsteady" and r.cop is None, r)
r = run.feed(**STEADY)
check("... and the way back is a step too, still dropped", r.status == "unsteady", r)
quiet = [run.feed(**STEADY).status for _ in range(5)]
check("after the last step the pump must be steady for 2 minutes again", quiet[:3] == ["unsteady"] * 3 and quiet[4] == "ok", quiet)
check("the dropped readings never reached the energy sums", close(run.tr.long_cop("heating"), COP_STEADY))

for label, fields in {
        "flow spike": dict(flow_lpm=45), "power spike": dict(power_w=3500), "frequency jump": dict(frequency_hz=95)}.items():
    rr = Run(); rr.hold(600, **STEADY)
    check(f"{label}: dropped as a transition", rr.feed(**{**STEADY, **fields}).status == "unsteady")

rr = Run(); rr.hold(600, **STEADY)
a = rr.feed(**{**STEADY, "power_w": 2300, "frequency_hz": 66})
check("a slow change (15 % power, 6 Hz) is a trend, not a step", a.status == "ok", a)

# a reading that is steady but physically implausible
bad = dict(STEADY, supply_c=50, power_w=1500)              # 20 K at 20 L/min on 1.5 kW = COP 18.5
rr = Run(); r = rr.hold(600, **bad)
check("implausible COP (18.5): rejected and counted as such", r.status == "implausible" and r.cop is None and rr.tr.rejected["heating"] > 0, (r, rr.tr.rejected))
check("implausible readings do not give a COP", rr.tr.long_cop("heating") is None and rr.tr.live_cop("heating") is None)
rr = Run(); r = rr.hold(600, **dict(STEADY, supply_c=30.5, flow_lpm=4))
check("COP below 0.8 is rejected as well (rise 0.5 K is also below the sensor accuracy)", r.status == "out of range", r)
rr = Run(); r = rr.hold(600, **dict(STEADY, supply_c=31.5, flow_lpm=5, power_w=2000))
check("a temperature rise of 1.5 K and a COP of 0.17: rejected as implausible", r.status == "implausible", r)

for label, fields in {
        "power below the minimum": dict(power_w=80), "flow below the minimum": dict(flow_lpm=1.5),
        "temperature rise below 1 K": dict(supply_c=30.6), "temperature rise above 25 K": dict(supply_c=58)}.items():
    rr = Run(); r = rr.hold(600, **{**STEADY, **fields})
    check(f"{label}: out of range, not counted", r.status == "out of range" and r.cop is None, r)

# a real reading from an S1155 at minimum speed (export of 2026-10-24): 24 Hz, 206 W, 15.1 L/min, 26.1 / 24.0 degC.
# The pump's own hourly log for that hour says 2.27 kWh produced for 0.24 kWh used (9.5); 0.10.0 dropped it.
REAL = dict(priority=30, valve_hot_water=0, compressor_state=60, compressor_on=1, frequency_hz=24, power_w=206,
            flow_lpm=15.1, supply_c=26.1, return_c=24.0, defrost=0)
rr = Run(); r = rr.hold(900, **REAL)
real_cop = 15.1 / 60 * 4.15 * 2.1 * 1000 / 206
check("real low-load reading (206 W, 2.1 K rise) counts, COP about 10.6", r.status == "ok" and close(r.cop, real_cop, 1e-6) and 10.5 < r.cop < 10.7, r)
check("... and shows as live COP", close(rr.tr.live_cop("heating"), real_cop, 1e-6), rr.tr.live_cop("heating"))

# ------------------------------------------------------------------ defrost, missing data, gaps
rr = Run(); rr.hold(600, **STEADY)
r = rr.feed(**{**STEADY, "defrost": 1})
check("defrosting: not counted", r.status == "defrost", r)
r = rr.feed(**STEADY)
check("after the defrost the settling starts again", r.status == "settling" and r.settle_left_s == 300, r)
rr = Run(); rr.hold(600, **{**STEADY, "defrost": 0})
check("defrost point present and 0: counts", rr.log[-1][1].status == "ok")
rr = Run(); rr.hold(600, **{**STEADY, "defrost": 2})
check("defrost value 2 (passive) is not a defrost", rr.log[-1][1].status == "ok")

rr = Run(); rr.hold(600, **STEADY)
r = rr.feed(**{**STEADY, "flow_lpm": None})
check("flow reading missing while running: no data, no heat output", r.status == "no data" and r.heat_kw is None, r)
r = rr.feed(**{**STEADY, "power_w": None})
check("power reading missing while running: no data, heat output still known", r.status == "no data" and close(r.heat_kw, Q_STEADY), r)
r = rr.feed(**{**STEADY, "priority": None})
check("priority missing while running: no data", r.status == "no data", r)
r = rr.feed(**{**STEADY, "compressor_state": None, "compressor_on": None})
check("no way to tell whether the compressor runs: no data", r.status == "no data" and r.heat_kw is None, r)
rr = Run(); rr.hold(600, **{**STEADY, "compressor_state": None})
check("without the state point the 'compressor running' flag is used", rr.log[-1][1].status == "ok")
rr = Run(); r = rr.hold(600, **{**STEADY, "compressor_state": None, "compressor_on": 0})
check("... and 0 means idle", r.status == "idle")
rr = Run(); r = rr.hold(600, **{**STEADY, "frequency_hz": 0})
check("compressor reported running at 0 Hz: idle", r.status == "idle")

rr = Run(); rr.hold(600, **STEADY); before = rr.tr.window("heating", 86400)
rr.skip(240)                                               # no update for 4 minutes (poll errors, restart of the link)
r = rr.feed(**STEADY)
check("longer gap than 150 s: nothing is integrated across it and settling starts again", r.status == "settling" and rr.tr.window("heating", 86400) == before, (r, before))
rr = Run(); rr.hold(600, **STEADY); before = rr.tr.window("heating", 86400)[0]
rr.skip(60); r = rr.feed(**STEADY)
check("a missed update (90 s apart) is still one run of data", r.status == "ok" and rr.tr.window("heating", 86400)[0] == before + 90, (r, before))
rr = Run(); rr.hold(600, **STEADY)
rr.tr.update(kpi.Sample(time=rr.t - 500, **STEADY))
check("a clock that goes backwards does not integrate negative time", min(e[1] for e in rr.tr._entries["heating"]) > 0)

# ------------------------------------------------------------------ energy weighting and windows
rr = Run(); rr.hold(600, **STEADY)
for _ in range(20): rr.feed(**dict(STEADY, power_w=2000))
for _ in range(20): rr.feed(**dict(STEADY, power_w=2400, frequency_hz=66))
valid, heat, power = rr.tr.window("heating", 86400)
n1 = (valid - 20 * 30) / 30; n2 = 20
expected = (Q_STEADY * (n1 + n2)) / (2.0 * n1 + 2.4 * n2)
mean_of_ratios = (COP_STEADY * n1 + (Q_STEADY / 2.4) * n2) / (n1 + n2)
check("COP is energy over energy, not an average of single readings", close(rr.tr.long_cop("heating"), expected, 1e-6) and abs(expected - mean_of_ratios) > 0.005,
      (rr.tr.long_cop("heating"), expected, mean_of_ratios))

rr = Run(); rr.hold(300 + 1800, **STEADY)
valid = rr.tr.window("heating", 900)[0]
check("live window covers the last 15 minutes only", 870 <= valid <= 900, valid)

rr = Run(); rr.hold(900, **STEADY)
t_end = rr.t
rr.hold(23 * 3600, **IDLE)
check("24 h value is still there after 23 hours of idling", rr.tr.long_cop("heating") is not None)
rr.hold(2 * 3600, **IDLE)
check("24 h value is gone after 25 hours: old readings expire", rr.tr.long_cop("heating") is None and rr.tr.window("heating", 86400)[0] == 0)
check("expired readings are freed", len(rr.tr._entries["heating"]) == 0)

rr = Run(); rr.hold(300 + 120, **STEADY)
check("a very short run (2.5 minutes counted) is not enough for a 24 h value",
      rr.tr.long_cop("heating") is None and rr.tr.window("heating", 86400)[2] < rr.tr.cfg.min_long_energy_kwh, rr.tr.window("heating", 86400))
rr.hold(300, **STEADY)
check("... a longer one is", close(rr.tr.long_cop("heating"), COP_STEADY), rr.tr.window("heating", 86400))

# ------------------------------------------------------------------ the point map and the helpers
def table(**vals):
    return {pid: {} for pid in vals}
ids = const.KPI_POINTS
full = {ids[k]: {} for k in ("priority", "flow", "supply", "return", "power", "state")}
check("available: the essential points present", kpi.available(full))
check("available: 'compressor running' can stand in for the state", kpi.available({**{k: v for k, v in full.items() if k != ids["state"]}, ids["running"]: {}}))
check("available: average power can stand in for the instantaneous one", kpi.available({**{k: v for k, v in full.items() if k != ids["power"]}, ids["power_avg"]: {}}))
for name in ("priority", "flow", "supply", "return"):
    check(f"available: no {name} point -> no COP sensors", not kpi.available({k: v for k, v in full.items() if k != ids[name]}))
check("available: no compressor state or running flag -> no COP sensors", not kpi.available({k: v for k, v in full.items() if k != ids["state"]}))
check("available: empty table", not kpi.available({}))
check("KPI point ids match the catalog points they are named after",
      (ids["priority"], ids["valve"], ids["state"], ids["running"], ids["freq"], ids["power"], ids["flow"], ids["supply"], ids["return"], ids["defrost"])
      == (1758, 2002, 2556, 1973, 1799, 1801, 58, 15, 10, 3126))

vals = {1758: 30, 2002: 0, 2556: 60, 1799: 55, 1801: None, 1932: 1900, 58: 20, 15: 36, 10: 30}
s = kpi.build_sample(5.0, lambda pid: vals.get(pid))
check("build_sample: fields come from the right points", (s.priority, s.valve_hot_water, s.compressor_state, s.frequency_hz, s.flow_lpm, s.supply_c, s.return_c)
      == (30, 0, 60, 55, 20, 36, 30) and s.time == 5.0 and s.defrost is None and s.compressor_on is None)
check("build_sample: average power used when the instantaneous reading is missing", s.power_w == 1900)
vals[1801] = 2100
check("build_sample: instantaneous power preferred", kpi.build_sample(0, lambda pid: vals.get(pid)).power_w == 2100)

# ------------------------------------------------------------------ in the coordinator
def point(pid, value, divisor=1, size="s16"):
    return {"metadata": {"variableId": pid, "variableType": "integer", "variableSize": size, "divisor": divisor},
            "value": {"isOk": True, "integerValue": None if value is None else round(value * divisor)}}

class Api:
    def __init__(self, with_kpi=True): self.v, self.with_kpi = dict(STEADY, defrost=0), with_kpi
    async def get_points(self):
        v = self.v
        t = {2509: point(2509, 1038)}
        if not self.with_kpi: return t
        t.update({1758: point(1758, v["priority"]), 2002: point(2002, v["valve_hot_water"]), 2556: point(2556, v["compressor_state"]),
                  1973: point(1973, v["compressor_on"]), 1799: point(1799, v["frequency_hz"]), 1801: point(1801, v["power_w"]),
                  1932: point(1932, v["power_w"]), 58: point(58, v["flow_lpm"], 10), 15: point(15, v["supply_c"], 10),
                  10: point(10, v["return_c"], 10), 3126: point(3126, v["defrost"])})
        return t
    async def get_device(self): return {}
    async def get_notifications(self): return []

clock = [5000.0]
pkg.time = types.SimpleNamespace(monotonic=lambda: clock[0])
pkg.dr = types.SimpleNamespace(async_get=lambda hass: types.SimpleNamespace(
    async_get_device=lambda identifiers=None, connections=None: None, async_update_device=lambda *a, **k: None))

class Cap(logging.Handler):
    def __init__(self): super().__init__(); self.recs = []
    def emit(self, r): self.recs.append(r)
cap = Cap(); lg = logging.getLogger("nibe_local_api"); lg.addHandler(cap); lg.setLevel(logging.DEBUG)

def mk(api, options=None, keep_files=False):
    if not keep_files: harness.Store.files.clear()      # a fresh .storage folder unless the test is about a restart
    return pkg.NibeCoordinator("HASS", types.SimpleNamespace(options=options or {}), api, {"serial": "S", "name": "N", "manufacturer": "NIBE", "firmware": ""})
def poll(c, seconds=30):
    clock[0] += seconds
    c.data = asyncio.run(c._async_update_data())

c = mk(Api(with_kpi=False))
poll(c)
check("coordinator: pump without the points -> no tracker, update works", c.kpi is None and 2509 in c.data)

api = Api(); c = mk(api)
check("coordinator: no tracker before the first table", c.kpi is None)
poll(c)
check("coordinator: tracker created from the first table that has the points", c.kpi is not None and c.kpi.last.status == "settling")
check("coordinator: raw values are scaled (flow 20.0 L/min, 36.0 / 30.0 °C -> 8.3 kW)", close(c.kpi.last.heat_kw, Q_STEADY, 1e-6), c.kpi.last.heat_kw)
for _ in range(25): poll(c)
check("coordinator: COP after 12 minutes of steady running", close(c.kpi.live_cop("heating"), COP_STEADY, 1e-6), c.kpi.live_cop("heating"))
check("coordinator: default tolerance for a missed update is 150 s", c.kpi.cfg.max_gap_s == 150.0)
c120 = mk(Api(), {"scan_interval": 120}); poll(c120, 120)
check("coordinator: long update interval widens it (2.5 x 120 s)", c120.kpi.cfg.max_gap_s == 300.0, c120.kpi.cfg.max_gap_s)

api.v.update(compressor_state=20, compressor_on=0, frequency_hz=0, power_w=0, priority=10)
poll(c)
check("coordinator: pump stops -> live COP empty, 24 h COP kept, heat output 0",
      c.kpi.live_cop("heating") is None and close(c.kpi.long_cop("heating"), COP_STEADY, 1e-6) and c.kpi.last.heat_kw == 0.0)

# an error inside the calculation must not break the regular update
real = pkg.build_sample
def boom(*a, **k): raise RuntimeError("bug")
pkg.build_sample = boom
cap.recs.clear(); c = mk(Api())
data = asyncio.run(c._async_update_data()); poll(c)
check("coordinator: error in the calculation -> table still returned", 2509 in data and 1758 in data)
check("coordinator: error logged once, calculation switched off", len([r for r in cap.recs if r.levelno >= logging.ERROR]) == 1 and c._kpi_failed)
pkg.build_sample = real

# ------------------------------------------------------------------ the sensors
sc = sys.modules["homeassistant.components.sensor"]
sc.SensorEntity = type("SensorEntity", (), {})
sensor = importlib.import_module("nibe_local_api.sensor")

api = Api(); c = mk(api)
for _ in range(30): poll(c)
ent = {(m, long): sensor.NibeCopSensor(c, m, long) for m in ("heating", "hot_water") for long in (False, True)}
heat_out = sensor.NibeHeatOutputSensor(c)

check("sensors: names", [e._attr_name for e in ent.values()] == ["COP heating", "COP heating (24 h)", "COP hot water", "COP hot water (24 h)"],
      [e._attr_name for e in ent.values()])
check("sensors: unique ids", sorted(e._attr_unique_id for e in ent.values()) == ["S_cop_heating", "S_cop_heating_24h", "S_cop_hot_water", "S_cop_hot_water_24h"]
      and heat_out._attr_unique_id == "S_heat_output_calc", [e._attr_unique_id for e in ent.values()])
check("sensors: no point context (they follow the full update only)", all(e.coordinator_context is None for e in [*ent.values(), heat_out]))
check("sensors: shown values, heating run", close(ent[("heating", False)].native_value, COP_STEADY, 1e-6) and close(ent[("heating", True)].native_value, COP_STEADY, 1e-6))
check("sensors: hot water has nothing yet", ent[("hot_water", False)].native_value is None and ent[("hot_water", True)].native_value is None)
check("sensors: heat output in kW", close(heat_out.native_value, Q_STEADY, 1e-6) and heat_out._attr_native_unit_of_measurement == "kW")
a = ent[("heating", False)].extra_state_attributes
check("sensors: attributes explain the number", a["status"] == "ok" and a["window_minutes"] == 15 and 9.5 <= a["counted_minutes"] <= 10.5
      and close(a["heat_kwh"] / a["electricity_kwh"], COP_STEADY, 0.02) and a["rejected_readings"] == 0, a)
check("sensors: 24 h window attribute", ent[("heating", True)].extra_state_attributes["window_minutes"] == 1440)
check("sensors: the 24 h value is ok, the hot water one says it is still collecting data",
      ent[("heating", True)].extra_state_attributes["status"] == "ok" and ent[("hot_water", True)].extra_state_attributes["status"] == "collecting data: 0.00 of 0.1 kWh of electricity"
      and ent[("heating", True)].extra_state_attributes["settling_seconds_left"] is None, (ent[("heating", True)].extra_state_attributes, ent[("hot_water", True)].extra_state_attributes))
check("sensors: changing attributes are kept out of the database",
      set(a) <= set(sensor.NibeCopSensor._unrecorded_attributes) and "status" in sensor.NibeHeatOutputSensor._unrecorded_attributes)

api.v.update(priority=20, valve_hot_water=1); poll(c)
a = ent[("hot_water", False)].extra_state_attributes
check("sensors: mode switch -> status and time left are visible", a["status"] == "settling" and a["settling_seconds_left"] == 300
      and ent[("heating", False)].native_value is None and close(ent[("heating", True)].native_value, COP_STEADY, 1e-6), a)
api.v.update(compressor_state=20, compressor_on=0, frequency_hz=0, power_w=0, priority=10, valve_hot_water=0); poll(c)
check("sensors: idle -> live COP unknown, status idle, heat output 0",
      ent[("heating", False)].native_value is None and ent[("heating", False)].extra_state_attributes["status"] == "idle"
      and heat_out.native_value == 0.0 and heat_out.extra_state_attributes["status"] == "idle")
check("sensors: heat output is a power in kW",
      heat_out._attr_device_class is sensor.SensorDeviceClass.POWER and heat_out._attr_native_unit_of_measurement == "kW")

setup_src = open(SRC + "/sensor.py").read().split("async def async_setup_entry")[1].split("\ndef _heater_values")[0]
check("setup: the COP sensors are only added when the pump reports the points (coordinator.kpi)",
      "if coordinator.kpi is not None" in setup_src and setup_src.count("NibeCopSensor(") == 4 and "NibeHeatOutputSensor(coordinator)" in setup_src)

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
