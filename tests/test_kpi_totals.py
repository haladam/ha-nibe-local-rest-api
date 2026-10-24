import sys, asyncio, importlib.util, importlib, logging, types, json, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import SRC
import harness
harness.install()

spec = importlib.util.spec_from_file_location("nibe_local_api", SRC + "/__init__.py", submodule_search_locations=[SRC])
pkg = importlib.util.module_from_spec(spec); sys.modules["nibe_local_api"] = pkg; spec.loader.exec_module(pkg)

from nibe_local_api import kpi, kpi_totals as kt, const

results = []
def check(name, cond, detail=""):
    results.append(bool(cond)); print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))

def close(a, b, tol=1e-6):
    return a is not None and b is not None and abs(a - b) <= tol

# 20 L/min through a 6 K rise = 8.3 kW of heat for 2 kW of electricity (COP 4.15)
STEADY = dict(priority=30, valve_hot_water=0, compressor_state=60, compressor_on=1, frequency_hz=60,
              power_w=2000, flow_lpm=20, supply_c=36, return_c=30)
WATER = dict(STEADY, priority=20, valve_hot_water=1)
IDLE = dict(priority=10, valve_hot_water=0, compressor_state=20, compressor_on=0, frequency_hz=0,
            power_w=0, flow_lpm=0, supply_c=30, return_c=30)
Q, P = 8.3, 2.0

class Feed:
    """Feeds an EnergyTotals one reading every 30 s."""
    def __init__(self, totals=None, day="2026-10-24", t0=1000.0, step=30.0):
        self.tot, self.day, self.t, self.step, self.started = totals or kt.EnergyTotals(season_month=10), day, t0, step, False
    def feed(self, counters=None, **fields):
        self.tot.update(kpi.Sample(time=self.t, **fields), self.day, counters); self.t += self.step; self.started = True
    def hold(self, seconds, counters=None, **fields):
        """`seconds` worth of intervals: the very first reading of a Feed only starts the first interval."""
        for _ in range(int(seconds / self.step) + (0 if self.started else 1)): self.feed(counters, **fields)

# ------------------------------------------------------------------ season_start
from datetime import date
check("season_start: October season, in the season and after New Year",
      kt.season_start(date(2026, 10, 24), 10) == date(2026, 10, 1) and kt.season_start(date(2026, 3, 5), 10) == date(2025, 10, 1)
      and kt.season_start(date(2026, 10, 1), 10) == date(2026, 10, 1) and kt.season_start(date(2026, 9, 30), 10) == date(2025, 10, 1))
check("season_start: January season is the calendar year, December season starts last December in spring",
      kt.season_start(date(2026, 6, 1), 1) == date(2026, 1, 1) and kt.season_start(date(2026, 6, 1), 12) == date(2025, 12, 1))

# ------------------------------------------------------------------ the totals
f = Feed(); f.hold(3600, **STEADY)
heat, el = f.tot.lifetime_sums("heating")
check("one hour of steady heating: 8.3 kWh of heat for 2.0 kWh of electricity", close(heat, Q) and close(el, P), (heat, el))
check("hot water and other stay at zero, total equals heating",
      f.tot.lifetime_sums("hot_water") == (0.0, 0.0) and f.tot.lifetime_sums("other") == (0.0, 0.0) and close(f.tot.lifetime_sums("total")[1], P))
check("COP is heat over electricity", close(f.tot.cop(heat, el), 4.15))
check("compressor run time of the day: one hour", close(f.tot.today("2026-10-24")["run_s"], 3600, 1e-3), f.tot.today("2026-10-24")["run_s"])
check("the first reading counted is the day counting began", f.tot.since == "2026-10-24")
check("coverage: everything was seen", close(f.tot.coverage(), 1.0) and close(f.tot.counted_s, 3600))

f = Feed(); f.hold(3600, **IDLE)
check("idle pump: nothing is counted, coverage still 1", f.tot.lifetime_sums("total") == (0.0, 0.0) and close(f.tot.coverage(), 1.0) and f.tot.today("2026-10-24")["run_s"] == 0)

