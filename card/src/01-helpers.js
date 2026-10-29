
/* =========================================================================
 * Colours (scale adapted from heatpump-flow-card)
 * ========================================================================= */

const TEMP_STOPS = [
  [-10, [29, 78, 216]],
  [5, [59, 130, 246]],
  [15, [56, 189, 248]],
  [22, [148, 163, 184]],
  [30, [251, 191, 36]],
  [40, [249, 115, 22]],
  [50, [239, 68, 68]],
  [70, [185, 28, 28]],
];

const COLOR_FLOW = "#ef4444";
const COLOR_RETURN = "#3b82f6";
const COLOR_BRINE = "#38bdf8";
const COLOR_PV = "#fbbf24";
const COLOR_GRID = "#a78bfa";
const COLOR_BATTERY = "#34d399";
const COLOR_COLD = "#60a5fa";

/* Flow colours follow one rule: red water is the warm side, blue water the cold side. */
const COLOR_WARM = COLOR_FLOW;
const COLOR_CHILL = COLOR_RETURN;
const toneColor = (tone) => (tone === "warm" ? COLOR_WARM : tone === "cold" ? COLOR_CHILL : null);

const rgb = (t) => `rgb(${t[0]}, ${t[1]}, ${t[2]})`;

function tempColor(celsius) {
  if (celsius === null || celsius === undefined || !Number.isFinite(celsius)) return null;
  const s = TEMP_STOPS;
  if (celsius <= s[0][0]) return rgb(s[0][1]);
  if (celsius >= s[s.length - 1][0]) return rgb(s[s.length - 1][1]);
  for (let i = 0; i < s.length - 1; i++) {
    const [t0, c0] = s[i];
    const [t1, c1] = s[i + 1];
    if (celsius >= t0 && celsius <= t1) {
      const f = (celsius - t0) / (t1 - t0);
      return rgb([0, 1, 2].map((k) => Math.round(c0[k] + (c1[k] - c0[k]) * f)));
    }
  }
  return rgb(s[s.length - 1][1]);
}

/** Text colour for a temperature; near-neutral values keep the theme colour. */
function tempTextColor(celsius) {
  const color = tempColor(celsius);
  if (!color) return null;
  const v = color.match(/\d+/g).map(Number);
  return Math.max(...v) - Math.min(...v) < 70 ? null : color;
}

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

/* =========================================================================
 * SVG primitives
 * ========================================================================= */

function svgEl(tag, attrs, children) {
  const node = document.createElementNS(SVG_NS, tag);
  if (attrs) {
    for (const key of Object.keys(attrs)) {
      const value = attrs[key];
      if (value === undefined || value === null || value === false) continue;
      node.setAttribute(key, String(value));
    }
  }
  if (children) for (const child of children) if (child) node.appendChild(child);
  return node;
}

function svgText(x, y, content, attrs) {
  const node = svgEl("text", { x, y, ...(attrs || {}) });
  node.textContent = content === undefined || content === null ? "" : String(content);
  return node;
}

/** Orthogonal polyline with rounded corners. */
function roundedPath(points, radius) {
  const pts = points.filter((p, i) => i === 0 || p[0] !== points[i - 1][0] || p[1] !== points[i - 1][1]);
  if (pts.length < 2) return "";
  const r = radius === undefined ? 14 : radius;
  let d = `M ${pts[0][0]} ${pts[0][1]}`;
  for (let i = 1; i < pts.length - 1; i++) {
    const [px, py] = pts[i - 1];
    const [cx, cy] = pts[i];
    const [nx, ny] = pts[i + 1];
    const len1 = Math.hypot(cx - px, cy - py);
    const len2 = Math.hypot(nx - cx, ny - cy);
    if (!len1 || !len2) continue;
    const corner = Math.min(r, len1 / 2, len2 / 2);
    d += ` L ${cx - ((cx - px) / len1) * corner} ${cy - ((cy - py) / len1) * corner}`;
    d += ` Q ${cx} ${cy} ${cx + ((nx - cx) / len2) * corner} ${cy + ((ny - cy) / len2) * corner}`;
  }
  const last = pts[pts.length - 1];
  return `${d} L ${last[0]} ${last[1]}`;
}

