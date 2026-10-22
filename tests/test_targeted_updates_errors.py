import sys, asyncio, importlib.util, importlib, logging, types, json, os, copy, ast, string, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import SRC, REST_413, REST_414, FIXTURES, CARD_BUILD, PREV_082, PREV_083, version_at_least
import harness
harness.install()

spec = importlib.util.spec_from_file_location("nibe_local_api", SRC + "/__init__.py", submodule_search_locations=[SRC])
pkg = importlib.util.module_from_spec(spec); sys.modules["nibe_local_api"] = pkg; spec.loader.exec_module(pkg)

from nibe_local_api import api as napi, catalog, const, entity
from harness import HomeAssistantError

results = []
def check(name, cond, detail=""):
    results.append(bool(cond)); print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))

REST = REST_413
DATA = catalog.load_data(SRC + "/data.json")
points = {int(k): v for k, v in json.load(open(REST, encoding="utf-8")).items()}
infos = catalog.build_infos(points, DATA)

def mk_coord(api=None, data=None):
    c = pkg.NibeCoordinator("HASS", types.SimpleNamespace(options={}), api, {"serial": "S", "name": "N", "manufacturer": "NIBE", "firmware": ""})
    c.data = copy.deepcopy(data if data is not None else points); c.infos = infos; c.last_update_success = True
    c.config_entry = types.SimpleNamespace(async_start_reauth=lambda hass: None)
    return c

# ------------------------------------------------------------------ A: targeted updates on the coordinator
c = mk_coord()
hits = []
cb = lambda name: (lambda: hits.append(name))
rel_a = c.async_add_listener(cb("a:4"), {4})
rel_b = c.async_add_listener(cb("b:4,8"), {4, 8})
rel_g = c.async_add_listener(cb("global"), None)
rel_f = c.async_add_listener(cb("frozen:8"), frozenset({8}))
c.async_update_point_listeners([4]); check("point update reaches only listeners that show that point", sorted(hits) == ["a:4", "b:4,8"], hits)
hits.clear(); c.async_update_point_listeners([8, 4]); check("two points -> each interested listener once", sorted(hits) == ["a:4", "b:4,8", "frozen:8"], hits)
hits.clear(); c.async_update_point_listeners([999]); check("point nobody shows -> nobody called", hits == [])
hits.clear(); c.async_update_point_listeners([]); check("no points -> nobody called", hits == [])
hits.clear(); c.async_update_listeners(); check("a full update still reaches every listener, with or without context", sorted(hits) == ["a:4", "b:4,8", "frozen:8", "global"], hits)
rel_a()
hits.clear(); c.async_update_point_listeners([4]); check("released listener is no longer called", hits == ["b:4,8"], hits)
rel_b(); rel_f(); rel_g()
check("registry is emptied again when everything is released", c._point_callbacks == {} and c._listeners == {})
rel_a()  # releasing twice must not raise
check("releasing twice is harmless", True)
c2 = mk_coord(); calls = []
c2.async_add_listener(lambda: calls.append(1), "not-a-set")
c2.async_update_point_listeners([4]); check("a context that is not a set of point ids is treated as no context", calls == [] and c2._point_callbacks == {})

# ------------------------------------------------------------------ A: which points each entity declares
sc = sys.modules["homeassistant.components.sensor"]; sc.SensorEntity = type("SensorEntity", (), {})
bs = types.ModuleType("homeassistant.components.binary_sensor"); bs.BinarySensorEntity = type("BinarySensorEntity", (), {})
bs.BinarySensorDeviceClass = types.SimpleNamespace(PROBLEM="problem", RUNNING="running"); sys.modules["homeassistant.components.binary_sensor"] = bs
bt = types.ModuleType("homeassistant.components.button"); bt.ButtonEntity = type("ButtonEntity", (), {}); sys.modules["homeassistant.components.button"] = bt
sensor = importlib.import_module("nibe_local_api.sensor")
binary_sensor = importlib.import_module("nibe_local_api.binary_sensor")
button = importlib.import_module("nibe_local_api.button")

