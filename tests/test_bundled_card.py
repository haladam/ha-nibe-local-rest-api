"""0.9.0: the bundled Lovelace card is served and registered by the integration."""
import sys, asyncio, importlib.util, importlib, types, json, os, re, ast, hashlib, logging
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import SRC, REST_413, REST_414, FIXTURES, CARD_BUILD, PREV_082, PREV_083, version_at_least
import harness
harness.install()

spec = importlib.util.spec_from_file_location("nibe_local_api", SRC + "/__init__.py", submodule_search_locations=[SRC])
pkg = importlib.util.module_from_spec(spec); sys.modules["nibe_local_api"] = pkg
results = []
def check(name, cond, detail=""):
    results.append(bool(cond)); print(("PASS " if cond else "FAIL ") + name + (f"  [{str(detail)[:300]}]" if detail and not cond else ""))

calls = {"static": [], "js": []}
class StaticPathConfig:
    def __init__(self, url_path, path, cache_headers=True): self.url_path, self.path, self.cache_headers = url_path, path, cache_headers
def stub_modules(fail_register=False, no_frontend=False, no_http_cls=False):
    calls["static"].clear(); calls["js"].clear()
    fe = types.ModuleType("homeassistant.components.frontend"); fe.add_extra_js_url = lambda hass, url, *a, **k: calls["js"].append(url)
    ht = types.ModuleType("homeassistant.components.http"); ht.StaticPathConfig = StaticPathConfig
    if no_frontend: del fe.add_extra_js_url
    if no_http_cls: del ht.StaticPathConfig
    sys.modules["homeassistant.components.frontend"] = fe; sys.modules["homeassistant.components.http"] = ht
class Http:
    def __init__(self, fail=False): self.fail = fail
    async def async_register_static_paths(self, configs):
        await asyncio.sleep(0)
        if self.fail: raise RuntimeError("path already registered")
        calls["static"].extend(configs)
class Hass:
    def __init__(self, http=True, fail=False):
        self.data = {}
        if http: self.http = Http(fail)
    async def async_add_executor_job(self, fn, *args):
        await asyncio.sleep(0)  # a real executor job lets other tasks run
        return fn(*args)

spec.loader.exec_module(pkg)
from nibe_local_api import card as frontend

logs = []
class H(logging.Handler):
    def emit(self, r): logs.append((r.levelname, r.getMessage()))
logging.getLogger("nibe_local_api.card").addHandler(H()); logging.getLogger("nibe_local_api.card").setLevel(logging.DEBUG)

man = json.load(open(SRC + "/manifest.json"))
check("manifest: version 0.9.x, device integration, loads after frontend and http",
      version_at_least(man["version"], "0.9.0") and man["integration_type"] == "device" and man["after_dependencies"] == ["frontend", "http"] and man["requirements"] == [], man)

# ---- the bundled file
card = open(SRC + "/frontend/nibe-plant-card.js", encoding="utf-8").read()
import subprocess
subprocess.run(["sh", os.path.join(os.path.dirname(CARD_BUILD), "build.sh")], check=True, stdout=subprocess.DEVNULL)   # always compare with a fresh build of card/src
built = open(CARD_BUILD, encoding="utf-8").read()
check("bundled card is byte-identical to the built card", card == built)
check("card version equals the manifest version", re.search(r'const CARD_VERSION = "([^"]+)"', card).group(1) == man["version"])
check("card keeps the MIT notice of heatpump-flow-card", "Copyright (c) 2026 Xerolux" in card and "MIT License" in card[:3000])
notice = open(SRC + "/THIRD_PARTY_NOTICES.md", encoding="utf-8").read()
check("THIRD_PARTY_NOTICES.md carries the full licence text", "Copyright (c) 2026 Xerolux" in notice and "THE SOFTWARE IS PROVIDED \"AS IS\"" in notice and "heatpump-flow-card" in notice)
check("card makes no network requests and uses no eval / innerHTML",
      not re.search(r"\bfetch\s*\(|XMLHttpRequest|WebSocket|\beval\s*\(|new Function|innerHTML|insertAdjacentHTML|importScripts|import\s*\(|document\.write", card))
urls = set(re.findall(r"https?://[^\s\"'`)]+", re.sub(r"/\*.*?\*/", "", card, flags=re.S)))
check("the only URLs in the code are the SVG namespace", urls <= {"http://www.w3.org/2000/svg"}, urls)
check("the card registers itself once per page", "if (window.customElements.get(CARD_TAG))" in card or "customElements.get(CARD_TAG)" in card)