# the electricity of a start-up counts although the heat arrives late: COP lower than steady
f = Feed()
f.feed(**IDLE)
for _ in range(10): f.feed(**dict(STEADY, supply_c=30.6))     # 5 minutes with only 0.6 K of rise: 0.83 kW of heat
heat, el = f.tot.lifetime_sums("heating")
check("start-up: all electricity counted, little heat: COP far below steady", el > 0.15 and heat / el < 1.0, (heat, el))
f.hold(1800, **STEADY)
check("... and the COP recovers towards steady as the run goes on", 3.4 < f.tot.cop(*f.tot.lifetime_sums("heating")) < 4.15)

# trapezoid: a run that ends within an interval counts half of that interval
f = Feed(); f.feed(**STEADY); f.feed(**IDLE)
heat, el = f.tot.lifetime_sums("heating")
check("run ends: half an interval of the last reading's rate", close(el, P * 15 / 3600) and close(heat, Q * 15 / 3600), (heat, el))
f = Feed(); f.feed(**IDLE); f.feed(**STEADY)
check("run starts: the same on the other side", close(f.tot.lifetime_sums("heating")[1], P * 15 / 3600))

# each end goes to the mode it was measured in
f = Feed(); f.feed(**STEADY); f.feed(**WATER)
check("heating then hot water: half an interval each", close(f.tot.lifetime_sums("heating")[1], P * 15 / 3600) and close(f.tot.lifetime_sums("hot_water")[1], P * 15 / 3600))
f = Feed(); f.feed(**STEADY); f.feed(**dict(STEADY, priority=20))          # priority moved, the valve has not
check("priority and valve disagree: that end goes to other",
      close(f.tot.lifetime_sums("other")[1], P * 15 / 3600) and close(f.tot.lifetime_sums("heating")[1], P * 15 / 3600))
check("... other is part of the total", close(f.tot.lifetime_sums("total")[1], P * 30 / 3600))
f = Feed(); f.hold(600, **dict(STEADY, priority=40));
check("pool operation: counted as other, not as heating", f.tot.lifetime_sums("heating") == (0.0, 0.0) and f.tot.lifetime_sums("other")[1] > 0.3)
f = Feed(); f.hold(600, **dict(STEADY, priority=None))
check("priority missing while the compressor runs: other", f.tot.lifetime_sums("other")[1] > 0.3)

# readings that cannot be trusted do not count for either side
f = Feed(); f.hold(300, **STEADY); before = f.tot.lifetime_sums("total")
f.feed(**dict(STEADY, flow_lpm=None)); f.feed(**STEADY)
check("flow missing for one reading: the two intervals around it count for nothing",
      f.tot.lifetime_sums("total") == before and close(f.tot.skipped_s, 60), (f.tot.lifetime_sums("total"), before, f.tot.skipped_s))
check("... and the coverage says so", f.tot.coverage() < 1.0)
f.feed(**STEADY)
check("counting continues afterwards", f.tot.lifetime_sums("total")[1] > before[1])
f = Feed(); f.hold(300, **STEADY); before = f.tot.lifetime_sums("total")
f.feed(**dict(STEADY, power_w=None)); f.feed(**STEADY)
check("power missing: skipped as well", f.tot.lifetime_sums("total") == before)
f = Feed(); f.hold(300, **STEADY); before = f.tot.lifetime_sums("total")
f.feed(**dict(STEADY, flow_lpm=400)); f.feed(**STEADY)
check("heat above 30 kW is a sensor glitch: skipped", f.tot.lifetime_sums("total") == before)
f = Feed(); f.hold(300, **dict(STEADY, supply_c=29, return_c=30))
check("negative temperature rise: no heat, electricity still counted", f.tot.lifetime_sums("heating")[0] == 0.0 and f.tot.lifetime_sums("heating")[1] > 0.15)
f = Feed(); f.hold(300, **dict(IDLE, power_w=5))
check("a few watts is not a running compressor", f.tot.lifetime_sums("total") == (0.0, 0.0))

f = Feed(); f.hold(300, **STEADY); before = f.tot.lifetime_sums("total")
f.t += 300; f.feed(**STEADY); f.feed(**STEADY)
heat, el = f.tot.lifetime_sums("total")
check("a pause longer than 150 s is not integrated (Home Assistant was down), the next interval is",
      close(f.tot.gap_s, 330) and close(el - before[1], P * 30 / 3600), (f.tot.gap_s, el - before[1]))
