"""Behaviour tests of nibe-plant-card.js in Chromium with a mock `hass` built from fixtures/points_live.csv."""
import copy, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright
import mockdata

HERE = os.path.dirname(os.path.abspath(__file__))
results = []
def check(name, cond, detail=""):
    results.append(bool(cond)); print(("PASS " if cond else "FAIL ") + name + (f"  [{str(detail)[:300]}]" if detail and not cond else ""))

READ = """() => {
  const root = window.__card.shadowRoot;
  const out = {readouts: {}, pairs: [], chips: [], pills: [], texts: [], dots: []};
  root.querySelectorAll('.npc-readout').forEach(r => { const t = r.querySelectorAll('text'); out.readouts[t[0].textContent] = t[1].textContent; out.pairs.push([t[0].textContent, t[1].textContent]); });
  root.querySelectorAll('.npc-chip').forEach(c => { if (c.style.display !== 'none') out.chips.push(c.textContent.trim()); });
  root.querySelectorAll('.npc-pill text').forEach(t => out.pills.push(t.textContent));
  root.querySelectorAll('svg text').forEach(t => out.texts.push(t.textContent));
  const svg = root.querySelector('svg'); out.viewBox = svg ? svg.getAttribute('viewBox') : null;
  out.note = root.querySelector('.npc-note') ? {text: root.querySelector('.npc-note').textContent, shown: root.querySelector('.npc-note').style.display !== 'none'} : null;
  out.title = root.querySelector('.npc-header') ? root.querySelector('.npc-header').textContent : null;
  out.running = [...root.querySelectorAll('.npc-pipe-active, .npc-pipe.npc-running')].length;
  return out;
}"""

class Page:
    def __init__(self, browser, scenario="idle", overrides=None, config=None, width=900, lang="en", drop=(), extra=None, mutate=None, errors=None, include=(), height=1300):
        self.page = browser.new_page(viewport={"width": width + 40, "height": height})
        self.errors = errors if errors is not None else []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.on("console", lambda m: self.errors.append(m.text) if m.type == "error" else None)
        self.page.goto("file://" + os.path.join(HERE, "page.html"))
        self.page.evaluate(f"document.documentElement.style.setProperty('--w','{width}px')")
        ov = dict(mockdata.scenario(scenario)); ov.update(overrides or {})
        self.states, self.entities = mockdata.build(ov, include=include)
        for k in drop:
            for eid in [e for e, st in self.states.items() if st["attributes"]["point_id"] == k]:
                self.states.pop(eid); self.entities.pop(eid)
        for eid, st in (extra or {}).items(): self.states[eid] = st
        if mutate: mutate(self.states, self.entities)
        self.lang = lang
        self.config = config or {"type": "custom:nibe-plant-card"}
        self.page.evaluate("""([cfg, hass]) => { const el = document.createElement('nibe-plant-card'); document.getElementById('holder').appendChild(el); el.setConfig(cfg); el.hass = hass; window.__card = el; }""",
                           [self.config, self.hass()])
        self.page.wait_for_timeout(120)
    def hass(self):
        return {"states": self.states, "entities": self.entities, "locale": {"language": self.lang}, "language": self.lang}
    def push(self, new_entities=None):
        if new_entities is not None: self.entities = new_entities
        self.page.evaluate("(h) => { window.__card.hass = h; }", self.hass()); self.page.wait_for_timeout(60)
    def set_state(self, point, state, raw=None):
        for e, st in self.states.items():
            if st["attributes"]["point_id"] == point:
                st["state"] = state
                if raw is not None: st["attributes"]["raw_value"] = raw
                return e
        raise KeyError(point)
    def read(self): return self.page.evaluate(READ)
    def close(self): self.page.close()

def by_point(states, point):
    return next(e for e, st in states.items() if st["attributes"]["point_id"] == point)

