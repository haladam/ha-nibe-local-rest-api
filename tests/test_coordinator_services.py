import sys, os, asyncio, importlib.util, logging, types
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import SRC, REST_413, REST_414, FIXTURES, CARD_BUILD, PREV_082, PREV_083, version_at_least
import harness
harness.install()

# execute the real __init__.py inside the stub package
spec = importlib.util.spec_from_file_location(
    "nibe_local_api", SRC + "/__init__.py",
    submodule_search_locations=[SRC])
pkg = importlib.util.module_from_spec(spec); sys.modules["nibe_local_api"] = pkg; spec.loader.exec_module(pkg)

from nibe_local_api import api as napi, aux, entity, catalog
from harness import HomeAssistantError, ConfigEntryAuthFailed, UpdateFailed, ConfigEntryState

results = []
def check(name, cond, detail=""):
    results.append(cond); print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))

# ------------------------------------------------------------------ fake pump over a fake aiohttp session
class Resp:
    def __init__(self, status, body): self.status, self._b = status, body
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    def raise_for_status(self):
        if self.status >= 400: raise Exception(f"HTTP {self.status}")
    async def text(self): return self._b
class Session:
    def __init__(self, handler): self.handler, self.calls = handler, []
    def request(self, method, url, **kw):
        path = url.split("/api/v1")[1]; self.calls.append((method, path, kw.get("json")))
        status, body = self.handler(method, path, kw.get("json"))
        return Resp(status, body)

import json
def make_api(handler):
    s = Session(handler); return napi.NibeLocalApi(s, "h", 8443, True), s

# ---- set_mode verification
state = {"aidMode": "off", "smartMode": "normal"}
def pump_ok(m, p, j):
    if m == "POST": state["aidMode"] = j.get("aidmode", j.get("aidMode", state["aidMode"])); return 200, ""
    return 200, json.dumps(state)
a, s = make_api(pump_ok)
r = asyncio.run(a.set_mode("aidmode", "aidMode", "on"))
check("set_mode: lowercase accepted, verified, one POST", r["aidMode"] == "on" and sum(c[0]=="POST" for c in s.calls) == 1)

state = {"aidMode": "off"}
def pump_camel_only(m, p, j):
    if m == "POST":
        if "aidMode" in j: state["aidMode"] = j["aidMode"]
        return 200, ""                       # lowercase: 200 but silently ignored
    return 200, json.dumps(state)
a, s = make_api(pump_camel_only)
r = asyncio.run(a.set_mode("aidmode", "aidMode", "on"))
posts = [c[2] for c in s.calls if c[0] == "POST"]
check("set_mode: ignored lowercase -> falls back to camelCase and verifies", r["aidMode"] == "on" and posts == [{"aidmode":"on"},{"aidMode":"on"}], posts)

state = {"aidMode": "off"}
a, s = make_api(lambda m,p,j: (200, "") if m=="POST" else (200, json.dumps(state)))
try: asyncio.run(a.set_mode("aidmode", "aidMode", "on")); ok = False
except napi.NibeApiError: ok = True
check("set_mode: pump ignores both -> raises instead of pretending success", ok)

def pump_400_then_ok(m, p, j):
    if m == "POST":
        if "aidmode" in j: return 400, ""
        state["aidMode"] = j["aidMode"]; return 200, ""
    return 200, json.dumps(state)
state = {"aidMode": "off"}; a, s = make_api(pump_400_then_ok)
check("set_mode: HTTP 400 on lowercase -> camelCase used", asyncio.run(a.set_mode("aidmode","aidMode","on"))["aidMode"] == "on")

a, s = make_api(lambda m,p,j: (401, ""))
try: asyncio.run(a.set_mode("aidmode","aidMode","on")); ok = False
except napi.NibeAuthError: ok = True
check("set_mode: 401 raised as auth error and not retried", ok and len(s.calls) == 1, s.calls)

def pump_post_ok_get_fails(m,p,j): return (200,"") if m=="POST" else (500,"")
a, s = make_api(pump_post_ok_get_fails)
check("set_mode: written but unreadable -> returns None, no error", asyncio.run(a.set_mode("smartmode","smartMode","away")) is None)

a, s = make_api(lambda m,p,j: (200, json.dumps({"title":"x","metadata":{},"value":{"integerValue":5}})))
check("get_point reads one point from /points/<id>", asyncio.run(a.get_point(4))["value"]["integerValue"] == 5 and s.calls[0][1] == "/devices/0/points/4")