f = Feed(); f.hold(300, **STEADY); before = f.tot.lifetime_sums("total")
f.t -= 500; f.feed(**STEADY)
check("a clock that goes backwards adds nothing", f.tot.lifetime_sums("total") == before)

# ------------------------------------------------------------------ days, seasons, starts
f = Feed(day="2026-09-30"); f.hold(3600, **STEADY)
f.day = "2026-10-01"; f.hold(7200, **STEADY)
f.day = "2026-10-24"; f.hold(3600, **STEADY)
check("lifetime: every day", close(f.tot.lifetime_sums("heating")[1], 4 * P, 1e-3), f.tot.lifetime_sums("heating"))
check("season (from 1 October): without the day before it", close(f.tot.season_sums("heating", "2026-10-24")[1], 3 * P, 1e-3), f.tot.season_sums("heating", "2026-10-24"))
check("previous season: what lies between last 1 October and this one", close(f.tot.season_sums("heating", "2026-10-24", previous=True)[1], P, 1e-3), f.tot.season_sums("heating", "2026-10-24", previous=True))
check("the season ending 1 October 2026 starts on 1 October 2025", close(f.tot.season_sums("heating", "2026-09-30")[1], P, 1e-3))
check("today: its own energy and run time only", close(f.tot.today("2026-10-24")["run_s"], 3600, 1e-3) and close(f.tot.today("2026-10-01")["run_s"], 7200, 1e-3) and f.tot.today("2026-12-01")["starts"] == 0)
check("season_since: the season's first day or the day counting began, whichever is later",
      f.tot.season_since("2026-10-24") == "2026-10-01" and f.tot.season_since("2027-03-01") == "2026-10-01" and f.tot.season_since("2026-09-30") == "2026-09-30")
f2 = Feed(); f2.hold(300, **STEADY)
check("season_since: counting began after the season started", f2.tot.season_since("2026-10-24") == "2026-10-24")
check("a COP needs 0.25 kWh of electricity first (5 minutes at 2 kW is 0.17)", f2.tot.cop(*f2.tot.lifetime_sums("heating")) is None and f.tot.cop(*f.tot.lifetime_sums("heating")) is not None)
check("... a different minimum can be asked for", f2.tot.cop(*f2.tot.lifetime_sums("heating"), minimum=0.1) is not None and f2.tot.cop(*f2.tot.lifetime_sums("heating"), minimum=1.0) is None)
check("collecting: says how far it is", f2.tot.collecting(0.17) == "collecting data: 0.17 of 0.25 kWh of electricity" and f2.tot.collecting(0.3) == "ok" and f2.tot.collecting(0.4, 1.0) == "collecting data: 0.40 of 1 kWh of electricity")

# the real operating point of an S1155 at minimum speed (24 Hz, 206 W, 15.1 L/min, 26.1 / 24.0 degC) draws 0.2 kWh an hour
REAL = dict(priority=30, valve_hot_water=0, compressor_state=60, compressor_on=1, frequency_hz=24, power_w=206, flow_lpm=15.1, supply_c=26.1, return_c=24.0, defrost=0)
fr = Feed(); fr.hold(3600, **REAL)
check("at minimum speed one hour is not enough electricity for a seasonal COP yet", fr.tot.cop(*fr.tot.lifetime_sums("total")) is None, fr.tot.lifetime_sums("total"))
fr.hold(1200, **REAL)
check("... 80 minutes are: COP 10.6", close(fr.tot.cop(*fr.tot.lifetime_sums("total")), 15.1 / 60 * 4.15 * 2.1 * 1000 / 206, 1e-6), fr.tot.cop(*fr.tot.lifetime_sums("total")))
check("a COP without any electricity is unknown", f2.tot.cop(0.0, 0.0) is None and f2.tot.cop(5.0, 0.0) is None)