c = mk_coord()
ctx = lambda e: e.coordinator_context
check("point entity: its own point", ctx(entity.NibePointEntity(c, 11)) == {11})
check("outdoor sensor class: its own point", ctx(sensor.NibeSensor(c, 11)) == {11})
check("heater steps sensor also follows the maximum-heater setting (its attributes show it)", ctx(sensor.NibeHeaterStepsSensor(c, const.HEATER_STEPS_POINT)) == {const.HEATER_STEPS_POINT, const.HEATER_MAX_POINT})
check("heater power sensor follows the step count", ctx(sensor.NibeHeaterPowerSensor(c)) == {const.HEATER_STEPS_POINT})
check("heater load sensor follows steps and maximum", ctx(sensor.NibeHeaterLoadSensor(c)) == {const.HEATER_STEPS_POINT, const.HEATER_MAX_POINT})
check("pump running sensor follows its speed point", ctx(binary_sensor.NibePumpRunningSensor(c, "gp1", 1975, "x")) == {1975})
check("software version sensor follows point 2509", ctx(sensor.NibeVersionSensor(c, 2509)) == {2509})
check("reset-alarms button follows the alarm number", ctx(button.NibeResetAlarmsButton(c)) == {const.ALARM_NUMBER_POINT})
check("alarm sensors (from notifications) have no point context", ctx(sensor.NibeAlarmSensor(c)) is None and ctx(binary_sensor.NibeAlarmBinarySensor(c)) is None)

# ------------------------------------------------------------------ A: end to end with real entities and the real fast poll
class FApi:
    def __init__(self, raw): self.raw, self.single = raw, []
    async def get_point(self, pid):
        self.single.append(pid)
        p = copy.deepcopy(points[pid]); p["value"]["integerValue"] = self.raw.get(pid, p["value"]["integerValue"]); return p
    async def patch_points(self, v): return {}
    async def reset_notifications(self): raise napi.NibeApiError("x")

def register_all(c):
    """Register a recorder for the entities of interest, using the context they declare."""
    ents = {
        "outdoor 4": entity.NibePointEntity(c, 4), "supply 8": entity.NibePointEntity(c, 8),
        "steps 1760": sensor.NibeHeaterStepsSensor(c, 1760), "power": sensor.NibeHeaterPowerSensor(c),
        "load": sensor.NibeHeaterLoadSensor(c), "max heater 3823": entity.NibePointEntity(c, 3823),
        "version 2509": sensor.NibeVersionSensor(c, 2509), "alarms": sensor.NibeAlarmSensor(c),
        "reset button": button.NibeResetAlarmsButton(c),
    }
    hit = []
    for name, e in ents.items():
        c.async_add_listener((lambda n: (lambda: hit.append(n)))(name), e.coordinator_context)
    return ents, hit

c = mk_coord(FApi({1760: 4})); c.fast_points = [1760]
ents, hit = register_all(c)
asyncio.run(c.async_fast_poll())
check("fast poll of the heater steps refreshes the three heater entities and nothing else",
      sorted(hit) == ["load", "power", "steps 1760"], sorted(hit))
check("fast poll stored the new value", c.data[1760]["value"]["integerValue"] == 4)
c = mk_coord(FApi({3823: 40})); c.fast_points = [3823]
ents, hit = register_all(c); asyncio.run(c.async_fast_poll())
check("polling the heater maximum refreshes its own entity, the load sensor and the steps attributes",
      sorted(hit) == ["load", "max heater 3823", "steps 1760"], sorted(hit))
c = mk_coord(FApi({})); c.fast_points = [4, 8]
ents, hit = register_all(c); asyncio.run(c.async_fast_poll())
check("polling two temperatures refreshes just those two entities (of 9 registered)", sorted(hit) == ["outdoor 4", "supply 8"], sorted(hit))
c = mk_coord(FApi({})); ents, hit = register_all(c); c.async_update_listeners()
check("a normal full update refreshes all nine", len(hit) == 9, sorted(hit))

# write read-back refreshes just the written point
c = mk_coord(FApi({8: 123})); ents, hit = register_all(c)
e = entity.NibePointEntity(c, 8)
asyncio.run(e._write_raw(123))
check("write read-back refreshes only the entities of the written point", hit == ["supply 8"], hit)
check("write read-back stores the pump's value", c.data[8]["value"]["integerValue"] == 123)

# ------------------------------------------------------------------ B: translated errors
EN = json.load(open(SRC + "/translations/en.json", encoding="utf-8"))["exceptions"]
used = {}
for f in glob.glob(SRC + "/*.py"):
    for node in ast.walk(ast.parse(open(f, encoding="utf-8").read())):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "translated_error" and node.args and isinstance(node.args[0], ast.Constant):
            used.setdefault(node.args[0].value, []).append({k.arg for k in node.keywords})
check("every error key used in the code exists in translations", all(k in EN for k in used), [k for k in used if k not in EN])
fields = lambda msg: {name for _, name, _, _ in string.Formatter().parse(msg) if name}
check("every call passes exactly the placeholders its message uses",
      all(kw == fields(EN[k]["message"]) for k, calls in used.items() if k in EN for kw in calls),
      [(k, kw, fields(EN[k]["message"])) for k, calls in used.items() if k in EN for kw in calls if kw != fields(EN[k]["message"])])