function fireEvent(node, type, detail) {
  const event = new Event(type, { bubbles: true, cancelable: false, composed: true });
  event.detail = detail;
  node.dispatchEvent(event);
}

/* =========================================================================
 * Texts
 * ========================================================================= */

const TEXTS = {
  en: {
    title: "Heating plant",
    pv: "Photovoltaics",
    power: "Power",
    battery: "Battery",
    gridSource: "Grid",
    batterySource: "Battery",
    gridTip: "Power drawn from the grid",
    batteryTip: "Power drawn from the battery",
    excess: "Excess solar",
    ground: "Ground loop",
    brineIn: "Brine in",
    brineOut: "Brine out",
    heatpump: "Heat pump",
    compressor: "Compressor",
    cop: "COP (1 h)",
    copLive: "COP",
    cop24: "COP (24 h)",
    copTip: {
      live: "calculated from flow and temperature rise, last 15 minutes",
      "24h": "calculated, last 24 hours",
      log: "from the pump's energy log, last hour",
    },
    outside: "Outside",
    heater: "Heater",
    tank: "Hot water",
    start: "Start",
    charging: "Charging",
    stop: "Stop",
    boost: "Boost",
    circ: "Circulation",
    coldIn: "Cold",
    hotOut: "Hot",
    circuit: "Heating circuit",
    underfloor: "Underfloor heating",
    radiator: "Radiators",
    both: "Radiators & underfloor",
    flow: "Flow",
    ret: "Return",
    target: "Target",
    dm: "Degree min.",
    passive: "Passive cooling",
    active: "Active cooling",
    ceiling: "Ceiling cooling",
    alarm: "Alarm",
    modes: { off: "Standby", hot_water: "Hot water", heating: "Heating", pool: "Pool", cooling: "Cooling" },
    jacket: "jacket",
    hotWaterTank: "hot water",
    unavailable: "not available",
  },
  de: {
    title: "Heizungsanlage",
    pv: "Photovoltaik",
    power: "Leistung",
    battery: "Batterie",
    gridSource: "Netz",
    batterySource: "Batterie",
    gridTip: "Leistung aus dem Netz",
    batteryTip: "Leistung aus der Batterie",
    excess: "PV-Überschuss",
    ground: "Erdsonde",
    brineIn: "Sole ein",
    brineOut: "Sole aus",
    heatpump: "Wärmepumpe",
    compressor: "Verdichter",
    cop: "COP (1 h)",
    copLive: "COP",
    cop24: "COP (24 h)",
    copTip: {
      live: "berechnet aus Durchfluss und Temperaturdifferenz, letzte 15 Minuten",
      "24h": "berechnet, letzte 24 Stunden",
      log: "aus dem Energieprotokoll der Pumpe, letzte Stunde",
    },
    outside: "Außen",
    heater: "Heizstab",
    tank: "Warmwasser",
    start: "Start",
    charging: "Ladung",
    stop: "Stopp",
    boost: "Boost",
    circ: "Zirkulation",
    coldIn: "Kalt",
    hotOut: "Warm",
    circuit: "Heizkreis",
    underfloor: "Fußbodenheizung",
    radiator: "Heizkörper",
    both: "Heizkörper & Fußboden",
    flow: "Vorlauf",
    ret: "Rücklauf",
    target: "Soll",
    dm: "Gradminuten",
    passive: "Passive Kühlung",
    active: "Aktive Kühlung",
    ceiling: "Deckenkühlung",
    alarm: "Alarm",
    modes: { off: "Bereit", hot_water: "Warmwasser", heating: "Heizen", pool: "Pool", cooling: "Kühlen" },
    jacket: "Mantel",
    hotWaterTank: "Warmwasser",
    unavailable: "nicht verfügbar",
  },
};

function textsFor(hass) {
  const lang = String((hass && (hass.locale && hass.locale.language || hass.language)) || "en").toLowerCase();
  return TEXTS[lang.split("-")[0]] || TEXTS.en;
}