# a September start of the season
f = Feed(totals=kt.EnergyTotals(season_month=9), day="2026-08-31"); f.hold(3600, **STEADY)
f.day = "2026-09-01"; f.hold(3600, **STEADY)
check("season starting in September: 31 August belongs to the previous one", close(f.tot.season_sums("heating", "2026-09-15")[1], P, 1e-3) and close(f.tot.season_sums("heating", "2026-09-15", previous=True)[1], P, 1e-3))
check("season month outside 1-12 is clamped", kt.EnergyTotals(season_month=0).season_month == 1 and kt.EnergyTotals(season_month=13).season_month == 12)

# the pump's own counters
f = Feed(); c0 = {"starts": 100, "heating": 1000.0, "hot_water": 200.0, "total_heat": 1200.0, "total_el": 300.0}
cur = dict(c0)
f.feed(dict(cur), **STEADY)
cur.update(starts=102, heating=1010.0, total_heat=1210.0, total_el=302.0); f.feed(dict(cur), **STEADY)
check("starts: counted between two readings", f.tot.today("2026-10-24")["starts"] == 2)
cur.update(starts=1); f.feed(dict(cur), **STEADY)
check("starts: a counter that goes down (reset) is ignored", f.tot.today("2026-10-24")["starts"] == 2)
cur.update(starts=500); f.feed(dict(cur), **STEADY)
check("starts: an implausible jump is ignored", f.tot.today("2026-10-24")["starts"] == 2)
cur.update(starts=501); f.feed(dict(cur), **STEADY)
check("starts: counting continues from the new value", f.tot.today("2026-10-24")["starts"] == 3)
cur.update(starts=504); f.t += 600; f.feed(dict(cur), **STEADY)
check("starts during a pause (Home Assistant down) are not counted into today", f.tot.today("2026-10-24")["starts"] == 3)
check("pump counters: change since the first reading", close(f.tot.pump_delta("heating"), 10.0) and f.tot.pump_delta("hot_water") == 0.0)
check("pump counters: season baseline is the first reading of the season", close(f.tot.pump_delta("total_heat", season=True), 10.0) and close(f.tot.pump_delta("total_el", season=True), 2.0) and f.tot.season_from == "2026-10-24")
check("pump counters: unknown key", f.tot.pump_delta("nonsense") is None)
cur.update(total_heat=1300.0, total_el=320.0); f.day = "2026-12-01"; f.feed(dict(cur), **STEADY)
check("pump counters: still the same season in December", close(f.tot.pump_delta("total_heat", season=True), 100.0))
cur.update(total_heat=1900.0, total_el=420.0); f.day = "2027-10-01"; f.feed(dict(cur), **STEADY)
check("pump counters: a new season starts from the first reading of 1 October", f.tot.pump_delta("total_heat", season=True) == 0.0 and f.tot.season_from == "2027-10-01" and f.tot.season == "2027-10-01")
check("pump counters: the lifetime baseline is not touched by the new season", close(f.tot.pump_delta("total_heat"), 700.0))
f = Feed(); f.feed({"heating": None, "total_heat": None}, **STEADY)
check("pump counters missing: no baseline, no value", f.tot.pump_delta("heating") is None and f.tot.pump_delta("total_heat", season=True) is None)

# ------------------------------------------------------------------ saving
f = Feed(day="2026-09-30"); f.hold(3600, dict(c0), **STEADY); f.day = "2026-10-24"; f.hold(1800, dict(c0, total_heat=1250.0), **WATER)
saved = json.loads(json.dumps(f.tot.to_dict()))        # through JSON, like the Store does
g = kt.EnergyTotals.from_dict(saved, season_month=10)
check("save and restore: totals, days, counters and coverage come back",
      g.lifetime_sums("total") == f.tot.lifetime_sums("total") or all(close(a, b, 1e-3) for a, b in zip(g.lifetime_sums("total"), f.tot.lifetime_sums("total"))))