with sync_playwright() as p:
    browser = p.chromium.launch()
    errs = []

    # ---- discovery and values (heating scenario)
    pg = Page(browser, "heating", errors=errs); r = pg.read()
    check("card renders the wide layout at 900 px", r["viewBox"] == "0 0 980 560", r["viewBox"])
    rd = r["readouts"]
    check("outdoor temperature read from point 4 (3.4 °C)", rd.get("Outside") == "3.4 °C", rd)
    check("flow / return / target read from points 8, 10, 1708", (rd.get("Flow"), rd.get("Return"), rd.get("Target")) == ("31.4 °C", "27.2 °C", "30.5 °C"), rd)
    check("brine in / out from points 13 and 14", rd.get("Brine in") == "8.1 °C" and rd.get("Brine out") == "4.2 °C", rd)
    check("compressor frequency and power", rd.get("Compressor") == "52 Hz" and rd.get("Power", "").endswith("W") and "1,240" in rd["Power"], rd)
    check("tank top temperature (BT7) is shown once, inside the vessel, and not as a readout below the tank", "Top (BT7)" not in rd and pg.page.evaluate("() => [...window.__card.shadowRoot.querySelectorAll('.npc-tank .npc-pill title')].filter(t => t.textContent === 'BT7').length") == 1, rd)
    check("hot water start and stop temperature sit next to each other below the tank", rd.get("Start") == "2.0 °C" and rd.get("Stop") == "5.0 °C" and list(rd).index("Stop") == list(rd).index("Start") + 1, rd)
    check("mode chip says Heating from priority code 30", "Heating" in r["chips"], r["chips"])
    check("title absent unless configured", r["title"] is None)
    check("no error note when entities are found", r["note"] and not r["note"]["shown"], r["note"])

    # COP: produced 0.9 / used 0.22 = 4.09 -> 4.1
    check("COP (1 h) = produced / used of the hourly log (0.9 / 0.22 = 4.1)", rd.get("COP (1 h)") == "4.1", rd)
    # hot water stop temperature by demand mode
    for code, start, expect in ((0, "2.0 °C", "5.0 °C"), (1, "40.0 °C", "45.0 °C"), (2, "67.0 °C", "70.0 °C"), (4, "–", "–")):
        pg.set_state(3697, {0: "Small", 1: "Medium", 2: "Large", 4: "Smart control"}[code], raw=float(code)); pg.push()
        check(f"stop temperature for hot water demand {code}: {expect}", pg.read()["readouts"].get("Stop") == expect, pg.read()["readouts"].get("Stop"))
        check(f"start temperature for hot water demand {code}: {start}", pg.read()["readouts"].get("Start") == start, pg.read()["readouts"].get("Start"))
    for label in ("Start", "Stop"):
        pg.page.evaluate("window.__moreInfo.length = 0")
        pg.page.evaluate("(l) => { [...window.__card.shadowRoot.querySelectorAll('.npc-readout')].find(r => r.querySelector('text').textContent === l).dispatchEvent(new MouseEvent('click', {bubbles: true, composed: true})); }", label)
        check(f"clicking {label} opens the hot water demand entity", pg.page.evaluate("window.__moreInfo") == [by_point(pg.states, 3697)], pg.page.evaluate("window.__moreInfo"))
    # enum raw_value: state label is German, raw 20 means hot water
    pg.set_state(1758, "Warmwasser", raw=20.0); pg.set_state(2002, "on"); pg.push()
    check("priority taken from raw_value, not from the (translated) state label", "Hot water" in pg.read()["chips"], pg.read()["chips"])
    pg.set_state(1758, "Warmwasser", raw=60.0); pg.push()
    check("priority 60 = cooling chip", "Cooling" in pg.read()["chips"], pg.read()["chips"])
    # unavailable entity shows a dash and does not break
    pg.set_state(4, "unavailable"); pg.push()
    check("unavailable outdoor sensor shows a dash", pg.read()["readouts"].get("Outside") == "–", pg.read()["readouts"].get("Outside"))
    pg.set_state(4, "unknown"); pg.set_state(8, "unknown"); pg.set_state(13, "unavailable"); pg.push()
    check("unknown / unavailable states: no script errors", not errs, errs)
    pg.set_state(4, "-7.5"); pg.push()
    check("a changed value is shown on the next hass update", pg.read()["readouts"].get("Outside") == "-7.5 °C", pg.read()["readouts"].get("Outside"))
    # signature skipping: identical push leaves DOM untouched
    n = pg.page.evaluate("""() => { const t = window.__card.shadowRoot.querySelector('.npc-value'); window.__mut = 0; new MutationObserver(m => window.__mut += m.length).observe(window.__card.shadowRoot, {subtree: true, childList: true, characterData: true, attributes: true}); window.__card.hass = {...window.__card.hass}; return 1; }""")
    pg.page.wait_for_timeout(100)
    check("a hass update without changes causes no DOM work", pg.page.evaluate("window.__mut") == 0, pg.page.evaluate("window.__mut"))
    pg.close()

    # ---- COP edge cases
    pg = Page(browser, "heating", overrides={25158: 0.0})
    check("COP is a dash when almost nothing was used in the last hour", pg.read()["readouts"].get("COP (1 h)") == "–", pg.read()["readouts"].get("COP (1 h)")); pg.close()
    pg = Page(browser, "heating", drop=[25154, 25155, 25157]); r = pg.read()
    check("COP is a dash when the pump has no produced-energy points", r["readouts"].get("COP (1 h)") == "–", r["readouts"].get("COP (1 h)")); pg.close()

    pg = Page(browser, "heating", overrides={25154: 0.2, 25158: 0.05})
    check("COP is a dash when less than 0.1 kWh was used (0.2 / 0.05 would give a meaningless 4.0)", pg.read()["readouts"].get("COP (1 h)") == "–", pg.read()["readouts"].get("COP (1 h)")); pg.close()
    pg = Page(browser, "heating")
    pg.states[by_point(pg.states, 22130)]["state"] = "1.24"; pg.states[by_point(pg.states, 22130)]["attributes"]["unit_of_measurement"] = "kW"; pg.push()
    check("heat pump power reported in kW is shown in watts", pg.read()["pairs"][2:3] == [["Power", "1,240 W"]] or ["Power", "1,240 W"] in pg.read()["pairs"], pg.read()["pairs"]); pg.close()
    pg = Page(browser, "heating")
    pg.set_state(1758, "unavailable", raw=20.0); pg.push()
    check("an unavailable enum sensor with a stale raw_value attribute is treated as unknown", "Hot water" not in pg.read()["chips"] and "Heating" not in pg.read()["chips"], pg.read()["chips"]); pg.close()

    # ---- layout
    pg = Page(browser, "heating", width=380); check("narrow layout below 560 px", pg.read()["viewBox"] == "0 0 480 1010", pg.read()["viewBox"]); pg.close()
    pg = Page(browser, "heating", width=900, config={"type": "custom:nibe-plant-card", "layout": "narrow"}); check("layout: narrow forces the phone layout", pg.read()["viewBox"] == "0 0 480 1010"); pg.close()
    pg = Page(browser, "heating", width=380, config={"type": "custom:nibe-plant-card", "layout": "wide"}); check("layout: wide forces the wide layout", pg.read()["viewBox"] == "0 0 980 560"); pg.close()
    pg = Page(browser, "heating", width=900)
    pg.page.evaluate("document.documentElement.style.setProperty('--w','400px')"); pg.page.wait_for_timeout(250)
    check("resizing the card below 560 px switches to the narrow layout", pg.read()["viewBox"] == "0 0 480 1010", pg.read()["viewBox"])
    pg.page.evaluate("document.documentElement.style.setProperty('--w','900px')"); pg.page.wait_for_timeout(250)
    check("... and back to wide", pg.read()["viewBox"] == "0 0 980 560", pg.read()["viewBox"])
    check("same values after switching layout", pg.read()["readouts"].get("Outside") == "3.4 °C"); pg.close()

    # ---- title, names, tank configuration
    pg = Page(browser, "heating", config={"type": "custom:nibe-plant-card", "title": "Heating plant", "heatpump": {"name": "My pump"},
                                           "tank": {"name": "Buffer", "hot_water_l": 200, "jacket_l": 100}, "circuit": {"type": "radiator", "name": "Radiators"}})
    r = pg.read()
    check("title shown", r["title"] == "Heating plant", r["title"])
    check("custom names for pump, tank and circuit", all(t in r["texts"] for t in ("My pump", "Buffer", "Radiators")), r["texts"][:20])
    check("tank subtitle follows the configured volumes", "200 L hot water · 100 L jacket" in r["texts"], [t for t in r["texts"] if " L " in t]); pg.close()
    pg = Page(browser, "heating"); r = pg.read()
    check("defaults: Greenwater 450/300 with 450 L + 300 L", "Greenwater 450/300" in r["texts"] and "450 L hot water · 300 L jacket" in r["texts"], r["texts"][:20])
    check("default circuit is underfloor heating (point 3976 reads underfloor)", "Underfloor heating" in r["texts"], r["texts"]); pg.close()
    for code, label, expect in ((1, "Radiators", "Radiators"), (3, "Both", "Radiators & underfloor"), (2, "Underfloor", "Underfloor heating")):
        pg = Page(browser, "heating", overrides={3976: code}, include=(3976,)); t = pg.read()["texts"]
        check(f"flow setting {code} picks the emitter title '{expect}'", expect in t, [x for x in t if "oor" in x or "adiat" in x]); pg.close()

    pg = Page(browser, "heating", overrides={3976: 1}); t = pg.read()["texts"]
    check("flow setting entity disabled (the integration's default): card keeps the underfloor drawing", "Underfloor heating" in t, t)
    pg.close()
    pg = Page(browser, "heating", overrides={3976: 2}, include=(3976,), config={"type": "custom:nibe-plant-card", "circuit": {"type": "radiator"}}); t = pg.read()["texts"]
    check("circuit.type in the config wins over the pump's flow setting", "Radiators" in t and "Underfloor heating" not in t, t); pg.close()
    pg = Page(browser, "heating", overrides={3976: 1}, include=(3976,))
    shown = pg.page.evaluate("""() => [...window.__card.shadowRoot.querySelectorAll('.npc-emitter > g')].map(g => g.style.display)""")
    check("only the matching emitter drawing is visible (radiator)", shown == ["none", "", "none", "none"], shown)
    pg.set_state(3976, "Underfloor heating", raw=2.0); pg.push()
    shown = pg.page.evaluate("""() => [...window.__card.shadowRoot.querySelectorAll('.npc-emitter > g')].map(g => g.style.display)""")
    check("... and follows a later change of the setting", shown == ["", "none", "none", "none"], shown); pg.close()

    # ---- languages
    pg = Page(browser, "hotwater", lang="de"); r = pg.read()
    check("German UI texts", "Fußbodenheizung" in r["texts"] and "Warmwasser" in r["chips"] and {"Start", "Stopp"} <= set(r["readouts"]), (r["chips"], list(r["readouts"])))
    check("German number format (decimal comma)", r["readouts"].get("Außen") == "8,9 °C", r["readouts"].get("Außen")); pg.close()
    pg = Page(browser, "hotwater", lang="fr"); r = pg.read()
    check("unknown language falls back to English", "Hot water" in r["chips"], r["chips"]); pg.close()

    # ---- explicit entity overrides
    extra = {"sensor.my_outdoor": {"entity_id": "sensor.my_outdoor", "state": "-12.5", "attributes": {"unit_of_measurement": "°C"}}}
    pg = Page(browser, "heating", extra=extra, config={"type": "custom:nibe-plant-card", "entities": {"outdoor": "sensor.my_outdoor"}})
    check("entities: slot override wins over discovery", pg.read()["readouts"].get("Outside") == "-12.5 °C", pg.read()["readouts"].get("Outside")); pg.close()
    pg = Page(browser, "heating", extra=extra, config={"type": "custom:nibe-plant-card", "entities": {"outdoor": "sensor.does_not_exist"}})
    check("entities: override pointing nowhere shows a dash instead of falling back", pg.read()["readouts"].get("Outside") == "–", pg.read()["readouts"].get("Outside")); pg.close()

    # ---- device filter
    def second_device(states, entities):
        clone = {}
        for eid, st in list(states.items()):
            e2 = eid.replace("nibe_s1155", "other_pump"); s2 = copy.deepcopy(st); s2["entity_id"] = e2
            if st["attributes"]["point_id"] == 4: s2["state"] = "-20"
            clone[e2] = s2; entities[e2] = {"entity_id": e2, "device_id": "dev_other"}
        # the other pump comes first in iteration order
        items = list(clone.items()) + list(states.items()); states.clear(); states.update(items)
    pg = Page(browser, "heating", mutate=second_device)
    check("two NIBE devices without a filter: first one found wins", pg.read()["readouts"].get("Outside") == "-20.0 °C", pg.read()["readouts"].get("Outside"))
    pg.close()
    pg = Page(browser, "heating", mutate=second_device, config={"type": "custom:nibe-plant-card", "device": "dev_nibe"})
    check("device: filter picks the entities of that device only", pg.read()["readouts"].get("Outside") == "3.4 °C", pg.read()["readouts"].get("Outside")); pg.close()

    # ---- missing integration
    pg = Page(browser, "heating", mutate=lambda s, e: (s.clear(), e.clear()), errors=errs)
    r = pg.read()
    check("no NIBE entities: hint shown, nothing crashes", r["note"] and r["note"]["shown"] and "No NIBE" in r["note"]["text"] and not errs, (r["note"], errs)); pg.close()
    def only_unrelated(states, entities):
        states.clear(); entities.clear(); states["sensor.temp"] = {"entity_id": "sensor.temp", "state": "5", "attributes": {"point_id": "x"}}
    pg = Page(browser, "heating", mutate=only_unrelated, errors=errs); r = pg.read()
    check("entities with a non-numeric point_id attribute are ignored", r["note"]["shown"] and not errs, errs); pg.close()
    # entities appear later (integration loads after the dashboard)
    pg = Page(browser, "heating", mutate=lambda s, e: (s.clear(), e.clear()))
    full_states, full_entities = mockdata.build(mockdata.scenario("heating"))
    pg.states, pg.entities = full_states, full_entities; pg.push()
    check("entities that show up later are picked up", pg.read()["readouts"].get("Outside") == "3.4 °C" and not pg.read()["note"]["shown"], pg.read()["readouts"].get("Outside")); pg.close()

    # ---- PV
    pv_state = lambda v, u="W": {"sensor.pv": {"entity_id": "sensor.pv", "state": v, "attributes": {"unit_of_measurement": u}}}
    pg = Page(browser, "heating", extra=pv_state("3.48", "kW"), config={"type": "custom:nibe-plant-card", "pv": {"power": "sensor.pv"}})
    check("PV power in kW is shown in watts", ["Power", "3,480 W"] in pg.read()["pairs"], pg.read()["pairs"][:3]); pg.close()
    pg = Page(browser, "heating", extra=pv_state("unavailable"), config={"type": "custom:nibe-plant-card", "pv": {"power": "sensor.pv"}}, errors=errs)
    check("PV sensor unavailable: dash, no errors", pg.read()["pairs"][0] == ["Power", "–"] and not errs, (pg.read()["pairs"][:2], errs)); pg.close()
    pg = Page(browser, "heating", drop=[6002, 14314]); r = pg.read()
    check("without PV entities and without a pv: block the PV panel is not drawn", "Photovoltaics" not in r["texts"], r["texts"][:6]); pg.close()
    pg = Page(browser, "heating"); r = pg.read()
    check("with the pump's own PV points (6002, 14314) the PV panel appears", "Photovoltaics" in r["texts"], r["texts"][:6]); pg.close()

    FRONIUS = "sensor.fronius_inverter_symo_gen24_10_0_pv_power"
    fr = lambda v, u="W": {FRONIUS: {"entity_id": FRONIUS, "state": v, "attributes": {"unit_of_measurement": u}}}
    cfgf = {"type": "custom:nibe-plant-card", "pv": {"power": FRONIUS}}
    pg = Page(browser, "heating", overrides={14314: 1500}, extra=fr("4210"), config=cfgf); pairs = pg.read()["pairs"]
    check("PV block: Power comes from pv.power (the Fronius sensor), the second value is labelled 'Excess solar'", ["Power", "4,210 W"] in pairs and ["Excess solar", "1,500 W"] in pairs and not any(p[0] == "To pump" for p in pairs), pairs[:3]); pg.close()
    pg = Page(browser, "heating", overrides={14314: 1500}, extra=fr("4.21", "kW"), config=cfgf); pairs = pg.read()["pairs"]
    check("PV block: a Fronius sensor in kW is converted to watts", ["Power", "4,210 W"] in pairs, pairs[:3]); pg.close()
    pg = Page(browser, "heating", overrides={14314: 1500}, extra=fr("4210"), config=cfgf, lang="de"); pairs = pg.read()["pairs"]
    check("PV block in German: 'PV-Überschuss'", any(p[0] == "PV-Überschuss" and p[1].endswith("W") for p in pairs), pairs[:3]); pg.close()
    pg = Page(browser, "heating", extra={**fr("4210"), "sensor.soc": {"entity_id": "sensor.soc", "state": "63", "attributes": {"unit_of_measurement": "%"}}},
              config={"type": "custom:nibe-plant-card", "pv": {"power": FRONIUS, "battery": "sensor.soc"}}); pairs = pg.read()["pairs"]
    check("with pv.battery configured the second PV value is the battery level, not the excess", ["Battery", "63 %"] in pairs and not any(p[0] == "Excess solar" for p in pairs), pairs[:3]); pg.close()
    pg = Page(browser, "heating", extra=fr("unavailable"), config=cfgf, errors=errs); pairs = pg.read()["pairs"]
    check("Fronius sensor unavailable (night, inverter asleep): dash instead of a number, no errors", pairs[0] == ["Power", "–"] and not errs, (pairs[:2], errs)); pg.close()

    # ---- circuit panel: same flow animation as the ground loop (gradient + moving dots), no wave lines
    RED, BLUE = "#ef4444", "#3b82f6"
    EMITTER = """() => { const root = window.__card.shadowRoot; const svg = root.querySelector('svg');
        const g = [...root.querySelectorAll('.npc-emitter > g')].find(x => x.style.display !== 'none');
        return {waves: root.querySelectorAll('.npc-heatwave').length, lines: [...g.querySelectorAll('.npc-emitter-line, .npc-rail')].map(l => {
          const m = l.style.stroke.match(/#([^")]+)/); const d = l.nextElementSibling;
          const stops = m ? [...svg.querySelectorAll('linearGradient')].find(x => x.id === m[1]).querySelectorAll('stop') : [];
          const n = l.getTotalLength(), a = l.getPointAtLength(0), b = l.getPointAtLength(n);
          const gr = m ? [...svg.querySelectorAll('linearGradient')].find(x => x.id === m[1]) : null;
          const axis = gr ? ['x1', 'y1', 'x2', 'y2'].map(k => Math.round(Number(gr.getAttribute(k)))) : null;
          return {axis, gradient: Boolean(m), c0: stops[0] ? stops[0].getAttribute('stop-color') : null, c1: stops[1] ? stops[1].getAttribute('stop-color') : null,
                  dots: d.classList.contains('npc-dots') && d.style.display !== 'none', sameShape: d.getAttribute('d') === l.getAttribute('d'),
                  start: [Math.round(a.x), Math.round(a.y)], end: [Math.round(b.x), Math.round(b.y)]}; })}; }"""
    for label, sc, over, cfgx, exp in (
        ("underfloor heating", "heating", {}, None, (RED, BLUE, True)),
        ("ceiling cooling (passive)", "cooling", {}, None, (BLUE, RED, True)),
        ("ceiling cooling (active)", "cooling", {1799: 40, 1973: 1}, None, (BLUE, RED, True)),
        ("ceiling cooling (active, cooling pump off)", "cooling", {3149: 0, 1799: 40, 1973: 1}, None, (BLUE, RED, True)),
        ("radiator heating", "heating", {}, {"type": "custom:nibe-plant-card", "circuit": {"type": "radiator"}}, (RED, BLUE, True)),
        ("both emitters heating", "heating", {}, {"type": "custom:nibe-plant-card", "circuit": {"type": "both"}}, (RED, BLUE, True)),
        ("idle", "idle", {}, None, (None, None, False)),
        ("cooling mode but cooling pump stopped", "cooling", {3149: 0}, None, (None, None, False)),
    ):
        pg = Page(browser, sc, overrides=over, config=cfgx); e = pg.page.evaluate(EMITTER); pg.close()
        c0, c1, flows = exp
        ok = len(e["lines"]) >= 1 and all(l["dots"] == flows and l["gradient"] == flows and l["c0"] == c0 and l["c1"] == c1 and l["sameShape"] for l in e["lines"])
        check(f"{label}: {'gradient ' + ('red to blue' if c0 == RED else 'blue to red') + ' with moving dots' if flows else 'no gradient and no dots'}", ok, e["lines"])
        check(f"{label}: no wave lines", e["waves"] == 0, e["waves"])
    pg = Page(browser, "heating", config={"type": "custom:nibe-plant-card", "animation": False}); e = pg.page.evaluate(EMITTER); pg.close()
    check("animation: false keeps the gradient but hides the dots", all(l["gradient"] and not l["dots"] for l in e["lines"]), e["lines"])
    pg = Page(browser, "heating"); pg.set_state(1758, "Off", raw=10.0); pg.set_state(1799, "0"); pg.set_state(1973, "off", raw=0.0); pg.push(); e = pg.page.evaluate(EMITTER); pg.close()
    check("heating stops: the lines go grey and the dots stop", all(not l["gradient"] and not l["dots"] for l in e["lines"]), e["lines"])

    # ---- alarm, boost, cooling chips
    pg = Page(browser, "alarm"); check("alarm number shown as chip", "Alarm 163" in pg.read()["chips"], pg.read()["chips"]); pg.close()
    pg = Page(browser, "boost"); check("boost chip with minutes", "Boost 142 min" in pg.read()["chips"], pg.read()["chips"])
    check("additional heater chip with kW", any(c.startswith("Heater") for c in pg.read()["chips"]), pg.read()["chips"]); pg.close()
    pg = Page(browser, "cooling"); r = pg.read()
    check("cooling: mode chip and passive cooling text", "Cooling" in r["chips"] and "Passive cooling" in r["texts"], (r["chips"], r["texts"][:30])); pg.close()
    pg = Page(browser, "heating"); check("passive cooling text hidden while heating", pg.page.evaluate("""() => [...window.__card.shadowRoot.querySelectorAll('text')].filter(t => t.textContent === 'Passive cooling' && t.style.display !== 'none').length""") == 0); pg.close()

    # ---- summer: cooling through the ceiling circuits
    VIS = "() => [...window.__card.shadowRoot.querySelectorAll('.npc-pipe-group')].filter(g => g.style.display !== 'none').length"
    EMIT = "() => [...window.__card.shadowRoot.querySelectorAll('.npc-emitter > g')].map(g => g.style.display)"
    pg = Page(browser, "cooling"); r = pg.read()
    check("cooling: the circuit becomes 'Ceiling cooling' with the passive cooling subtitle", "Ceiling cooling" in r["texts"] and "Passive cooling" in r["texts"] and "Underfloor heating" not in r["texts"], [t for t in r["texts"] if "ooling" in t or "oor" in t])
    check("cooling: only the ceiling drawing is visible", pg.page.evaluate(EMIT) == ["none", "none", "none", ""], pg.page.evaluate(EMIT))
    check("cooling: target shows the calculated cooling supply (point 2695), not the heating curve", r["readouts"].get("Target") == "18.5 °C", r["readouts"].get("Target"))
    check("cooling: COP is a dash in passive cooling even though the log shows energy used", r["readouts"].get("COP (1 h)") == "–", r["readouts"].get("COP (1 h)"))
    pg.page.evaluate("window.__moreInfo.length = 0")
    pg.page.evaluate("""() => { [...window.__card.shadowRoot.querySelectorAll('.npc-readout')].find(r => r.querySelector('text').textContent === 'Target').dispatchEvent(new MouseEvent('click', {bubbles: true, composed: true})); }""")
    check("cooling: clicking Target opens the cooling supply entity", pg.page.evaluate("window.__moreInfo") == [by_point(pg.states, 2695)], pg.page.evaluate("window.__moreInfo"))
    cool_pipes = pg.page.evaluate(VIS); pg.close()
    pg = Page(browser, "heating"); heat_pipes = pg.page.evaluate(VIS)
    check("heating: the two passive cooling pipes (cold out, warm back) are hidden, in passive cooling they replace the two heating pipes of the circuit (wide)", cool_pipes == heat_pipes, (cool_pipes, heat_pipes))
    pg.page.evaluate("window.__moreInfo.length = 0")
    pg.page.evaluate("""() => { [...window.__card.shadowRoot.querySelectorAll('.npc-readout')].find(r => r.querySelector('text').textContent === 'Target').dispatchEvent(new MouseEvent('click', {bubbles: true, composed: true})); }""")
    check("heating: Target opens the heating curve entity (point 1708)", pg.page.evaluate("window.__moreInfo") == [by_point(pg.states, 1708)], pg.page.evaluate("window.__moreInfo"))
    check("heating: emitter drawing is the underfloor one", pg.page.evaluate(EMIT) == ["", "none", "none", "none"], pg.page.evaluate(EMIT)); pg.close()
    pg = Page(browser, "cooling", width=380); n_cool = pg.page.evaluate(VIS); pg.close()
    pg = Page(browser, "heating", width=380); n_heat = pg.page.evaluate(VIS); pg.close()
    check("phone layout: the two cooling pipes along the right edge appear in cooling only, in place of the circuit's two heating pipes", n_cool == n_heat, (n_cool, n_heat))
    pg = Page(browser, "cooling", lang="de"); check("German: Deckenkühlung / Passive Kühlung", {"Deckenkühlung", "Passive Kühlung"} <= set(pg.read()["texts"]), pg.read()["texts"]); pg.close()
    pg = Page(browser, "cooling", config={"type": "custom:nibe-plant-card", "circuit": {"cooling_type": "same"}})
    check("circuit.cooling_type: same keeps the heating drawing and title in summer", "Underfloor heating" in pg.read()["texts"] and pg.page.evaluate(EMIT) == ["", "none", "none", "none"], pg.read()["texts"]); pg.close()
    LIVE = "() => [...window.__card.shadowRoot.querySelectorAll('.npc-pipe-group')].filter(g => g.style.display !== 'none' && !g.classList.contains('npc-idle')).length"
    pg = Page(browser, "cooling"); live_passive = pg.page.evaluate(LIVE); pg.close()
    pg = Page(browser, "cooling", overrides={1799: 40, 1973: 1}); n_act = pg.page.evaluate(VIS); live_active = pg.page.evaluate(LIVE)
    check("active cooling: the circuit lanes move water (four pipes) and the two passive bypass pipes do not", live_active == live_passive + 2, (live_active, live_passive))
    note_shown = pg.page.evaluate("""() => [...window.__card.shadowRoot.querySelectorAll('text')].filter(t => t.textContent === 'Passive cooling' && t.style.display !== 'none').length""")
    check("active cooling: the ground-loop cooling pipe and its caption are hidden", n_act == heat_pipes and note_shown == 0, (n_act, heat_pipes, note_shown)); pg.close()
    pg = Page(browser, "cooling", config={"type": "custom:nibe-plant-card", "circuit": {"cooling_name": "Rooms upstairs"}})
    check("circuit.cooling_name renames the cooling circuit", "Rooms upstairs" in pg.read()["texts"]); pg.close()
    pg = Page(browser, "cooling", overrides={1799: 40, 1973: 1, 25157: 1.2, 25161: 0.3, 25158: 0.0, 25159: 0.0, 25162: 0.0, 25163: 0.0})
    r = pg.read()
    check("compressor running in cooling mode = active cooling, COP is shown (1.2 / 0.3 = 4.0)", "Active cooling" in r["texts"] and r["readouts"].get("COP (1 h)") == "4.0", (r["readouts"].get("COP (1 h)"), [t for t in r["texts"] if "ooling" in t])); pg.close()
    pg = Page(browser, "hotwater", overrides={3149: 1})
    check("circulation pump of the cooling circuit on while the pump charges hot water: still the ceiling circuit", "Ceiling cooling" in pg.read()["texts"] and "Hot water" in pg.read()["chips"], (pg.read()["texts"][:40], pg.read()["chips"])); pg.close()
    pg = Page(browser, "cooling"); pg.set_state(3149, "off", raw=0.0); pg.set_state(1758, "Off", raw=10.0); pg.push()
    check("cooling ends: back to the underfloor heating drawing", pg.page.evaluate(EMIT) == ["", "none", "none", "none"] and "Underfloor heating" in pg.read()["texts"], pg.page.evaluate(EMIT)); pg.close()

    # ---- pipes: a live connection must be animated from end to end
    ENDS = """() => [...window.__card.shadowRoot.querySelectorAll('.npc-pipe-group')]
        .filter(g => g.style.display !== 'none' && !g.classList.contains('npc-idle') && !g.classList.contains('npc-energy'))
        .map(g => { const p = g.querySelector('.npc-pipe'); const n = p.getTotalLength(); const a = p.getPointAtLength(0), b = p.getPointAtLength(n); return [Math.round(a.x), Math.round(a.y), Math.round(b.x), Math.round(b.y)]; })"""
    def connected(ends, start, goal):
        seen, todo = {tuple(start)}, [tuple(start)]
        while todo:
            cur = todo.pop()
            for x0, y0, x1, y1 in ends:
                for a, b in (((x0, y0), (x1, y1)), ((x1, y1), (x0, y0))):
                    if abs(a[0] - cur[0]) <= 1 and abs(a[1] - cur[1]) <= 1 and b not in seen:
                        seen.add(b); todo.append(b)
        return any(abs(g[0] - goal[0]) <= 1 and abs(g[1] - goal[1]) <= 1 for g in seen)
    # (hp supply port, hp return port, circuit supply, circuit return, tank supply, tank return)
    PORTS = {900: ((630, 170), (630, 340), (700, 412), (700, 457), (778, 129), (778, 244)),
             380: ((260, 570), (340, 570), (290, 684), (380, 684), (66, 760), (66, 868))}
    for width, (hp_s, hp_r, c_s, c_r, t_s, t_r) in PORTS.items():
        lay = "wide" if width == 900 else "phone"
        pg = Page(browser, "heating", width=width); ends = pg.page.evaluate(ENDS); pg.close()
        check(f"heating, {lay} layout: supply line is animated from the heat pump to the heating circuit", connected(ends, hp_s, c_s), ends)
        check(f"heating, {lay} layout: return line is animated from the heating circuit all the way back to the heat pump", connected(ends, c_r, hp_r), ends)
        check(f"heating, {lay} layout: the hot water tank is not connected", not connected(ends, hp_s, t_s) and not connected(ends, t_r, hp_r), ends)
        pg = Page(browser, "hotwater", width=width); ends = pg.page.evaluate(ENDS); pg.close()
        check(f"hot water, {lay} layout: supply and return are animated between heat pump and tank", connected(ends, hp_s, t_s) and connected(ends, t_r, hp_r), ends)
        check(f"hot water, {lay} layout: the heating circuit is not connected", not connected(ends, hp_s, c_s) and not connected(ends, c_r, hp_r), ends)
        pg = Page(browser, "idle", width=width); ends = pg.page.evaluate(ENDS); pg.close()
        check(f"idle, {lay} layout: no water line between heat pump and circuit or tank", not any(connected(ends, a, b) for a, b in ((hp_s, c_s), (c_r, hp_r), (hp_s, t_s), (t_r, hp_r))), ends)

    # ---- the emitter pipe is one continuous line from the supply port to the return port, like the ground loop
    # (heat pump supply, heat pump return, circuit supply port, circuit return port, ground port of the cold passive pipe, ground port of the warm one)
    LOOP = {900: ("wide", (630, 170), (630, 340), (700, 412), (700, 457), (220, 497), (220, 520)),
            380: ("phone", (260, 570), (340, 570), (290, 684), (380, 684), (430, 160), (430, 130))}
    for width, (lay, hp_s, hp_r, c_s, c_r, g_c, g_w) in LOOP.items():
        for typ in ("underfloor", "radiator", "both"):
            pg = Page(browser, "heating", width=width, config={"type": "custom:nibe-plant-card", "circuit": {"type": typ}})
            e = pg.page.evaluate(EMITTER); ends = pg.page.evaluate(ENDS); pg.close()
            ln = e["lines"]
            check(f"{typ}, {lay} layout: one pipe from the supply port to the return port", len(ln) == 1 and ln[0]["start"] == list(c_s) and ln[0]["end"] == list(c_r), ln)
            ax = ln[0]["axis"]
            check(f"{typ}, {lay} layout: the colour gradient runs from the supply port to the return port", ax is not None and (ax[1], ax[3]) == (c_s[1], c_r[1]) if width == 900 else ax is not None and (ax[0], ax[2]) == (c_s[0], c_r[0]), ax)
            emit = [[*ln[0]["start"], *ln[0]["end"]]] if ln and ln[0]["dots"] else []
            check(f"{typ}, {lay} layout: water runs unbroken from the heat pump through the emitter and back", bool(emit) and connected(ends + emit, hp_s, hp_r) and not connected(ends, hp_s, hp_r), (emit, ends))
        pg = Page(browser, "cooling", width=width); e = pg.page.evaluate(EMITTER); ends = pg.page.evaluate(ENDS); pg.close()
        ln = e["lines"]
        check(f"ceiling, {lay} layout (passive cooling): one pipe from the supply port to the return port", len(ln) == 1 and ln[0]["start"] == list(c_s) and ln[0]["end"] == list(c_r), ln)
        emit = [[*ln[0]["start"], *ln[0]["end"]]] if ln and ln[0]["dots"] else []
        check(f"ceiling, {lay} layout (passive cooling): the ground loop is connected through the ceiling circuit and back", bool(emit) and connected(ends + emit, g_c, g_w) and not connected(ends, g_c, g_w), (emit, ends))
        check(f"ceiling, {lay} layout (passive cooling): the heat pump is not part of the loop", not connected(ends + emit, hp_s, hp_r))
        pg = Page(browser, "cooling", width=width, overrides={1799: 40, 1973: 1}); e = pg.page.evaluate(EMITTER); ends = pg.page.evaluate(ENDS); pg.close()
        ln = e["lines"]; emit = [[*ln[0]["start"], *ln[0]["end"]]] if ln and ln[0]["dots"] else []
        check(f"ceiling, {lay} layout (active cooling): water runs from the heat pump through the ceiling circuit and back", bool(emit) and connected(ends + emit, hp_s, hp_r) and not connected(ends + emit, g_c, g_w), (emit, ends))
        pg = Page(browser, "heating", width=width); ends = pg.page.evaluate(ENDS); pg.close()
        check(f"heating, {lay} layout: passive cooling pipes are not part of the loop", not connected(ends, g_c, g_w))

    for width in (900, 380):
        pg = Page(browser, "heating", width=width)
        w = pg.page.evaluate("""() => { const r = window.__card.shadowRoot; const g = [...r.querySelectorAll('.npc-emitter > g')].find(x => x.style.display !== 'none');
            return [getComputedStyle(g.querySelector('.npc-emitter-line')).strokeWidth, getComputedStyle(r.querySelector('.npc-collector')).strokeWidth]; }"""); pg.close()
        check(f"width {width}: the emitter pipe is as thick as the ground loop pipe", w[0] == w[1], w)
    # ---- flow colours: red is the warm side, blue the cold side
    RED, BLUE, AMBER = "#ef4444", "#3b82f6", "#fbbf24"
    PIPES = """() => { const root = window.__card.shadowRoot; const svg = root.querySelector('svg');
        const col = (id) => [...svg.querySelectorAll('linearGradient')].find(g => g.id === id).querySelectorAll('stop');
        return [...root.querySelectorAll('.npc-pipe-group')].filter(g => g.style.display !== 'none').map(g => {
          const p = g.querySelector('.npc-pipe'); const n = p.getTotalLength(); const a = p.getPointAtLength(0), b = p.getPointAtLength(n);
          const s = col(p.getAttribute('stroke').slice(5, -1));
          return {a: [Math.round(a.x), Math.round(a.y)], b: [Math.round(b.x), Math.round(b.y)], c0: s[0].getAttribute('stop-color'), c1: s[1].getAttribute('stop-color'), idle: g.classList.contains('npc-idle')}; }); }"""
    def find(pipes, a, b):
        hit = [p for p in pipes if p["a"] == list(a) and p["b"] == list(b)]
        return hit[0] if hit else None
    def colour(pipes, a, b):
        p = find(pipes, a, b)
        return None if p is None else (p["c0"], p["c1"])
    # name -> (from, to) for the wide layout and for the phone layout
    LINES = {
        900: dict(trunk_s=((630, 170), (690, 170)), tank_s=((690, 170), (778, 129)), circ_s=((690, 170), (700, 412)),
                  trunk_r=((645, 340), (630, 340)), tank_r=((778, 244), (645, 340)), circ_r=((700, 457), (645, 340)),
                  to_ground=((360, 365), (220, 365)), from_ground=((220, 410), (360, 410)),
                  cool_s=((220, 497), (700, 412)), cool_r=((700, 457), (220, 520))),
        380: dict(trunk_s=((260, 570), (260, 644)), tank_s=((260, 644), (66, 760)), circ_s=((260, 644), (290, 684)),
                  trunk_r=((340, 588), (340, 570)), tank_r=((66, 868), (340, 588)), circ_r=((380, 684), (340, 588)),
                  to_ground=((305, 270), (305, 200)), from_ground=((350, 200), (350, 270)),
                  cool_s=((430, 160), (290, 684)), cool_r=((380, 684), (430, 130))),
    }
    both = lambda c: (c, c)
    for width, L in LINES.items():
        lay = "wide" if width == 900 else "phone"
        for scenario, over, expect in (
            ("heating", {}, dict(trunk_s=RED, circ_s=RED, trunk_r=BLUE, circ_r=BLUE, to_ground=BLUE, from_ground=RED)),
            ("hotwater", {}, dict(trunk_s=RED, tank_s=RED, trunk_r=BLUE, tank_r=BLUE, to_ground=BLUE, from_ground=RED)),
            ("idle", {}, dict(trunk_s=RED, circ_s=RED, tank_s=RED, trunk_r=BLUE, circ_r=BLUE, tank_r=BLUE, to_ground=BLUE, from_ground=RED)),
            ("cooling", {}, dict(to_ground=RED, from_ground=BLUE, cool_s=BLUE, cool_r=RED)),
            ("cooling", {1799: 40, 1973: 1}, dict(trunk_s=BLUE, circ_s=BLUE, trunk_r=RED, circ_r=RED, to_ground=RED, from_ground=BLUE)),
            ("cooling", {1799: 40, 1973: 1, 2002: 1, 1758: 20}, dict(trunk_s=RED, tank_s=RED, trunk_r=BLUE, tank_r=BLUE)),
        ):
            name = {(): ""}.get((), "")
            kind = "active cooling" if over.get(1799) else scenario
            if over.get(2002): kind = "hot water charge during cooling"
            pg = Page(browser, scenario, overrides=over, width=width, include=()); pipes = pg.page.evaluate(PIPES); pg.close()
            bad = {k: (colour(pipes, *L[k]), c) for k, c in expect.items() if colour(pipes, *L[k]) != both(c)}
            check(f"{kind}, {lay} layout: pipes {', '.join(sorted(expect))} have the right warm / cold colour", not bad, bad)
        pg = Page(browser, "heating", width=width); pipes = pg.page.evaluate(PIPES); pg.close()
        check(f"heating, {lay} layout: passive cooling pipes are not drawn", find(pipes, *L["cool_s"]) is None and find(pipes, *L["cool_r"]) is None)
        pg = Page(browser, "cooling", width=width); pipes = pg.page.evaluate(PIPES); pg.close()
        check(f"passive cooling, {lay} layout: the circuit is fed by the ground loop alone, the heating pipes to it are not drawn",
              find(pipes, *L["circ_s"]) is None and find(pipes, *L["circ_r"]) is None and find(pipes, *L["cool_s"]) is not None and find(pipes, *L["cool_r"]) is not None)
    pg = Page(browser, "heating", extra={"sensor.pv": {"entity_id": "sensor.pv", "state": "2000", "attributes": {"unit_of_measurement": "W"}}}, config={"type": "custom:nibe-plant-card", "pv": {"power": "sensor.pv"}})
    pipes = pg.page.evaluate(PIPES); pg.close()
    check("the solar line keeps its own colour (amber)", colour(pipes, (220, 95), (495, 140)) == (AMBER, AMBER), [p for p in pipes if p["a"] == [220, 95]])
    # no hot water circulation pump by default (the plant has none); `tank.circulation: true` draws the loop
    PUMPS = "() => [...window.__card.shadowRoot.querySelectorAll('.npc-pump title')].map(t => t.textContent)"
    CAPS = "() => [...window.__card.shadowRoot.querySelectorAll('.npc-tank > .npc-caption')].map(t => t.textContent)"
    for width in (900, 380):
        lay = "wide" if width == 900 else "phone"
        for sc in ("hotwater", "heating", "idle"):
            pg = Page(browser, sc, width=width); pipes = pg.page.evaluate(PIPES); pumps = pg.page.evaluate(PUMPS); caps = pg.page.evaluate(CAPS); pg.close()
            check(f"{sc}, {lay} layout: no circulation pump and no loop in the tank by default", sorted(pumps) == ["GP1", "GP2"] and not caps and not [p for p in pipes if p["c0"] == RED and p["c1"] == BLUE and p["a"][0] > 700], (pumps, caps))
        pg = Page(browser, "hotwater", width=width, config={"type": "custom:nibe-plant-card", "tank": {"circulation": True}})
        pipes = pg.page.evaluate(PIPES); pumps = pg.page.evaluate(PUMPS); caps = pg.page.evaluate(CAPS); pg.close()
        loop = [p for p in pipes if p["c0"] == RED and p["c1"] == BLUE]
        check(f"tank.circulation: true, {lay} layout: the loop is drawn, with its pump and caption", sorted(pumps) == ["Circulation", "GP1", "GP2"] and caps == ["Hot water"] and len(loop) == 1, (pumps, caps, loop))
        pg = Page(browser, "hotwater", width=width, config={"type": "custom:nibe-plant-card", "tank": {"circulation": "yes"}}); pumps = pg.page.evaluate(PUMPS); pg.close()
        check(f"tank.circulation only counts when it is true, {lay} layout", "Circulation" not in pumps, pumps)
    pg = Page(browser, "hotwater", config={"type": "custom:nibe-plant-card", "tank": {"circulation": True}}); pipes = pg.page.evaluate(PIPES); pg.close()
    loop = [p for p in pipes if p["c0"] == RED and p["c1"] == BLUE]
    check("hot water circulation loop in the tank (opt-in) runs from red (warm) to blue (cold)", len(loop) == 1, loop)
    # ---- the tank is drawn after the KNV Greenwater: insulation, domed hot water vessel above a heating water zone
    TANK = """() => { const r = window.__card.shadowRoot, q = (s) => [...r.querySelectorAll('.npc-tank ' + s)];
        const bb = (e) => { const b = e.getBBox(); return {x: b.x, y: b.y, w: b.width, h: b.height}; };
        const ins = bb(q('.npc-insulation')[0]), jac = bb(q('.npc-jacket')[0]), ves = q('.npc-dhw')[0], vb = bb(ves), fl = q('.npc-flange-ring')[0];
        const left = q('.npc-ports .npc-port').map(e => bb(e)).filter(b => b.x < ins.x + ins.w / 2).map(b => [Math.round(ins.x), Math.round(b.y + b.h / 2)]).sort((a, b) => a[1] - b[1]);
        const title = q('.npc-title')[0];
        return {ins, jac, vb, flange: [Number(fl.getAttribute('cx')), Number(fl.getAttribute('cy'))], domes: (ves.getAttribute('d').match(/Q/g) || []).length,
          counts: {coil: q('.npc-coil').length, necks: q('.npc-necks .npc-port').length, arrows: q('.npc-arrow').length, tubes: q('.npc-tube').length,
                   ports: q('.npc-ports .npc-port').length, sensors: q('.npc-ports .npc-sensor').length, flange: q('.npc-flange').length},
          pills: Object.fromEntries(['BT7', 'BT6'].map(tip => { const g = q('.npc-pill').find(p => p.querySelector('title').textContent === tip), b = bb(g.querySelector('rect')); return [tip, {cy: b.y + b.h / 2, top: b.y, bottom: b.y + b.h}]; })),
          sensorYs: q('.npc-ports .npc-sensor').map(c => Number(c.getAttribute('cy'))).sort((a, b) => a - b),
          vesselStops: [...r.querySelector('svg').querySelectorAll('linearGradient')].find(g => g.id === ves.getAttribute('fill').slice(5, -1)).querySelectorAll('stop').length ? [...[...r.querySelector('svg').querySelectorAll('linearGradient')].find(g => g.id === ves.getAttribute('fill').slice(5, -1)).querySelectorAll('stop')].map(x => x.getAttribute('stop-color')) : [],
          neckLabels: q('.npc-necks text').map(t => t.textContent), leftPorts: left, titleY: title ? Number(title.getAttribute('y')) : null}; }"""
    for width in (900, 380):
        lay = "wide" if width == 900 else "phone"
        pg = Page(browser, "heating", width=width); d = pg.page.evaluate(TANK); pg.close()
        check(f"{lay} layout: the tank is built of insulation, jacket, vessel, 2 necks with arrows, 2 dip tubes, sensors and a flange (no coil)",
              d["counts"] == {"coil": 0, "necks": 2, "arrows": 2, "tubes": 2, "ports": 4, "sensors": 2, "flange": 1}, d["counts"])
        check(f"{lay} layout: the hot water vessel has domed ends", d["domes"] == 4, d["domes"])
        check(f"{lay} layout: the vessel sits inside the jacket and the jacket inside the insulation",
              d["vb"]["x"] > d["jac"]["x"] and d["vb"]["x"] + d["vb"]["w"] < d["jac"]["x"] + d["jac"]["w"] and d["vb"]["y"] >= d["jac"]["y"] and d["jac"]["x"] > d["ins"]["x"], d)
        check(f"{lay} layout: the heating water zone with the flange is below the vessel, which ends well above the jacket bottom",
              d["flange"][1] > d["vb"]["y"] + d["vb"]["h"] and d["jac"]["y"] + d["jac"]["h"] - (d["vb"]["y"] + d["vb"]["h"]) > 35 and abs(d["flange"][0] - (d["ins"]["x"] + d["ins"]["w"] / 2)) < 1, d)
        check(f"{lay} layout: the tank is taller than wide, like the real one", d["ins"]["h"] > 1.4 * d["ins"]["w"], d["ins"])
        vb_bottom = d["vb"]["y"] + d["vb"]["h"]
        check(f"{lay} layout: BT7 is shown inside the hot water vessel", d["vb"]["y"] <= d["pills"]["BT7"]["top"] and d["pills"]["BT7"]["bottom"] <= vb_bottom, (d["pills"], d["vb"]))
        check(f"{lay} layout: BT6 is shown in the outer layer (heating water jacket), below the vessel and above the flange",
              d["pills"]["BT6"]["top"] >= vb_bottom - 1 and d["pills"]["BT6"]["bottom"] < d["flange"][1] - 8 and d["pills"]["BT6"]["bottom"] < d["jac"]["y"] + d["jac"]["h"], (d["pills"], d["vb"], d["flange"]))
        check(f"{lay} layout: the BT6 sensor sits at the height of its value, on the jacket wall, and BT7 further up", abs(d["sensorYs"][1] - d["pills"]["BT6"]["cy"]) <= 1 and d["sensorYs"][0] < d["sensorYs"][1] - 40, (d["sensorYs"], d["pills"]))
        port_s, port_r = PORTS[width][4], PORTS[width][5]
        check(f"{lay} layout: the heating water pipes end exactly at the upper (supply) and lower (return) left connections",
              [list(p) for p in d["leftPorts"]] == [[port_s[0], port_s[1]], [port_r[0], port_r[1]]], (d["leftPorts"], port_s, port_r))
        if width == 380:
            check("phone layout: the tank heading is below the drawing, so the pipes do not cross it", d["titleY"] > d["ins"]["y"] + d["ins"]["h"], (d["titleY"], d["ins"]))
        else:
            check("wide layout: the tank heading is at the top of the panel", d["titleY"] < d["ins"]["y"], (d["titleY"], d["ins"]))
    LANES = """() => [...window.__card.shadowRoot.querySelectorAll('.npc-pipe-group')].filter(g => g.style.display !== 'none').map(g => {
        const p = g.querySelector('.npc-pipe'), n = p.getTotalLength(), a = p.getPointAtLength(0); let min = 1e9;
        for (let l = 0; l <= n; l += 2) min = Math.min(min, p.getPointAtLength(l).x);
        return {a: [Math.round(a.x), Math.round(a.y)], minX: Math.round(min)}; })"""
    pg = Page(browser, "hotwater", width=380); lanes = pg.page.evaluate(LANES); pg.close()
    ret = [p for p in lanes if p["a"] == [66, 868]]; sup = [p for p in lanes if p["a"] == [260, 644] and p["minX"] < 100]
    check("phone layout: the tank's return runs on the outer lane and the supply on the inner one, 12 px or more apart (so they do not cross there)",
          len(ret) == 1 and len(sup) == 1 and ret[0]["minX"] + 12 <= sup[0]["minX"], (ret, sup))

    # ---- crossings: with two consumers on one side of the heat pump one crossing cannot be avoided, but never more,
    # and wherever two visible pipes cross, the lower one is cut open so it reads as a bridge and not as a junction
    CROSSINGS = """() => {
      const root = window.__card.shadowRoot;
      const groups = [...root.querySelectorAll('.npc-pipe-group')].filter(g => g.style.display !== 'none');
      const lines = groups.map(g => { const p = g.querySelector('.npc-pipe'), n = p.getTotalLength(), pts = [];
        for (let l = 0; l <= n; l += 1) { const q = p.getPointAtLength(l); pts.push([q.x, q.y]); }
        const last = p.getPointAtLength(n); pts.push([last.x, last.y]); return pts; });
      const cut = (g, x, y) => { const m = g.getAttribute('mask'); if (!m) return false;
        const mask = root.getElementById ? root.getElementById(m.slice(5, -1)) : root.querySelector('#' + m.slice(5, -1));
        return [...mask.querySelectorAll('rect')].filter(r => r.getAttribute('fill') === '#000').some(r => {
          const rx = +r.getAttribute('x'), ry = +r.getAttribute('y'), rw = +r.getAttribute('width'), rh = +r.getAttribute('height');
          return x >= rx && x <= rx + rw && y >= ry && y <= ry + rh; }); };
      const found = [];
      for (let i = 0; i < lines.length; i++) for (let j = i + 1; j < lines.length; j++) {
        for (let a = 0; a + 1 < lines[i].length; a++) for (let b = 0; b + 1 < lines[j].length; b++) {
          const [p1, p2, p3, p4] = [lines[i][a], lines[i][a + 1], lines[j][b], lines[j][b + 1]];
          const d = (p2[0] - p1[0]) * (p4[1] - p3[1]) - (p2[1] - p1[1]) * (p4[0] - p3[0]);
          if (Math.abs(d) < 1e-9) continue;
          const t = ((p3[0] - p1[0]) * (p4[1] - p3[1]) - (p3[1] - p1[1]) * (p4[0] - p3[0])) / d;
          const u = ((p3[0] - p1[0]) * (p2[1] - p1[1]) - (p3[1] - p1[1]) * (p2[0] - p1[0])) / d;
          if (t < 0 || t > 1 || u < 0 || u > 1) continue;
          const x = p1[0] + t * (p2[0] - p1[0]), y = p1[1] + t * (p2[1] - p1[1]);
          // pipes that join end to end (or in a T) meet at the end of a pipe; that is a junction, not a crossing
          if ([i, j].some(k => [lines[k][0], lines[k][lines[k].length - 1]].some(e => Math.hypot(e[0] - x, e[1] - y) < 1.5))) continue;
          // the same crossing is found in neighbouring segments; keep one per pair of pipes and place
          if (!found.some(f => f.i === i && f.j === j && Math.hypot(f.x - x, f.y - y) < 6))
            found.push({i, j, x: Math.round(x), y: Math.round(y), cut: cut(groups[i], x, y) || cut(groups[j], x, y)});
        } } return found; }"""
    for width, lay in ((900, "wide"), (380, "phone")):
        for sc, over in (("heating", {}), ("hotwater", {}), ("idle", {}), ("cooling", {}), ("cooling", {1799: 40, 1973: 1}), ("boost", {})):
            pg = Page(browser, sc, overrides=over, width=width); cr = pg.page.evaluate(CROSSINGS); pg.close()
            kind = "active cooling" if over else ("passive cooling" if sc == "cooling" else sc)
            # the wide layout drops the circuit's supply lane in passive cooling, so nothing is left to cross; on the
            # phone the tank's return still passes the supply line from the heat pump
            none = sc == "cooling" and not over and width == 900
            check(f"{kind}, {lay} layout: {'the pipes do not cross' if none else 'one crossing at most'}", len(cr) <= (0 if none else 1), cr)
            check(f"{kind}, {lay} layout: every crossing is a bridge (the lower pipe is cut open)", all(c["cut"] for c in cr), cr)
    pg = Page(browser, "heating", width=900); cr = pg.page.evaluate(CROSSINGS); pg.close()
    check("wide layout: the one crossing is where the tank's return passes the supply line to the heating circuit", len(cr) == 1 and (cr[0]["x"], cr[0]["y"]) == (690, 244), cr)
    pg = Page(browser, "heating", width=380); cr = pg.page.evaluate(CROSSINGS); pg.close()
    check("phone layout: the one crossing is where the tank's return passes the supply line, clear of the circulation pump", len(cr) == 1 and (cr[0]["x"], cr[0]["y"]) == (260, 588), cr)
    # the circuit's own pipe has no crossing (the old layout swapped supply and return ports)
    pg = Page(browser, "heating", width=900); sw = pg.page.evaluate("""() => { const r = window.__card.shadowRoot.querySelector('.npc-pipes'); return [...r.querySelectorAll('.npc-pipe-group[mask]')].length; }"""); pg.close()
    check("wide layout: only one pipe is cut open", sw == 1, sw)

    # ---- compressor: a scroll compressor, one spiral wall fixed and an identical one orbiting around it
    SCROLL = r"""async () => {
      const root = window.__card.shadowRoot, comp = root.querySelector('.npc-compressor');
      const fixed = comp.querySelector('.npc-scroll-fixed'), orb = comp.querySelector('.npc-orbit'), moving = comp.querySelector('.npc-scroll-orbit');
      const pts = (p) => [...p.getAttribute('d').matchAll(/(-?[\d.]+) (-?[\d.]+)/g)].map(m => [+m[1], +m[2]]);
      const A = pts(fixed), B = pts(moving), wall = +fixed.getAttribute('stroke-width');
      const radius = parseFloat(getComputedStyle(comp).getPropertyValue('--npc-orbit'));
      // the orbiting wall is the fixed one turned by half a turn
      const half = Math.max(...A.map((p, k) => Math.hypot(-p[0] - B[k][0], -p[1] - B[k][1])));
      const seg = (p, a, b) => { const dx = b[0] - a[0], dy = b[1] - a[1], l = dx * dx + dy * dy;
        const t = l ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l)) : 0; return Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy); };
      const near = (P, Q) => Math.min(...P.map(p => Math.min(...Q.slice(1).map((q, k) => seg(p, Q[k], q)))));
      const gaps = [];
      for (let deg = 0; deg < 360; deg += 30) {
        const v = [radius * Math.cos(deg * Math.PI / 180), radius * Math.sin(deg * Math.PI / 180)];
        const T = B.map(p => [p[0] + v[0], p[1] + v[1]]);
        gaps.push(Math.min(near(A, T), near(T, A)));
      }
      const samples = [];
      for (let i = 0; i < 5; i++) { const m = new DOMMatrix(getComputedStyle(orb).transform);
        samples.push({r: Math.hypot(m.e, m.f), angle: Math.atan2(m.f, m.e), a: m.a, b: m.b}); await new Promise(r => setTimeout(r, 200)); }
      const cs = getComputedStyle(orb);
      return {wall, radius, half, gaps, samples, state: cs.animationPlayState, name: cs.animationName, duration: parseFloat(orb.style.animationDuration), points: A.length,
              impeller: getComputedStyle(root.querySelector('.npc-impeller')).animationName, gas: !!comp.querySelector('.npc-gas'), port: !!comp.querySelector('.npc-discharge')};
    }"""
    pg = Page(browser, "heating"); sc = pg.page.evaluate(SCROLL); pg.close()
    check("compressor: a fixed and an orbiting spiral wall, a gas pressure gradient and a discharge port", sc["points"] > 60 and sc["gas"] and sc["port"], sc["points"])
    check("compressor: the orbiting wall is the fixed one turned by half a turn", sc["half"] < 0.02, sc["half"])
    gap = sc["wall"] + 0.3
    check("compressor: the walls touch at every orbit position and never overlap (spacing = wall + a hair line)", all(gap - 0.12 <= g <= gap + 0.12 for g in sc["gaps"]), (gap, [round(g, 2) for g in sc["gaps"]]))
    check("compressor: the orbit radius is the channel width between the walls (pi * a - wall - hair line)", abs(sc["radius"] - (3.14159265 * 2 - sc["wall"] - 0.3)) < 0.01, sc["radius"])
    check("compressor (running): the orbiting wall runs", sc["state"] == "running" and sc["name"] == "npc-orbit", (sc["state"], sc["name"]))
    check("compressor (running): the wall moves on a circle of the orbit radius without turning", all(abs(x["r"] - sc["radius"]) < 0.12 and abs(x["a"] - 1) < 1e-6 and abs(x["b"]) < 1e-6 for x in sc["samples"]), sc["samples"])
    import math
    turn = [(sc["samples"][k + 1]["angle"] - sc["samples"][k]["angle"] + math.pi) % (2 * math.pi) - math.pi for k in range(4)]
    check("compressor (running): the orbit turns against the winding of the spiral, which is the direction that compresses", all(t < 0 for t in turn), turn)
    check("compressor (52 Hz): one orbit takes 1.53 s", abs(sc["duration"] - (2.4 - 52 / 60)) < 0.01, sc["duration"])
    pg = Page(browser, "heating", overrides={1799: 90}); sc90 = pg.page.evaluate(SCROLL); pg.close()
    check("compressor: faster at a higher frequency, but never faster than 0.5 s per orbit", sc90["duration"] < sc["duration"] and sc90["duration"] >= 0.5, (sc["duration"], sc90["duration"]))
    pg = Page(browser, "idle"); sci = pg.page.evaluate(SCROLL); pg.close()
    check("compressor (stopped): the orbiting wall stands still", sci["state"] == "paused" and all(abs(x["angle"] - sci["samples"][0]["angle"]) < 1e-6 for x in sci["samples"]), (sci["state"], sci["samples"]))
    pg = Page(browser, "heating", config={"type": "custom:nibe-plant-card", "animation": False}); sca = pg.page.evaluate(SCROLL); pg.close()
    check("animation: false stops the compressor and the pump impellers as well as the moving pipes", sca["name"] == "none" and sca["impeller"] == "none" and sc["impeller"] != "none", (sca["name"], sca["impeller"], sc["impeller"]))
    pg = Page(browser, "heating"); pg.page.emulate_media(reduced_motion="reduce"); name = pg.page.evaluate("() => getComputedStyle(window.__card.shadowRoot.querySelector('.npc-orbit')).animationName"); pg.close()
    check("prefers-reduced-motion stops the compressor", name == "none", name)
    pg = Page(browser, "heating"); pg.page.evaluate("window.__moreInfo.length = 0")
    pg.page.evaluate("() => window.__card.shadowRoot.querySelector('.npc-compressor').dispatchEvent(new MouseEvent('click', {bubbles: true, composed: true}))")
    check("compressor: clicking it opens the frequency entity", pg.page.evaluate("window.__moreInfo") == [by_point(pg.states, 1799)], pg.page.evaluate("window.__moreInfo")); pg.close()
    stops = []
    for bt6 in (20.0, 60.0):
        pg = Page(browser, "heating", overrides={12: bt6}); stops.append(pg.page.evaluate(TANK)["vesselStops"]); pg.close()
    check("the colour of the hot water vessel follows BT7 only (BT6 measures the heating water), uniform from top to bottom",
          stops[0] == stops[1] and len(stops[0]) == 2 and stops[0][0] == stops[0][1], stops)
    pg = Page(browser, "heating"); en = pg.page.evaluate(TANK); pg.close()
    pg = Page(browser, "heating", lang="de"); de = pg.page.evaluate(TANK); pg.close()
    check("cold water in / hot water out labels: English and German", en["neckLabels"] == ["Cold", "Hot"] and de["neckLabels"] == ["Kalt", "Warm"], (en["neckLabels"], de["neckLabels"]))
    # ground collector: entry cold, exit warm in heating; the other way round in cooling
    GR = "() => { const root = window.__card.shadowRoot; const svg = root.querySelector('svg'); const id = root.querySelector('.npc-collector').style.stroke.match(/#([^\\\"\\)]+)/)[1]; const s = [...svg.querySelectorAll('linearGradient')].find(g => g.id === id).querySelectorAll('stop'); return [s[0].getAttribute('stop-color'), s[1].getAttribute('stop-color')]; }"
    for sc, exp in (("heating", [BLUE, RED]), ("cooling", [RED, BLUE]), ("idle", [BLUE, RED])):
        for width in (900, 380):
            pg = Page(browser, sc, width=width); g = pg.page.evaluate(GR); pg.close()
            check(f"{sc}, width {width}: ground collector runs {'cold to warm' if exp[0] == BLUE else 'warm to cold'}", g == exp, g)
    # emitter and tank jacket
    pg = Page(browser, "heating"); v = pg.page.evaluate("() => window.__card.shadowRoot.querySelector('.npc-emitter').style.getPropertyValue('--npc-emitter-color')"); pg.close()
    check("heating emitter is red", v == RED, v)
    pg = Page(browser, "cooling"); v = pg.page.evaluate("() => window.__card.shadowRoot.querySelector('.npc-emitter').style.getPropertyValue('--npc-emitter-color')"); pg.close()
    check("ceiling cooling emitter is blue", v == BLUE, v)
    pg = Page(browser, "hotwater"); v = pg.page.evaluate("() => window.__card.shadowRoot.querySelector('.npc-jacket').style.fill"); pg.close()
    check("tank jacket turns red while charging", v in ("rgb(239, 68, 68)", RED), v)

    # ---- the wide picture fits the window height, the phone layout may scroll
    FIT = "() => { const r = window.__card.shadowRoot.querySelector('svg').getBoundingClientRect(); return {w: r.width, h: r.height, bottom: window.__card.getBoundingClientRect().bottom}; }"
    pg = Page(browser, "heating", width=1800, height=900); f = pg.page.evaluate(FIT); pg.close()
    check("wide layout, 1800 x 900 window: the picture is scaled to 740 px high (window - 160) and the card ends inside the window",
          abs(f["h"] - 740) <= 1.5 and f["bottom"] <= 900, f)
    pg = Page(browser, "heating", width=1800, height=900, config={"type": "custom:nibe-plant-card", "fit_height": False}); f = pg.page.evaluate(FIT); pg.close()
    check("fit_height: false keeps the full width height (about 1019 px, taller than the window)", abs(f["h"] - f["w"] * 560 / 980) <= 1.5 and f["h"] > 900, f)
    pg = Page(browser, "heating", width=1800, height=500); f = pg.page.evaluate(FIT); pg.close()
    check("wide layout in a very short window: never smaller than 380 px high", abs(f["h"] - 380) <= 1.5, f)
    pg = Page(browser, "heating", width=900, height=1300); f = pg.page.evaluate(FIT); pg.close()
    check("wide layout in a tall window: no change, the height follows the width", abs(f["h"] - f["w"] * 560 / 980) <= 1.5, f)
    pg = Page(browser, "heating", width=380, height=600); f = pg.page.evaluate(FIT); pg.close()
    check("phone layout: not limited by the window height (it scrolls)", abs(f["h"] - f["w"] * 1010 / 480) <= 1.5 and f["h"] > 600, f)
    pg = Page(browser, "heating", width=1800, height=900, config={"type": "custom:nibe-plant-card", "layout": "narrow"}); f = pg.page.evaluate(FIT); pg.close()
    check("layout: narrow on a wide screen is not limited either", f["h"] > 900, f)
    pg = Page(browser, "heating", width=1800, height=900, config={"type": "custom:nibe-plant-card", "fit_height": 0}); f = pg.page.evaluate(FIT); pg.close()
    check("fit_height: only the value false switches it off (0 does not)", abs(f["h"] - 740) <= 1.5, f)

    # ---- clicks open more-info
    pg = Page(browser, "heating")
    pg.page.evaluate("window.__moreInfo.length = 0")
    pg.page.evaluate("""() => { const rs = [...window.__card.shadowRoot.querySelectorAll('.npc-readout')]; rs.find(r => r.querySelector('text').textContent === 'Outside').dispatchEvent(new MouseEvent('click', {bubbles: true, composed: true})); }""")
    got = pg.page.evaluate("window.__moreInfo")
    check("clicking a readout opens more-info of the underlying entity", got == [by_point(pg.states, 4)], (got, by_point(pg.states, 4)))
    pg.page.evaluate("window.__moreInfo.length = 0")
    pg.page.evaluate("""() => { const el = [...window.__card.shadowRoot.querySelectorAll('.npc-readout')].find(r => r.querySelector('text').textContent === 'Outside'); el.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true})); }""")
    check("keyboard Enter on a readout opens more-info too", len(pg.page.evaluate("window.__moreInfo")) == 1)
    check("clickable elements are keyboard focusable buttons", pg.page.evaluate("""() => { const c = window.__card.shadowRoot.querySelectorAll('.npc-clickable'); return c.length > 10 && [...c].every(x => x.getAttribute('tabindex') === '0' && x.getAttribute('role') === 'button'); }"""))
    pg.close()

    # ---- animation switch, config validation, card API
    pg = Page(browser, "heating"); pipes_on = pg.page.evaluate("window.__card.shadowRoot.querySelectorAll('.npc-pipe').length"); pg.close()
    check("pipes exist", pipes_on > 5, pipes_on)
    pg = Page(browser, "heating", config={"type": "custom:nibe-plant-card", "animation": False})
    check("animation: false renders without animation class", pg.page.evaluate("() => !window.__card.shadowRoot.querySelector('svg').classList.contains('npc-animated')")); pg.close()
    pg = Page(browser, "heating")
    api = pg.page.evaluate("""() => ({ stub: customElements.get('nibe-plant-card').getStubConfig(), size: window.__card.getCardSize(), grid: window.__card.getGridOptions(), cc: window.customCards.filter(c => c.type === 'nibe-plant-card').length })""")
    check("getStubConfig / getCardSize / getGridOptions / customCards registered once", api["stub"] == {"type": "custom:nibe-plant-card"} and api["size"] == 6 and api["grid"]["columns"] == 12 and api["cc"] == 1, api)
    bad = pg.page.evaluate("() => { try { window.__card.setConfig(null); return 'no error'; } catch (e) { return e.message; } }")
    check("setConfig(null) throws a readable error", bad == "Invalid configuration", bad)
    code = open(os.path.join(HERE, "..", "nibe-plant-card.js"), encoding="utf-8").read()
    twice = pg.page.evaluate("""(t) => { (0, eval)(t); return window.customCards.filter(c => c.type === 'nibe-plant-card').length; }""", code)
    check("loading the script a second time does not re-register or throw", twice == 1, twice)
    pg.close()

    # ---- robustness: odd states everywhere
    def odd(states, entities):
        for i, (eid, st) in enumerate(states.items()):
            st["state"] = ["", "abc", "NaN", "unavailable", "unknown", "None", "1e999", "-"][i % 8]
            if i % 3 == 0: st["attributes"].pop("raw_value", None)
            if i % 5 == 0: st["attributes"].pop("unit_of_measurement", None)
    for width in (900, 380):
        pg = Page(browser, "heating", width=width, mutate=odd, errors=errs); r = pg.read()
        check(f"garbage states everywhere ({width} px): no errors, still renders", not errs and r["viewBox"] is not None, errs); pg.close()
    pg = Page(browser, "heating", config={"type": "custom:nibe-plant-card", "entities": {"outdoor": None, "supply": ""}, "pv": None, "tank": None, "circuit": None, "heatpump": None}, errors=errs)
    check("null / empty config sections are tolerated", not errs and pg.read()["viewBox"] == "0 0 980 560", errs); pg.close()

    check("no JavaScript errors in any test", not errs, errs)
    browser.close()

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
