import sys, asyncio, importlib.util, importlib, logging, types, json, os, copy, shutil, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import SRC, REST_413, REST_414, FIXTURES, CARD_BUILD, PREV_082, PREV_083, version_at_least
import harness
harness.install()

spec = importlib.util.spec_from_file_location(
    "nibe_local_api", SRC + "/__init__.py",
    submodule_search_locations=[SRC])
pkg = importlib.util.module_from_spec(spec); sys.modules["nibe_local_api"] = pkg; spec.loader.exec_module(pkg)

from nibe_local_api import api as napi, catalog, const

results = []
def check(name, cond, detail=""):
    results.append(bool(cond)); print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))

REST = REST_413
DATA = catalog.load_data(SRC + "/data.json")

# ------------------------------------------------------------------ decoding
check("decode_version: 1037 -> 4.13 and 1038 -> 4.14 (both confirmed on the pump)", napi.decode_version(1037) == "4.13" and napi.decode_version(1038) == "4.14")
check("decode_version: high byte major, low byte minor", napi.decode_version(0x0201) == "2.1" and napi.decode_version(0x050A) == "5.10" and napi.decode_version(0x04FF) == "4.255")
check("decode_version: major 0, small values, not-connected marker and junk -> None",
      all(napi.decode_version(v) is None for v in (0, 1, 255, 65535, 70000, -1, None, "1037", 1037.0, True)))
check("const: version point is 2509", const.VERSION_POINT == 2509)

def vpoint(raw, ok=True, key="value"):
    return {2509: {"metadata": {"variableId": 2509}, key: {"isOk": ok, "integerValue": raw}}}
check("firmware_version: reads point 2509", napi.firmware_version(vpoint(1038)) == "4.14")
check("firmware_version: datavalue key accepted too", napi.firmware_version(vpoint(1038, key="datavalue")) == "4.14")
check("firmware_version: value not ok, point missing, empty table -> None",
      napi.firmware_version(vpoint(1038, ok=False)) is None and napi.firmware_version({4: {}}) is None and napi.firmware_version({}) is None)
check("firmware_version: not-connected marker -> None", napi.firmware_version(vpoint(65535)) is None)

# ------------------------------------------------------------------ catalog on the real export
if os.path.exists(REST):
    points = {int(k): v for k, v in json.load(open(REST, encoding="utf-8")).items()}
    infos = catalog.build_infos(points, DATA)
    i = infos[2509]
    check("catalog: 2509 is the enabled diagnostic sensor 'Software version'",
          i.name == "Software version" and i.kind == "sensor" and i.enabled and i.category == "diagnostic" and i.live, (i.name, i.kind, i.enabled, i.category))
    check("catalog: 2509 has no unit, device class or state class (so no statistics change on upgrade)",
          not i.unit and not i.device_class and not i.state_class)
    check("catalog: description explains the missing patch level", "patch level" in i.description and "3.1.15" in i.description)
    check("real: yesterday's raw 1037 decodes to 4.13", napi.firmware_version(points) == "4.13")

    prev_dir = PREV_083
    if prev_dir and os.path.isdir(prev_dir):
        tmp = tempfile.mkdtemp()
        shutil.copytree(prev_dir, tmp + "/nibe_local_api")
        sys.modules["prev083"] = types.ModuleType("prev083"); sys.modules["prev083"].__path__ = [tmp + "/nibe_local_api"]
        prev = importlib.import_module("prev083.catalog")
        old = prev.build_infos(points, prev.load_data(tmp + "/nibe_local_api/data.json"))
        changed = {}
        for p in points:
            for f in ("name", "kind", "unit", "device_class", "state_class", "category", "enabled", "live", "options", "reason", "min_raw", "max_raw", "range_note"):
                if getattr(old[p], f) != getattr(infos[p], f): changed.setdefault(p, []).append(f)
        PRESSURE0 = {2885, 2913, 2941, 2969, 2997, 3025, 3053, 3081, 3108, 3109, 3122, 3123}   # 0.8.6: 0 bar = no sensor
        check("diff vs 0.8.3: only point 2509 and the zero-pressure points changed", set(changed) == {2509} | PRESSURE0, changed)
        check("diff vs 0.8.3: the zero-pressure points only changed live/reason",
              all(set(changed[p]) == {"live", "reason"} for p in PRESSURE0), {p: changed.get(p) for p in PRESSURE0})
        check("diff vs 0.8.3: 2509 changed name, enabled and reason only (it was already a diagnostic)",
              set(changed.get(2509, [])) == {"name", "enabled", "reason"}, changed.get(2509))
    else:
        print("SKIP comparison with release 0.8.3 (set NIBE_TEST_PREV_083 to its unpacked nibe_local_api folder)")