check("save and restore: seasons", all(close(a, b, 1e-3) for a, b in zip(g.season_sums("hot_water", "2026-10-24"), f.tot.season_sums("hot_water", "2026-10-24"))))
check("save and restore: counting continues where it was", g.since == "2026-09-30" and g.pump_base == f.tot.pump_base and g.season_base == f.tot.season_base and g.season == f.tot.season)
check("save and restore: seconds", [round(g.counted_s), round(g.skipped_s), round(g.gap_s)] == [round(f.tot.counted_s), round(f.tot.skipped_s), round(f.tot.gap_s)])
g.update(kpi.Sample(time=5000.0, **STEADY), "2026-10-24", c0); g.update(kpi.Sample(time=5030.0, **STEADY), "2026-10-24", c0)
check("restored totals keep accumulating (the first reading after a restart only starts an interval)", g.lifetime_sums("total")[1] > f.tot.lifetime_sums("total")[1])

for label, broken in {"nothing saved": None, "wrong type": "junk", "another format": {"format": 99}, "missing keys": {"format": 1, "since": None},
                      "bad number": dict(saved, lifetime={"heating": ["x", 1], "hot_water": [0, 0], "other": [0, 0]}),
                      "bad day": dict(saved, days={"yesterday": saved["days"]["2026-10-24"]})}.items():
    h = kt.EnergyTotals.from_dict(broken)
    check(f"restore from damaged data ({label}): a fresh instance", h.since is None and h.lifetime_sums("total") == (0.0, 0.0) and h.days == {})

f = Feed(totals=kt.EnergyTotals(settings=kt.TotalsSettings(keep_days=5)), day="2026-10-01"); f.hold(60, **STEADY)
for d in ("2026-10-02", "2026-10-03", "2026-10-08", "2026-10-09"):
    f.day = d; f.hold(60, **STEADY)
check("old days are dropped (history kept for seasons only), lifetime keeps them", "2026-10-01" not in f.tot.days and "2026-10-09" in f.tot.days and f.tot.lifetime_sums("total")[1] > 0.04, sorted(f.tot.days))

# ------------------------------------------------------------------ in the coordinator and the sensors
def point(pid, value, divisor=1, size="s16"):
    return {"metadata": {"variableId": pid, "variableType": "integer", "variableSize": size, "divisor": divisor},
            "value": {"isOk": True, "integerValue": None if value is None else round(value * divisor)}}

class Api:
    def __init__(self, counters=True):
        self.v = dict(STEADY, defrost=0)
        self.c = {"starts": 774, "heating": 40109.7, "hot_water": 6249.6, "total_heat": 46175.1, "total_el": 9534.0}
        self.with_counters = counters
    async def get_points(self):
        v = self.v
        t = {2509: point(2509, 1038), 1758: point(1758, v["priority"]), 2002: point(2002, v["valve_hot_water"]), 2556: point(2556, v["compressor_state"]),
             1973: point(1973, v["compressor_on"]), 1799: point(1799, v["frequency_hz"]), 1801: point(1801, v["power_w"]),
             1932: point(1932, v["power_w"]), 58: point(58, v["flow_lpm"], 10), 15: point(15, v["supply_c"], 10),
             10: point(10, v["return_c"], 10), 3126: point(3126, v["defrost"])}
        if self.with_counters:
            c = self.c
            t.update({2561: point(2561, c["starts"], 1, "u32"), 27378: point(27378, c["heating"], 10, "u32"), 27379: point(27379, c["hot_water"], 10, "u32"),
                      28392: point(28392, c["total_heat"], 10, "u32"), 28393: point(28393, c["total_el"], 10, "u32")})
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

day = ["2026-10-24"]
def mk(api, options=None, keep_files=False):
    if not keep_files: harness.Store.files.clear()
    c = pkg.NibeCoordinator("HASS", types.SimpleNamespace(options=options or {}), api, {"serial": "S", "name": "N", "manufacturer": "NIBE", "firmware": ""})
    c._today = lambda: day[0]
    return c
def poll(c, seconds=30):
    clock[0] += seconds
    c.data = asyncio.run(c._async_update_data())

sc = sys.modules["homeassistant.components.sensor"]; sc.SensorEntity = type("SensorEntity", (), {})
sensor = importlib.import_module("nibe_local_api.sensor")

api = Api(); c = mk(api)
poll(c)
check("coordinator: totals are created with the tracker", c.totals is not None and c.kpi is not None and c.totals.since == "2026-10-24")
check("coordinator: the pump counters are read (scaled)", close(c.totals.pump_now["total_heat"], 46175.1) and close(c.totals.pump_now["heating"], 40109.7) and c.totals.pump_now.get("starts") is None)
for i in range(120):
    if i == 40: api.c["starts"] += 2
    poll(c)