check("no translation entry is unused", set(EN) == set(used), set(EN) ^ set(used))
check("seven error messages are defined", len(EN) == 7)
check("no plain-text HomeAssistantError left in the code",
      not [f for f in glob.glob(SRC + "/*.py") if "raise HomeAssistantError(" in open(f, encoding="utf-8").read()])

class EApi:
    def __init__(self, exc=None, result=None): self.exc, self.result = exc, result or {}
    async def patch_points(self, v):
        if self.exc: raise self.exc
        return self.result
    async def get_point(self, pid): return copy.deepcopy(points[pid])
    async def reset_notifications(self): raise napi.NibeApiError("x")
c = mk_coord(EApi(napi.NibeApiError("net down"))); e = entity.NibePointEntity(c, 8)
try: asyncio.run(e._write_raw(1)); err = None
except HomeAssistantError as x: err = x
check("write failure: translation key, placeholders and rendered message",
      err and err.translation_key == "write_failed" and err.translation_domain == "nibe_local_api"
      and err.translation_placeholders == {"point_id": "8", "error": "net down"} and str(err) == "Writing point 8 failed: net down", str(err))
c = mk_coord(EApi(result={"8": "error: read only value"})); e = entity.NibePointEntity(c, 8)
try: asyncio.run(e._write_raw(1)); err = None
except HomeAssistantError as x: err = x
check("pump rejection: rendered message", err and str(err) == "The heat pump rejected the write to point 8: error: read only value", str(err))

aux = importlib.import_module("nibe_local_api.aux")
class AuxCoord:
    def __init__(self, api, reg=aux.FUNCTION_REGISTER):
        self.api, self.aux_lock, self.refreshes = api, asyncio.Lock(), 0
        self.data = {aux.FUNCTION_POINT: {"metadata": {"modbusRegisterID": reg}}, aux.STATE_POINT: {"metadata": {"modbusRegisterID": aux.STATE_REGISTER}}}
    async def async_request_refresh(self): self.refreshes += 1
try: asyncio.run(aux.async_set_aux(AuxCoord(EApi(), reg=5), "block_heating", True)); err = None
except HomeAssistantError as x: err = x
check("aux register mismatch: rendered message names found and expected registers",
      err and err.translation_key == "aux_unavailable" and f"reports Modbus register 5, expected {aux.FUNCTION_REGISTER}" in str(err), str(err))
try: asyncio.run(aux.async_set_aux(AuxCoord(EApi(napi.NibeApiError("boom"))), "block_heating", True)); err = None
except HomeAssistantError as x: err = x
check("aux write failure: rendered message", err and str(err) == "AUX write failed: boom", str(err))

class MApi:
    async def set_mode(self, *a): raise napi.NibeApiError("not applied")
co = pkg.NibeCoordinator("HASS", types.SimpleNamespace(options={}), MApi(), {"serial": "S", "name": "N", "manufacturer": "NIBE", "firmware": ""})
try: asyncio.run(co.async_set_mode("aidmode", "aidMode", "on")); err = None
except HomeAssistantError as x: err = x
check("mode failure: rendered message", err and str(err) == "Setting aidmode to on failed: not applied", str(err))

# service handler without a loaded entry
class Services:
    def __init__(self): self.handlers = {}
    def has_service(self, d, s): return False
    def async_register(self, d, s, handler, schema=None): self.handlers[s] = handler
class CE:
    def async_entries(self, domain): return []
hass = types.SimpleNamespace(services=Services(), config_entries=CE())
pkg._register_services(hass)
try: asyncio.run(hass.services.handlers["set_aux"](types.SimpleNamespace(data={"function": "block_heating", "state": True}))); err = None
except HomeAssistantError as x: err = x
check("service without a loaded entry: translated 'not loaded' error", err and err.translation_key == "not_loaded" and str(err) == "NIBE Local REST API is not loaded", str(err))

c = mk_coord(EApi()); b = button.NibeResetAlarmsButton(c)
try: asyncio.run(b.async_press()); err = None
except HomeAssistantError as x: err = x
check("alarm reset failure: rendered message", err and err.translation_key == "alarm_reset_failed" and "not supported or not enabled" in str(err) and "x" in str(err), str(err))

# ------------------------------------------------------------------ D: reset-alarms button availability
def button_state(alarms, number, present=True):
    c = mk_coord(); c.alarms = alarms
    if present: c.data[const.ALARM_NUMBER_POINT]["value"]["integerValue"] = number
    else: c.data.pop(const.ALARM_NUMBER_POINT)
    return button.NibeResetAlarmsButton(c).available