else:
    print("SKIP real-data checks (export not found)")

# ------------------------------------------------------------------ coordinator keeps the device version current
class Registry:
    def __init__(self, device=True): self.device, self.updates, self.lookups = device, [], []
    def async_get_device(self, identifiers=None, connections=None):
        self.lookups.append(identifiers); return types.SimpleNamespace(id="dev1") if self.device else None
    def async_update_device(self, device_id, **kw): self.updates.append((device_id, kw))
reg = Registry()
pkg.dr = types.SimpleNamespace(async_get=lambda hass: reg)

class VApi:
    def __init__(self, raw): self.raw = raw
    async def get_points(self): return vpoint(self.raw) if self.raw is not None else {4: {"metadata": {}}}
    async def get_device(self): return {}
    async def get_notifications(self): return []
def vcoord(api):
    c = pkg.NibeCoordinator("HASS", types.SimpleNamespace(options={}), api, {"serial": "S", "name": "N", "manufacturer": "NIBE", "firmware": "nibe-n"})
    return c

class Cap(logging.Handler):
    def __init__(self): super().__init__(); self.msgs = []
    def emit(self, r): self.msgs.append((r.levelno, r.getMessage()))
cap = Cap(); lg = logging.getLogger("nibe_local_api"); lg.addHandler(cap); lg.setLevel(logging.DEBUG)

c = vcoord(VApi(1038))
check("coordinator: 'nibe-n' is not shown as a version before the first poll", c.device_info["sw_version"] is None)
asyncio.run(c._async_update_data())
check("coordinator: first poll sets the device version for entities created afterwards", c.device_info["sw_version"] == "4.14")
check("coordinator: registry entry updated once, keyed by the integration's identifier",
      reg.updates == [("dev1", {"sw_version": "4.14"})] and reg.lookups == [{("nibe_local_api", "S")}], (reg.updates, reg.lookups))
check("coordinator: first value is not logged as a change", not [m for l, m in cap.msgs if "changed" in m])
asyncio.run(c._async_update_data())
check("coordinator: unchanged version -> no further registry write", len(reg.updates) == 1)
c.api.raw = 1039; asyncio.run(c._async_update_data())
check("coordinator: firmware update while running -> registry and device info follow, one info line",
      c.device_info["sw_version"] == "4.15" and reg.updates[-1] == ("dev1", {"sw_version": "4.15"}) and len(reg.updates) == 2
      and [m for l, m in cap.msgs if "changed from 4.14 to 4.15" in m], reg.updates)
c.api.raw = None; asyncio.run(c._async_update_data())
check("coordinator: version point missing in a poll -> last known version kept", c.device_info["sw_version"] == "4.15" and len(reg.updates) == 2)
reg2 = Registry(device=False); pkg.dr = types.SimpleNamespace(async_get=lambda hass: reg2)
c = vcoord(VApi(1038)); asyncio.run(c._async_update_data())
check("coordinator: device not in the registry yet (first start) -> no error, version still set", c.device_info["sw_version"] == "4.14" and reg2.updates == [])

# ------------------------------------------------------------------ the sensor entity
sc = sys.modules["homeassistant.components.sensor"]
sc.SensorEntity = type("SensorEntity", (), {})
sensor = importlib.import_module("nibe_local_api.sensor")
if os.path.exists(REST):
    coord = types.SimpleNamespace(serial="S", device_info={}, infos=infos, data=copy.deepcopy(points))
    ent = sensor.NibeVersionSensor(coord, 2509)
    check("sensor: shows '4.13' for raw 1037", ent.native_value == "4.13" and ent.available)
    coord.data[2509]["value"]["integerValue"] = 1038
    check("sensor: follows the pump to '4.14' on the next poll", ent.native_value == "4.14")
    check("sensor: raw register stays visible as an attribute", ent.extra_state_attributes["raw_value"] == 1038)
    coord.data[2509]["value"]["isOk"] = False
    check("sensor: value not ok -> no state", ent.native_value is None)
    check("sensor: unique id unchanged from earlier versions", ent._attr_unique_id == "S_2509")
    check("sensor setup picks the version class for point 2509 only",
          "NibeVersionSensor" in open(SRC + "/sensor.py").read().split("elif pid == VERSION_POINT:")[1][:80]
          and all(c.__name__ != "NibeVersionSensor" for c in [sensor.NibeSensor, sensor.NibeHeaterStepsSensor]))

check("manifest: version 0.8.4 or later", version_at_least(json.load(open(SRC + "/manifest.json"))["version"], "0.8.4"))
print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