api.c.update(total_heat=46183.4, total_el=9534.5, heating=40118.0)
poll(c)
heat, el = c.totals.lifetime_sums("heating")
check("coordinator: one hour of heating is summed (121 intervals of 30 s, the pump counters are read too)", close(heat, Q * 3630 / 3600, 1e-3) and close(el, P * 3630 / 3600, 1e-3), (heat, el))
check("coordinator: starts of the day", c.totals.today("2026-10-24")["starts"] == 2)

ent = {(k, m): sensor.NibeEnergyTotalSensor(c, k, m) for k in ("electricity", "heat") for m in ("heating", "hot_water")}
check("energy sensors: names and unique ids",
      sorted(e._attr_name for e in ent.values()) == ["Compressor electricity, heating (calculated)", "Compressor electricity, hot water (calculated)",
                                                      "Heat produced, heating (calculated)", "Heat produced, hot water (calculated)"]
      and sorted(e._attr_unique_id for e in ent.values()) == ["S_calc_electricity_heating", "S_calc_electricity_hot_water", "S_calc_heat_heating", "S_calc_heat_hot_water"],
      [e._attr_unique_id for e in ent.values()])
check("energy sensors: kWh, energy, total increasing, no point context",
      all(e._attr_native_unit_of_measurement == "kWh" and e._attr_device_class is sensor.SensorDeviceClass.ENERGY
          and e._attr_state_class is sensor.SensorStateClass.TOTAL_INCREASING and e.coordinator_context is None for e in ent.values()))
check("energy sensors: values", close(ent[("heat", "heating")].native_value, Q * 3630 / 3600, 1e-3) and close(ent[("electricity", "heating")].native_value, P * 3630 / 3600, 1e-3)
      and ent[("heat", "hot_water")].native_value == 0 and ent[("electricity", "hot_water")].native_value == 0)
a = ent[("heat", "heating")].extra_state_attributes
check("energy sensors: heat sensors compare with the pump's own counter",
      a["counting_since"] == "2026-10-24" and a["coverage"] == 1.0 and close(a["pump_counter_kwh"], 8.3) and close(a["calculated_vs_pump"], round(8.4 / 8.3, 3), 0.01), a)
a = ent[("electricity", "heating")].extra_state_attributes
check("energy sensors: electricity sensors have no pump counter to compare with", "pump_counter_kwh" not in a and a["counted_hours"] >= 1.0, a)
check("energy sensors: their changing attributes are kept out of the database", set(a) | {"pump_counter_kwh", "calculated_vs_pump"} <= set(sensor.NibeEnergyTotalSensor._unrecorded_attributes))

cop = {(m, s): sensor.NibeCopPeriodSensor(c, m, s) for s in ("season", "lifetime") for m in ("heating", "hot_water", "total")}
check("COP sensors: names and unique ids",
      sorted(e._attr_name for e in cop.values()) == ["COP heating (lifetime)", "COP heating (season)", "COP hot water (lifetime)", "COP hot water (season)", "COP total (lifetime)", "COP total (season)"]
      and sorted(e._attr_unique_id for e in cop.values()) == ["S_cop_heating_lifetime", "S_cop_heating_season", "S_cop_hot_water_lifetime", "S_cop_hot_water_season", "S_cop_total_lifetime", "S_cop_total_season"],
      sorted(e._attr_name for e in cop.values()))
check("COP sensors: hot water says why it has no value", cop[("hot_water", "season")].extra_state_attributes["status"] == "collecting data: 0.00 of 0.25 kWh of electricity")
check("COP sensors: heating and total show the COP, hot water has no energy yet",
      close(cop[("heating", "season")].native_value, 4.15, 1e-3) and close(cop[("heating", "lifetime")].native_value, 4.15, 1e-3)
      and close(cop[("total", "season")].native_value, 4.15, 1e-3) and cop[("hot_water", "season")].native_value is None and cop[("hot_water", "lifetime")].native_value is None)
