"""Layout check: no text on text, no text on a visible pipe, nothing outside the viewBox."""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from playwright.sync_api import sync_playwright
import mockdata

HERE = os.path.dirname(os.path.abspath(__file__))
JS = """
() => {
  const card = window.__card; const root = card.shadowRoot; const svg = root.querySelector('svg');
  const vb = svg.viewBox.baseVal;
  const visible = (el) => { for (let n = el; n && n !== svg; n = n.parentNode) { if (n.style && n.style.display === 'none') return false; const cs = getComputedStyle(n); if (cs.display === 'none') return false; } return true; };
  const box = (el) => { const b = el.getBBox(); const m = el.getCTM(); const s = svg.getCTM(); 
      // map to svg user space
      const rel = s.inverse().multiply(m);
      const pts = [[b.x,b.y],[b.x+b.width,b.y],[b.x,b.y+b.height],[b.x+b.width,b.y+b.height]].map(([x,y]) => { const p = svg.createSVGPoint(); p.x = x; p.y = y; return p.matrixTransform(rel); });
      const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
      return {x: Math.min(...xs), y: Math.min(...ys), w: Math.max(...xs)-Math.min(...xs), h: Math.max(...ys)-Math.min(...ys)}; };
  const texts = [...svg.querySelectorAll('text')].filter(t => t.textContent.trim() && visible(t)).map(t => ({text: t.textContent.trim(), cls: t.getAttribute('class') || '', inNode: Boolean(t.closest('.npc-node')), ...box(t)}));
  const panels = [...svg.querySelectorAll('.npc-panel')].map(r => box(r));
  const pipes = [...svg.querySelectorAll('.npc-pipe, .npc-emitter-line')].filter(visible).map(p => {
    const len = p.getTotalLength(); const pts = []; const m = p.getCTM(); const s = svg.getCTM().inverse().multiply(m);
    for (let l = 0; l <= len; l += 3) { const q = p.getPointAtLength(l); const sp = svg.createSVGPoint(); sp.x = q.x; sp.y = q.y; const t = sp.matrixTransform(s); pts.push([t.x, t.y]); }
    return pts; });
  const rects = [...svg.querySelectorAll('.npc-chip rect, .npc-pill rect, .npc-badge rect')].filter(visible).map(r => ({...box(r)}));
  return {vb: [vb.width, vb.height], texts, pipes, rects, panels};
}
"""
def overlap(a, b, pad=0):
    return min(a['x']+a['w'], b['x']+b['w']) - max(a['x'], b['x']) > pad and min(a['y']+a['h'], b['y']+b['h']) - max(a['y'], b['y']) > pad

def check(shots):
    problems = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for s in shots:
            page = browser.new_page(viewport={"width": s.get("width", 900)+40, "height": 1300})
            page.goto("file://" + os.path.join(HERE, "page.html"))
            page.evaluate(f"document.documentElement.style.setProperty('--w','{s.get('width', 900)}px')")
            ov = dict(mockdata.scenario(s["scenario"])) if s.get("scenario") else {}
            states, entities = mockdata.build(ov)
            for eid, st in (s.get("extra_states") or {}).items(): states[eid] = st
            hass = {"states": states, "entities": entities, "locale": {"language": s.get("lang", "en")}, "language": s.get("lang", "en")}
            page.evaluate("""([cfg, hass]) => { const el = document.createElement('nibe-plant-card'); document.getElementById('holder').appendChild(el); el.setConfig(cfg); el.hass = hass; window.__card = el; }""",
                          [s.get("config") or {"type": "custom:nibe-plant-card"}, hass])
            page.wait_for_timeout(150)
            d = page.evaluate(JS)
            vw, vh = d["vb"]
            texts = d["texts"]
            tag = s["name"]
            for i, a in enumerate(texts):
                if a['x'] < -0.5 or a['y'] < -0.5 or a['x']+a['w'] > vw+0.5 or a['y']+a['h'] > vh+0.5:
                    problems.append((tag, "outside", a['text']))
                for b in texts[i+1:]:
                    if overlap(a, b, 1.0): problems.append((tag, "text-text", a['text'], b['text']))
                for pts in d["pipes"]:
                    hit = [pt for pt in pts if a['x']-2 < pt[0] < a['x']+a['w']+2 and a['y']-1 < pt[1] < a['y']+a['h']+1]
                    if hit and 'pill' not in a['cls']:
                        problems.append((tag, "text-pipe", a['text'], (round(hit[0][0]), round(hit[0][1]))))
                        break
            for a in texts:
                if not a['inNode']: continue
                home = [p for p in d['panels'] if p['x'] - 1 <= a['x'] <= p['x'] + p['w'] and p['y'] - 1 <= a['y'] <= p['y'] + p['h']]
                if not home: problems.append((tag, 'text-outside-panel', a['text'])); continue
                p = home[0]
                if a['x'] + a['w'] > p['x'] + p['w'] - 6 or a['y'] + a['h'] > p['y'] + p['h'] - 2:
                    problems.append((tag, 'text-crosses-panel-edge', a['text'], round(a['x'] + a['w'] - (p['x'] + p['w']), 1)))
            page.close()
        browser.close()
    return problems

if __name__ == "__main__":
    pv = {"extra_states": {"sensor.pv_power": {"entity_id": "sensor.pv_power", "state": "3.48", "attributes": {"unit_of_measurement": "kW"}}}}
    cfg = {"type": "custom:nibe-plant-card", "pv": {"power": "sensor.pv_power", "battery": "sensor.pv_power"}}
    shots = []
    for layout, width in (("wide", 900), ("narrow", 380)):
        for sc in ("idle", "heating", "hotwater", "cooling", "boost", "alarm"):
            for lang in ("en", "de"):
                shots.append({"name": f"{layout}-{sc}-{lang}", "scenario": sc, "width": width, "lang": lang, "config": cfg, **pv})
    for layout, width in (("wide", 900), ("narrow", 380)):
        for typ in ("underfloor", "radiator", "both"):
            for lang in ("en", "de"):
                shots.append({"name": f"{layout}-heating-{typ}-{lang}", "scenario": "heating", "width": width, "lang": lang,
                              "config": {**cfg, "circuit": {"type": typ}}, **pv})
    for layout, width in (("wide", 900), ("narrow", 380)):
        for lang in ("en", "de"):
            shots.append({"name": f"{layout}-hotwater-circulation-{lang}", "scenario": "hotwater", "width": width, "lang": lang,
                          "config": {**cfg, "tank": {"circulation": True}}, **pv})
    probs = check(shots)
    for pr in probs: print(pr)
    print(len(shots), "shots,", len(probs), "problems")
    sys.exit(1 if probs else 0)
