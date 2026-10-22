import json, sys, os
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(__file__))
import mockdata

HERE = os.path.dirname(os.path.abspath(__file__))

def run(shots, headless=True):
    """shots: list of dicts {name, scenario|overrides, config, width, dark, lang}. Returns results per shot."""
    out = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for s in shots:
            page = browser.new_page(viewport={"width": s.get("width", 900) + 40, "height": 1300}, device_scale_factor=s.get("scale", 1))
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.goto("file://" + os.path.join(HERE, "page.html"))
            if s.get("dark"):
                page.evaluate("document.body.classList.add('dark')")
            page.evaluate(f"document.documentElement.style.setProperty('--w','{s.get('width', 900)}px')")
            ov = dict(mockdata.scenario(s["scenario"])) if s.get("scenario") else {}
            ov.update({int(k): v for k, v in (s.get("overrides") or {}).items()})
            states, entities = mockdata.build(ov)
            for k in s.get("drop", []):  # drop entities by point id
                for eid in [e for e, st in states.items() if st["attributes"]["point_id"] == k]:
                    states.pop(eid); entities.pop(eid)
            for eid, st in (s.get("extra_states") or {}).items():
                states[eid] = st
            hass = {"states": states, "entities": entities, "locale": {"language": s.get("lang", "en")}, "language": s.get("lang", "en")}
            cfg = s.get("config") or {"type": "custom:nibe-plant-card"}
            page.evaluate("""([cfg, hass]) => {
                const el = document.createElement('nibe-plant-card');
                document.getElementById('holder').appendChild(el);
                el.setConfig(cfg); el.hass = hass; window.__card = el;
            }""", [cfg, hass])
            page.wait_for_timeout(250)
            res = {"name": s["name"], "errors": errors}
            if s.get("after"):
                res["after"] = page.evaluate(s["after"])
            holder = page.locator("#holder")
            holder.screenshot(path=os.path.join(HERE, "out", s["name"] + ".png"))
            out.append(res)
            page.close()
        browser.close()
    return out

if __name__ == "__main__":
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    shots = [
        {"name": "wide_idle", "scenario": "idle", "config": {"type": "custom:nibe-plant-card", "pv": {"power": "sensor.pv_power"}},
         "extra_states": {"sensor.pv_power": {"entity_id": "sensor.pv_power", "state": "3480", "attributes": {"unit_of_measurement": "W"}}}},
        {"name": "wide_heating", "scenario": "heating"},
        {"name": "wide_hotwater", "scenario": "hotwater"},
    ]
    for r in run(shots):
        print(r)