a = cop[("heating", "season")].extra_state_attributes
check("COP sensors: status says ok", a["status"] == "ok")
check("COP sensors: season attributes", a["season_start"] == "2026-10-01" and a["since"] == "2026-10-24" and a["previous_season_cop"] is None and close(a["heat_kwh"] / a["electricity_kwh"], 4.15, 0.01), a)
a = cop[("heating", "lifetime")].extra_state_attributes
check("COP sensors: lifetime attributes", a["since"] == "2026-10-24" and "season_start" not in a and a["electricity_kwh"] > 2.0, a)

pump = {s: sensor.NibeCopPumpSensor(c, s) for s in ("season", "lifetime")}
check("pump-counter COP: lifetime is the pump's Tot. production over Tot. consumption", close(pump["lifetime"].native_value, 46183.4 / 9534.5, 1e-3) and pump["lifetime"]._attr_unique_id == "S_cop_pump_lifetime"
      and pump["lifetime"]._attr_name == "COP pump counters (lifetime)", pump["lifetime"].native_value)
check("pump-counter COP: season uses the change since the first reading, and waits for 1 kWh",
      pump["season"].native_value is None and close(pump["season"].extra_state_attributes["heat_kwh"], 8.3, 0.01)
      and pump["season"].extra_state_attributes["status"] == "collecting data: 0.50 of 1 kWh of electricity", pump["season"].extra_state_attributes)
api.c.update(total_heat=46190.1, total_el=9537.1)
poll(c)
check("pump-counter COP: lifetime status ok", pump["lifetime"].extra_state_attributes["status"] == "ok")
check("pump-counter COP: season value once there is enough electricity", close(pump["season"].native_value, (46190.1 - 46175.1) / (9537.1 - 9534.0), 1e-3), pump["season"].native_value)
check("pump-counter COP: season attributes", pump["season"].extra_state_attributes["season_start"] == "2026-10-01" and pump["season"].extra_state_attributes["since"] == "2026-10-24")

starts, runtime = sensor.NibeStartsSensor(c), sensor.NibeRunTimeSensor(c)
check("starts sensor: two starts today", starts.native_value == 2 and starts._attr_unique_id == "S_compressor_starts_today" and starts._attr_state_class is sensor.SensorStateClass.TOTAL_INCREASING
      and starts.extra_state_attributes == {"yesterday": None}, starts.extra_state_attributes)
check("run time per start: the hour's running time over two starts", close(runtime.native_value, 31.0, 0.7) and runtime._attr_native_unit_of_measurement == "min", runtime.native_value)
check("run time per start: attributes", runtime.extra_state_attributes["starts"] == 2 and 60 < runtime.extra_state_attributes["run_minutes"] < 63 and runtime.extra_state_attributes["yesterday_minutes"] is None, runtime.extra_state_attributes)
day[0] = "2026-10-25"; poll(c)
check("next day: starts and run time restart, yesterday's values are shown",
      starts.native_value == 0 and starts.extra_state_attributes["yesterday"] == 2 and runtime.native_value is None and 30 < runtime.extra_state_attributes["yesterday_minutes"] < 33,
      (starts.native_value, starts.extra_state_attributes, runtime.native_value, runtime.extra_state_attributes))
check("next day: lifetime keeps adding up", cop[("heating", "lifetime")].extra_state_attributes["electricity_kwh"] > 2.0)
day[0] = "2026-10-24"

# saving and restoring through the Store
store = c._store
check("store: a save is requested every five minutes, not on every update", 10 <= len(store.delayed) <= 14 and all(d == 30 for _, d in store.delayed), len(store.delayed))
store.run_delayed()
saved_key = "nibe_local_api.S.kpi"
check("store: file written under the entry's serial number", saved_key in harness.Store.files and harness.Store.files[saved_key]["format"] == 1)
before = c.totals.lifetime_sums("heating")
c2 = mk(Api(), keep_files=True); poll(c2); poll(c2)
check("restart: the saved totals are loaded and counting continues", c2.totals.since == "2026-10-24" and c2.totals.lifetime_sums("heating")[1] > before[1] - 0.001, (c2.totals.lifetime_sums("heating"), before))
check("restart: the baseline of the pump counters is from the first run", close(c2.totals.pump_base["total_heat"], 46175.1))
c.totals.update(kpi.Sample(time=clock[0] + 30, **STEADY), "2026-10-24", None)
asyncio.run(c.async_save_totals())
check("save on unload or stop: writes the latest totals at once", harness.Store.files[saved_key]["lifetime"]["heating"][1] > round(before[1], 4), harness.Store.files[saved_key]["lifetime"]["heating"])