# ---- registration
stub_modules()
hass = Hass()
ok = asyncio.run(frontend.async_register_card(hass))
check("registers the card: returns True", ok is True)
check("static path points at the bundled file, URL under the integration's domain",
      len(calls["static"]) == 1 and calls["static"][0].url_path == "/nibe_local_api/nibe-plant-card.js" and calls["static"][0].path == SRC + "/frontend/nibe-plant-card.js", [(c.url_path, c.path) for c in calls["static"]])
check("cache headers off (the version query busts the cache instead)", calls["static"][0].cache_headers is False)
sha = hashlib.sha1(open(SRC + "/frontend/nibe-plant-card.js", "rb").read()).hexdigest()[:10]
check("extra JS url carries a content hash as version", calls["js"] == [f"/nibe_local_api/nibe-plant-card.js?v={sha}"], calls["js"])
check("static path is served from an existing file", os.path.isfile(calls["static"][0].path))
asyncio.run(frontend.async_register_card(hass)); asyncio.run(frontend.async_register_card(hass))
check("a second and third config entry do not register again", len(calls["static"]) == 1 and len(calls["js"]) == 1)
hass2 = Hass(); stub_modules(); asyncio.run(frontend.async_register_card(hass2))
async def both(h): return await asyncio.gather(frontend.async_register_card(h), frontend.async_register_card(h), frontend.async_register_card(h))
stub_modules(); hc = Hass(); rr = asyncio.run(both(hc))
check("three config entries set up at the same time register the card exactly once", rr == [True, True, True] and len(calls["static"]) == 1 and len(calls["js"]) == 1, (rr, len(calls["static"]), len(calls["js"])))
check("a fresh Home Assistant run (new hass.data) registers again", len(calls["static"]) == 1 and len(calls["js"]) == 1)

# ---- failures never reach the integration
for label, kwargs, hkw in (
    ("no http component", {}, {"http": False}),
    ("register_static_paths raises (path already registered)", {}, {"fail": True}),
    ("add_extra_js_url missing (renamed in a newer Home Assistant)", {"no_frontend": True}, {}),
    ("StaticPathConfig missing", {"no_http_cls": True}, {}),
):
    stub_modules(**kwargs); logs.clear(); h = Hass(**hkw)
    try: r = asyncio.run(frontend.async_register_card(h)); err = None
    except Exception as e: r, err = None, e
    check(f"{label}: no exception, returns False, nothing marked as registered", err is None and r is False and "nibe_local_api_card_registered" not in h.data, (r, err, h.data))
    if label.startswith("no http"):
        check("... a missing http server is only a debug message", all(l == "DEBUG" for l, _ in logs) and logs, logs)
    else:
        check(f"{label}: one warning that names the problem", [l for l, _ in logs].count("WARNING") == 1 and ("path already" in logs[-1][1] or "add_extra_js_url" in logs[-1][1] or "StaticPathConfig" in logs[-1][1]), logs)
# a failure is retried by the next config entry
stub_modules(); h = Hass(fail=True); asyncio.run(frontend.async_register_card(h)); h.http.fail = False
check("after a failure the next call tries again and succeeds", asyncio.run(frontend.async_register_card(h)) is True and len(calls["static"]) == 1)
# executor hash failure (file missing)
stub_modules(); h = Hass(); orig = frontend.card_path; frontend.card_path = lambda: "/nonexistent/card.js"
r = asyncio.run(frontend.async_register_card(h)); frontend.card_path = orig
check("a missing card file is a warning, not an error", r is False and "nibe_local_api_card_registered" not in h.data and calls["static"] == [])

# ---- wiring in __init__
tree = ast.parse(open(SRC + "/__init__.py", encoding="utf-8").read())
setup = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "async_setup_entry")
awaits = [n for n in ast.walk(setup) if isinstance(n, ast.Await) and isinstance(n.value, ast.Call)]
names = [ast.unparse(n.value.func) for n in awaits]
i_card = next(i for i, n in enumerate(names) if n == "async_register_card")
i_fwd = next(i for i, n in enumerate(names) if n.endswith("async_forward_entry_setups"))
check("async_setup_entry registers the card before the platforms are forwarded", i_card < i_fwd, names)
check("the card is registered after the first refresh succeeded (a failed setup does not register it)", names.index("coordinator.async_config_entry_first_refresh") < i_card, names)
check("card.py imports Home Assistant's frontend/http only inside the function",
      not re.search(r"^(from|import) homeassistant", open(SRC + "/card.py").read(), flags=re.M))
check("README for the card ships with it", os.path.isfile(SRC + "/frontend/README.md"))

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
