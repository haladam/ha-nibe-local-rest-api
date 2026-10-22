"""0.8.6: firmware 4.14.6 sends some titles in German and 0 bar for sensors the model lacks."""
import sys, json, types, importlib, copy, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import SRC, REST_413, REST_414, FIXTURES, CARD_BUILD, PREV_082, PREV_083, version_at_least
m = types.ModuleType("aiohttp"); m.ClientSession = object; m.ClientError = Exception; sys.modules["aiohttp"] = m
pkg = types.ModuleType("nibe_local_api"); pkg.__path__ = [SRC]; sys.modules["nibe_local_api"] = pkg
from nibe_local_api import api, catalog

results = []
def check(name, cond, detail=""):
    results.append(bool(cond)); print(("PASS " if cond else "FAIL ") + name + (f"  [{str(detail)[:300]}]" if detail and not cond else ""))

DATA = catalog.load_data(SRC + "/data.json")
load = lambda f: {int(k): v for k, v in json.load(open(f, encoding="utf-8")).items()}
A = load(REST_413)            # firmware 4.13.12
B = load(REST_414)       # firmware 4.14.6
ia, ib = catalog.build_infos(A, DATA), catalog.build_infos(B, DATA)
ET = DATA["english_titles"]

# ---- data.json
check("english_titles: one entry per point of the 4.13 export", len(ET) == len(A) == 1176 and set(ET) == {str(p) for p in A})
check("english_titles: identical to the cleaned titles of the 4.13 export", all(ET[str(p)] == api.clean_title(A[p]) for p in A))
check("english_titles: no soft hyphens, no mojibake, none empty", all(t and "­" not in t and "Ã" not in t and "Â" not in t for t in ET.values()))
check("english_titles: the 56 points that arrive in German are English here",
      ET["24485"] == "Supply Line Set Point Heating 2" and ET["32342"] == "Desired room temperature for zone 2" and ET["24492"] == "Supply Line Set Point Cooling 1")
check("both exports cover the same 1176 points", set(A) == set(B) and len(B) == 1176)

# ---- 4.14.6 with German titles classifies exactly like 4.13
fields = ("name", "kind", "unit", "device_class", "state_class", "category", "enabled", "live", "options", "reason", "min_raw", "max_raw", "description", "range_note")
diff = {p: [f for f in fields if getattr(ia[p], f) != getattr(ib[p], f)] for p in A}
diff = {p: f for p, f in diff.items() if f}
check("4.14.6 vs 4.13: only point 2555 (its unit was fixed) differs", set(diff) == {2555} and set(diff[2555]) == {"unit", "device_class"}, diff)
check("4.14.6: same entities enabled by default as on 4.13 (222)", {p for p, i in ia.items() if i.enabled} == {p for p, i in ib.items() if i.enabled} and sum(i.enabled for i in ib.values()) == 222)
german = [p for p in B if B[p]["title"] != A[p]["title"] and re.search(r"Vorlauf|Gew|Zone|Heizung|K.hlung", api.clean_title(B[p]))]
check("test data: 56 points arrive with German titles", len(german) == 56, len(german))
check("the 16 supply setpoints (24484-24499) stay off by default despite the German titles", all(not ib[p].enabled for p in range(24484, 24500)), [p for p in range(24484, 24500) if ib[p].enabled])
check("... and keep the reasons they had on 4.13", all(ib[p].reason == ia[p].reason for p in range(24484, 24500)) and ib[24485].reason == "likely unused hardware" and ib[24484].reason == "advanced installer setting")
check("entity names do not turn German", all(not re.search(r"Vorlauf|Gew|Raumtemp", i.name) for i in ib.values()))
check("PointInfo.title still shows what the pump sent", ib[24485].title == "Vorlaufsollwert Heizung 2" and ia[24485].title == "Supply Line Set Point Heating 2")

# ---- a point not in english_titles falls back to the pump's own title
def clone(src, pid, title=None, **meta):
    p = copy.deepcopy(A[src]); p["metadata"] = {**p["metadata"], "variableId": pid, **meta}; p["value"]["variableId"] = pid
    if title: p["title"] = title
    return p