harness.Store.files[saved_key] = "junk"
cap.recs.clear(); c3 = mk(Api(), keep_files=True); poll(c3)
check("restart with a damaged file: fresh totals, no error", c3.totals.since == "2026-10-24" and c3.totals.lifetime_sums("total")[1] == 0.0 and not c3._kpi_failed)

class BrokenStore(harness.Store):
    async def async_load(self): raise OSError("disk")
real_store = pkg.Store; pkg.Store = BrokenStore
cap.recs.clear(); c4 = mk(Api()); poll(c4)
check("store cannot be read: warning, counting starts again", c4.totals is not None and not c4._kpi_failed and any(r.levelno == logging.WARNING for r in cap.recs))
class BrokenSave(harness.Store):
    async def async_save(self, data): raise OSError("disk full")
pkg.Store = BrokenSave; cap.recs.clear(); c5 = mk(Api()); poll(c5); asyncio.run(c5.async_save_totals())
check("store cannot be written: warning only", not c5._kpi_failed and any(r.levelno == logging.WARNING for r in cap.recs))
pkg.Store = real_store

# pump without the counters, without the points, and options
c6 = mk(Api(counters=False)); poll(c6)
check("no pump counters: totals still work", c6.totals is not None and close(c6.totals.lifetime_sums("total")[1], 0.0) and c6.totals.pump_now == {})
poll(c6)
check("no pump counters: the pump-counter sensors and starts are not created", "KPI_COUNTERS[\"total_heat\"] in coordinator.data" in open(SRC + "/sensor.py").read()
      and "KPI_COUNTERS[\"starts\"] in coordinator.data" in open(SRC + "/sensor.py").read())
check("coordinator: season month from the options, bad values fall back to October",
      [pkg._season_month(o) for o in ({}, {"season_start_month": 9}, {"season_start_month": "3"}, {"season_start_month": 13}, {"season_start_month": 0}, {"season_start_month": "x"}, {"season_start_month": None})]
      == [10, 9, 3, 10, 10, 10, 10])
c7 = mk(Api(), {"season_start_month": 9}); poll(c7)
check("coordinator: the totals use the chosen season month", c7.totals.season_month == 9 and c7.totals.season == "2026-09-01")
c8 = mk(Api(), {"season_start_month": 10}); poll(c8); poll(c8); c8._store.run_delayed()
c9 = mk(Api(), {"season_start_month": 9}, keep_files=True); poll(c9)
check("changing the season month: the saved days stay, the pump baseline restarts", c9.totals.since == "2026-10-24" and c9.totals.season == "2026-09-01" and c9.totals.season_from == "2026-10-24")

# the local day
c10 = mk(Api()); c10._today = c10._local_day
check("local day: an ISO date (no time zone configured in the stand-in: system zone)", len(c10._today()) == 10 and c10._today()[4] == "-")
c10.hass = types.SimpleNamespace(config=types.SimpleNamespace(time_zone="Pacific/Kiritimati"))
d_k = date.fromisoformat(c10._today()); c10.hass.config.time_zone = "Etc/GMT+12"
check("local day: follows Home Assistant's time zone (UTC+14 is a day or two ahead of UTC-12)", (d_k - date.fromisoformat(c10._today())).days in (1, 2))

# unload and setup wiring
src = open(SRC + "/__init__.py").read()
check("setup: the stop event saves the totals, unload saves them too",
      "EVENT_HOMEASSISTANT_STOP, coordinator.async_save_totals" in src and "await save()" in src.split("async def async_unload_entry")[1])
tail = src.split("async def async_unload_entry")[1]
check("unload: totals are saved before the platforms are unloaded", tail.index("await save()") < tail.index("async_unload_platforms"))

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