# ------------------------------------------------------------------ aux lock
class AuxApi:
    def __init__(self): self.log, self.function = [], None
    async def patch_points(self, values):
        await asyncio.sleep(0.01)
        for pid, raw in values.items():
            if pid == aux.FUNCTION_POINT: self.function = raw
            else: self.log.append((self.function, raw))
        return {}
class AuxCoord:
    def __init__(self, api=None):
        self.api = api or AuxApi(); self.aux_lock = asyncio.Lock(); self.refreshes = 0
        self.data = {aux.FUNCTION_POINT: {"metadata": {"modbusRegisterID": aux.FUNCTION_REGISTER}},
                     aux.STATE_POINT: {"metadata": {"modbusRegisterID": aux.STATE_REGISTER}}}
    async def async_request_refresh(self): self.refreshes += 1
async def two_calls():
    c = AuxCoord()
    await asyncio.gather(aux.async_set_aux(c, "block_heating", True), aux.async_set_aux(c, "hot_water_large", False))
    return c.api.log
log = asyncio.run(two_calls())
check("aux: concurrent calls no longer interleave", sorted(log) == sorted([(6, 1), (1, 0)]), log)

class FailApi:
    async def patch_points(self, values): raise napi.NibeApiError("boom")
try: asyncio.run(aux.async_set_aux(AuxCoord(FailApi()), "block_heating", True)); ok = False
except HomeAssistantError: ok = True
check("aux: API failure surfaces as HomeAssistantError", ok)

c = AuxCoord(); c.data[aux.STATE_POINT]["metadata"]["modbusRegisterID"] = 1
try: asyncio.run(aux.async_set_aux(c, "block_heating", True)); ok = False
except HomeAssistantError: ok = True
check("aux: register mismatch still refuses to write", ok and c.api.log == [])

# ------------------------------------------------------------------ entity write + read-back
def mk_point(raw, pid=7):
    return {"title": "T", "metadata": {"variableType": "integer", "variableSize": "s16", "divisor": 10, "isWritable": True}, "value": {"isOk": True, "integerValue": raw}}
class EApi:
    def __init__(self, fresh_raw=215, patch_result=None, patch_exc=None, point_exc=None):
        self.fresh_raw, self.patch_result, self.patch_exc, self.point_exc, self.patched = fresh_raw, patch_result or {}, patch_exc, point_exc, []
    async def patch_points(self, v):
        if self.patch_exc: raise self.patch_exc
        self.patched.append(v); return self.patch_result
    async def get_point(self, pid):
        if self.point_exc: raise self.point_exc
        return mk_point(self.fresh_raw)
class ECoord:
    serial = "S"; device_info = {}
    def __init__(self, api):
        self.api = api; self.data = {7: mk_point(100)}; self.refreshes = 0; self.updates = 0
        self.infos = {7: catalog.PointInfo(point_id=7, title="T", name="T", kind="number", enabled=True, live=True)}
    async def async_request_refresh(self): self.refreshes += 1
    def async_update_listeners(self): self.updates += 1
    def async_update_point_listeners(self, ids): self.updates += 1

class Cap(logging.Handler):
    def __init__(self): super().__init__(); self.msgs = []
    def emit(self, r): self.msgs.append(r.getMessage())
cap = Cap(); logging.getLogger("nibe_local_api.entity").addHandler(cap)

def write(api):
    c = ECoord(api); e = entity.NibePointEntity(c, 7); cap.msgs.clear()
    try: asyncio.run(e._write_raw(215)); err = None
    except HomeAssistantError as x: err = x
    return c, e, err
c, e, err = write(EApi(fresh_raw=215))
check("write: value read back and published without a full refresh", err is None and c.data[7]["value"]["integerValue"] == 215 and c.updates == 1 and c.refreshes == 0 and not cap.msgs)
c, e, err = write(EApi(fresh_raw=100))
check("write: unchanged value logs a warning (e.g. read-only mode)", err is None and len(cap.msgs) == 1 and "read-only" in cap.msgs[0], cap.msgs)
c, e, err = write(EApi(point_exc=napi.NibeApiError("x")))
check("write: single-point read fails -> falls back to normal refresh", err is None and c.refreshes == 1)
c, e, err = write(EApi(patch_exc=napi.NibeApiError("net down")))
check("write: network error becomes HomeAssistantError", isinstance(err, HomeAssistantError) and "net down" in str(err))
c, e, err = write(EApi(patch_result={"7": "error: read only value"}))
check("write: pump 'error:' status becomes HomeAssistantError", isinstance(err, HomeAssistantError) and "read only" in str(err))
check("entity: static attributes and raw_value are not recorded",
      {"description", "menu_note", "raw_value", "nibe_title"} <= set(entity.NibePointEntity._unrecorded_attributes))