check("button: no alarm anywhere -> not offered", button_state([], 0) is False)
check("button: notification list has an alarm -> offered", button_state([{"id": 1}], 0) is True)
check("button: alarm number set (list empty) -> offered", button_state([], 163) is True)
check("button: alarm point missing and list empty -> not offered", button_state([], 0, present=False) is False)

# ------------------------------------------------------------------ C: config flow catch-all
class Marker:
    def __init__(self, schema, default=None): self.schema, self.default = schema, default
    def __hash__(self): return hash(self.schema)
    def __eq__(self, o): return isinstance(o, Marker) and o.schema == self.schema
fake_vol = types.ModuleType("voluptuous")
fake_vol.Schema = lambda d: d; fake_vol.Required = lambda k, default=None: Marker(k, default); fake_vol.Optional = fake_vol.Required
fake_vol.All = lambda *a: ("All", a); fake_vol.Range = lambda **k: ("Range", k); fake_vol.UNDEFINED = object()
sys.modules["voluptuous"] = fake_vol
class FlowBase:
    def __init_subclass__(cls, domain=None, **kw): pass
    hass = "HASS"
    def async_show_form(self, step_id=None, data_schema=None, errors=None, **kw): return {"type": "form", "step": step_id, "errors": errors or {}}
    def async_create_entry(self, title=None, data=None, **kw): return {"type": "create_entry", "title": title, "data": data}
    async def async_set_unique_id(self, uid): self.uid = uid
    def _abort_if_unique_id_configured(self): pass
    def _abort_if_unique_id_mismatch(self, reason=None): pass
    def async_update_reload_and_abort(self, entry, data_updates=None): return {"type": "abort", "reason": "done", "updates": data_updates}
ce = sys.modules["homeassistant.config_entries"]; ce.ConfigFlow = FlowBase; ce.OptionsFlow = FlowBase
sys.modules["homeassistant"].config_entries = ce
sel = sys.modules["homeassistant.helpers.selector"]
for n in ("SelectOptionDict", "SelectSelectorConfig", "SelectSelector", "SelectSelectorMode"): setattr(sel, n, lambda *a, **k: None)
cf = importlib.import_module("nibe_local_api.config_flow")
ENTRY = types.SimpleNamespace(title="NIBE", data={"host": "h", "port": 8443, "https": True, "username": "u", "password": "p"})
def flow():
    f = cf.NibeConfigFlow(); f._get_reauth_entry = lambda: ENTRY; f._get_reconfigure_entry = lambda: ENTRY; return f
FORM = {"host": "h", "port": 8443, "https": True, "username": "u", "password": "p"}
INFO = {"serial": "S1", "name": "NIBE S1155"}
def run_step(step, probe_result, data=FORM):
    async def probe(hass, d):
        if isinstance(probe_result, Exception): raise probe_result
        return probe_result
    cf._probe = probe
    return asyncio.run(getattr(flow(), step)(data))

logging.getLogger("nibe_local_api.config_flow").setLevel(logging.CRITICAL)   # keep the expected traceback out of the test output
for step in ("async_step_user", "async_step_reauth_confirm", "async_step_reconfigure"):
    check(f"{step}: unexpected exception -> form with 'unknown', no crash", run_step(step, RuntimeError("bug"))["errors"] == {"base": "unknown"})
    check(f"{step}: wrong login -> invalid_auth", run_step(step, napi.NibeAuthError("401"))["errors"] == {"base": "invalid_auth"})
    check(f"{step}: unreachable -> cannot_connect", run_step(step, napi.NibeApiError("down"))["errors"] == {"base": "cannot_connect"})
res = run_step("async_step_user", INFO)
check("user step: success still creates the entry", res["type"] == "create_entry" and res["title"] == "NIBE S1155" and res["data"] == FORM)
check("reconfigure step: success still updates the entry", run_step("async_step_reconfigure", INFO)["type"] == "abort")
cf.NibeConfigFlow._abort_if_unique_id_configured = lambda self: (_ for _ in ()).throw(KeyError("abort"))
try:
    run_step("async_step_user", INFO); swallowed = True
except KeyError:
    swallowed = False
check("abort exceptions propagate (only the probe is guarded)", swallowed is False)
check("translations: 'unknown' error exists", "unknown" in json.load(open(SRC + "/translations/en.json"))["config"]["error"])

# ------------------------------------------------------------------ E: manifest
man = json.load(open(SRC + "/manifest.json"))
check("manifest: device integration type, version 0.8.5 or later", man["integration_type"] == "device" and version_at_least(man["version"], "0.8.5"), man)
check("manifest: still a valid custom integration manifest", {"domain", "name", "version", "config_flow", "iot_class", "requirements"} <= set(man) and man["domain"] == "nibe_local_api")

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