unk = clone(24485, 999001, "Supply Line Set Point Heating 3")
i = catalog.info_for(999001, unk, DATA)
check("unknown point id: rules still use the pump's title (English)", not i.enabled and i.reason == "likely unused hardware", (i.enabled, i.reason))
i = catalog.info_for(999001, clone(24485, 999001, "Vorlaufsollwert Heizung 3"), DATA)
check("unknown point id with a German title: no rule matches, so nothing is hidden by title (documented fallback)", i.enabled, i.reason)
i = catalog.info_for(24485, clone(24485, 24485, "Vorlaufsollwert Heizung 2"), {**DATA, "english_titles": {}})
check("without the table the German title would enable the point (this is what 0.8.5 did)", i.enabled and i.reason == "live")
i = catalog.info_for(24485, clone(24485, 24485, "Vorlaufsollwert Heizung 2"), DATA)
check("with the table the same point stays off", not i.enabled and i.reason == "likely unused hardware")
# robustness: title missing entirely
nt = clone(24485, 24485); nt.pop("title")
i = catalog.info_for(24485, nt, DATA)
check("no title from the pump: classification still works, title shows 'Unknown'", not i.enabled and i.title == "Unknown")

# ---- zero-pressure rule
def pressure(pid_src, value, unit="bar", title=None, pid=None):
    p = clone(pid_src, pid or pid_src, title, unit=unit, shortUnit=unit)
    p["value"]["integerValue"] = value; return p
i = catalog.info_for(2555, pressure(2555, 0), DATA)
check("2555 reading 0 bar: not live, not enabled, reason says no sensor", not i.live and not i.enabled and i.reason.startswith("no value"), (i.live, i.enabled, i.reason))
i = catalog.info_for(2555, pressure(2555, 55), DATA)
check("2555 reading 5.5 bar (a pump that has the sensor): live and enabled, pressure sensor in bar",
      i.live and i.enabled and i.unit == "bar" and i.device_class == "pressure" and i.state_class == "measurement", (i.live, i.enabled, i.unit, i.device_class))
i = catalog.info_for(2555, pressure(2555, -32768), DATA)
check("2555 with the 'no value' marker: still not live", not i.live and not i.enabled)
i = catalog.info_for(2555, pressure(2555, 0, unit="°C"), DATA)
check("2555 as 4.13 reported it (unit °C): rule not involved, behaves as before", i.unit == "°C")
i = catalog.info_for(999002, pressure(2555, 0, title="Brine pressure (EB100-BP5)", pid=999002), DATA)
check("brine pressure sensor (BP5) reading 0 stays live: that value could be real", i.live, (i.live, i.reason))
i = catalog.info_for(999003, pressure(2555, 0, title="Condenser pressure sensor", pid=999003), DATA)
check("generic 'pressure sensor' title reading 0 bar is treated as not fitted", not i.live)
i = catalog.info_for(999004, pressure(2555, 0, title="Low press (EB100-BP8)", pid=999004, unit="°C"), DATA)
check("pressure title without bar unit is left alone", i.live)
zero_bar = [p for p in B if api.unit_of(B[p]["metadata"]) == "bar"]
check("4.14.6: all 13 bar points (all 0) are not live; BP8/BP4 sensors of absent units hidden", len(zero_bar) == 13 and all(not ib[p].live and not ib[p].enabled for p in zero_bar), zero_bar)
check("4.14.6 and 4.13 have the same number of points that are not live",
      sum(not i.live for i in ib.values()) == sum(not i.live for i in ia.values()) , (sum(not i.live for i in ib.values()), sum(not i.live for i in ia.values())))

# ---- language select
sel = ib[3745]
check("language: select, options still only the 25 named languages although the pump now reports 0-31",
      sel.kind == "select" and sorted(sel.options) == list(range(25)) and B[3745]["metadata"]["maxValue"] == 31, (sel.kind, sorted(sel.options or [])[-3:]))

# ---- manifest
man = json.load(open(SRC + "/manifest.json"))
check("manifest: version 0.8.6 or later, device integration", version_at_least(man["version"], "0.8.6") and man["integration_type"] == "device")

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