# ------------------------------------------------------------------ coordinator polling
class PApi:
    def __init__(self, points=None, device=None, notes=None):
        self.points, self.device, self.notes = points, device, notes
    async def get_points(self):
        if isinstance(self.points, Exception): raise self.points
        return self.points
    async def get_device(self):
        if isinstance(self.device, Exception): raise self.device
        return self.device
    async def get_notifications(self):
        if isinstance(self.notes, Exception): raise self.notes
        return self.notes or []
    async def set_mode(self, *a):
        if isinstance(self.device, Exception): raise self.device
        return self.device
entry = types.SimpleNamespace(options={})
info = {"serial": "S", "name": "N", "manufacturer": "NIBE", "firmware": ""}
def coord(api):
    co = pkg.NibeCoordinator(None, entry, api, info); return co
good = {4: mk_point(72)}
co = coord(PApi(good, napi.NibeApiError("flaky"))); co.device_state = {"aidMode": "off"}
r = asyncio.run(co._async_update_data())
check("poll: failed device-state call keeps the good points and the old state", r is good and co.device_state == {"aidMode": "off"})
co = coord(PApi(good, napi.NibeAuthError("401")))
try: asyncio.run(co._async_update_data()); ok = False
except ConfigEntryAuthFailed: ok = True
check("poll: 401 on device-state call still triggers reauth", ok)
co = coord(PApi(napi.NibeApiError("down"), {}))
try: asyncio.run(co._async_update_data()); ok = False
except UpdateFailed: ok = True
check("poll: failed points call -> UpdateFailed", ok)
co = coord(PApi(good, {"aidMode": "on"}, napi.NibeApiError("404")))
r = asyncio.run(co._async_update_data())
check("poll: notifications failure -> empty alarms, poll still succeeds", r is good and co.alarms == [] and co.device_state == {"aidMode": "on"})

co = coord(PApi(good, {"aidMode": "on", "smartMode": "normal"}))
asyncio.run(co.async_set_mode("aidmode", "aidMode", "on"))
check("mode write: verified state is published immediately", co.device_state["aidMode"] == "on" and co.listener_updates == 1)
co = coord(PApi(good, napi.NibeApiError("not applied")))
try: asyncio.run(co.async_set_mode("aidmode", "aidMode", "on")); ok = False
except HomeAssistantError: ok = True
check("mode write: failure becomes HomeAssistantError", ok)
co = coord(PApi(good, None))
asyncio.run(co.async_set_mode("aidmode", "aidMode", "on"))
check("mode write: unverifiable -> normal refresh", co.refreshes == 1)
check("coordinator owns an asyncio.Lock for AUX", isinstance(co.aux_lock, asyncio.Lock))

# ------------------------------------------------------------------ services + unload
E = lambda eid, st, rt: types.SimpleNamespace(entry_id=eid, state=st, runtime_data=rt)
class Services:
    def __init__(self): self.removed = []
    def async_remove(self, d, s): self.removed.append((d, s))
class CE:
    def __init__(self, entries): self.entries = entries
    def async_entries(self, domain): return self.entries
    async def async_unload_platforms(self, entry, platforms): return True
class Hass:
    def __init__(self, entries): self.config_entries = CE(entries); self.services = Services()
live, stale = E("a", ConfigEntryState.LOADED, "COORD-A"), E("b", "not_loaded", "STALE-B")
check("service target: only LOADED entries, stale runtime_data ignored", pkg._loaded_coordinators(Hass([stale, live])) == ["COORD-A"])
h = Hass([live])
check("unload: last loaded entry -> service removed", asyncio.run(pkg.async_unload_entry(h, live)) and h.services.removed == [("nibe_local_api", "set_aux")])
other = E("c", ConfigEntryState.LOADED, "COORD-C"); h = Hass([live, other])
asyncio.run(pkg.async_unload_entry(h, live))
check("unload: another entry still loaded -> service kept", h.services.removed == [])

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
