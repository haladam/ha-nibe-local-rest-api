/*!
 * nibe-plant-card
 * An animated hydraulic overview for a NIBE S1155 ground source heat pump with a
 * Greenwater double-jacket hot water tank: ground loop, heat pump, hot water,
 * underfloor heating circuit, PV and electrical power.
 *
 * Part of the "NIBE Local REST API" Home Assistant integration. The card finds the
 * integration's entities by NIBE point id, so no entity needs to be configured.
 *
 * Derived from heatpump-flow-card (https://github.com/Xerolux/heatpump-flow-card):
 * the colour scale, the animated pipe technique, the pump and panel look and the
 * styles are adapted from it. That project is released under the MIT licence:
 *
 *   MIT License
 *   Copyright (c) 2026 Xerolux
 *
 *   Permission is hereby granted, free of charge, to any person obtaining a copy
 *   of this software and associated documentation files (the "Software"), to deal
 *   in the Software without restriction, including without limitation the rights
 *   to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 *   copies of the Software, and to permit persons to whom the Software is
 *   furnished to do so, subject to the following conditions:
 *
 *   The above copyright notice and this permission notice shall be included in all
 *   copies or substantial portions of the Software.
 *
 *   THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 *   IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 *   FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 *   AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 *   LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 *   OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 *   SOFTWARE.
 */

(() => {
"use strict";

const CARD_VERSION = "0.10.1";
const CARD_TAG = "nibe-plant-card";

if (customElements.get(CARD_TAG)) {
  // loaded twice (integration resource plus a manual one): keep the first copy
  return;
}

console.info(
  `%c NIBE-PLANT-CARD %c v${CARD_VERSION} `,
  "color:#fff;background:#0369a1;font-weight:700;border-radius:3px 0 0 3px;padding:2px 4px",
  "color:#0369a1;background:#e0f2fe;font-weight:700;border-radius:0 3px 3px 0;padding:2px 4px"
);

const SVG_NS = "http://www.w3.org/2000/svg";

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
    excess: "Excess solar",
    ground: "Ground loop",
    brineIn: "Brine in",
    brineOut: "Brine out",
    heatpump: "Heat pump",
    compressor: "Compressor",
    cop: "COP (1 h)",
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
    excess: "PV-Überschuss",
    ground: "Erdsonde",
    brineIn: "Sole ein",
    brineOut: "Sole aus",
    heatpump: "Wärmepumpe",
    compressor: "Verdichter",
    cop: "COP (1 h)",
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

/* =========================================================================
 * Data access: NIBE point ids -> entities
 * ========================================================================= */

/** Slots the drawing uses and the NIBE point each one reads (integration point ids). */
const SLOT_POINTS = {
  outdoor: 4, supply: 8, return: 10, calc_supply: 1708,
  hw_top: 11, hw_charge: 12, brine_in: 13, brine_out: 14,
  compressor_hz: 1799, compressor_state: 2556, compressor_running: 1973,
  power: 22130, compressor_power: 1801, gp1: 1975, gp2: 1977,
  priority: 1758, aux_power: 1756, valve_hw: 2002, circ_pump: 1829,
  cooling_pump: 3149, degree_minutes: 781, alarm: 3375,
  boost_minutes: 4030, boost_status: 1942, demand: 3697, flow_setting: 3976,
  hw_stop_low: 3705, hw_stop_normal: 3704, hw_stop_high: 3703,
  hw_start_low: 3701, hw_start_normal: 3700, hw_start_high: 3699,
  calc_supply_cooling: 2695,
  pv_surplus: 14314, pv_pump: 6002,
  produced_heating: 25154, produced_hw: 25155, produced_cooling: 25157,
  used_heating: 25158, used_hw: 25159, used_cooling: 25161,
  used_aux_heating: 25162, used_aux_hw: 25163,
};

/** Operating priority codes (point 1758). */
const PRIORITY = { 10: "off", 20: "hot_water", 30: "heating", 40: "pool", 60: "cooling" };

const UNAVAILABLE = new Set(["unavailable", "unknown", "none", ""]);

/**
 * Resolves slots to entities and reads their values. A slot is an explicit entity
 * from the card's `entities:` block, otherwise the entity of this integration that
 * carries the slot's NIBE point id in its `point_id` attribute.
 */
class Plant {
  constructor(config) {
    this.config = config || {};
    this.hass = undefined;
    this._index = new Map();
    this._indexKey = undefined;
    this._indexAt = 0;
  }

  setHass(hass) {
    this.hass = hass;
    const stale =
      this._indexKey !== hass.entities ||
      (Date.now() - this._indexAt > 15000 && this._missingSlots());
    if (stale) this._reindex();
  }

  _missingSlots() {
    // reindex only if something we draw could not be resolved
    for (const slot of Object.keys(SLOT_POINTS)) if (!this.entityId(slot)) return true;
    return false;
  }

  _reindex() {
    const hass = this.hass;
    const device = this.config.device;
    const found = new Map();
    for (const entityId of Object.keys(hass.states)) {
      const attrs = hass.states[entityId].attributes;
      if (!attrs || typeof attrs.point_id !== "number" || typeof attrs.nibe_title !== "string") continue;
      if (device && hass.entities && hass.entities[entityId] && hass.entities[entityId].device_id !== device) continue;
      if (!found.has(attrs.point_id)) found.set(attrs.point_id, entityId);
    }
    this._index = found;
    this._indexKey = hass.entities;
    this._indexAt = Date.now();
  }

  entityId(slot) {
    const explicit = this.config.entities && this.config.entities[slot];
    if (explicit) return explicit;
    const point = SLOT_POINTS[slot];
    return point === undefined ? undefined : this._index.get(point);
  }

  stateObj(slot) {
    const id = this.entityId(slot);
    return id && this.hass ? this.hass.states[id] : undefined;
  }

  _missing(st) {
    return !st || UNAVAILABLE.has(String(st.state).toLowerCase());
  }

  /** Numeric state, or null. */
  num(slot) {
    const st = this.stateObj(slot);
    if (this._missing(st)) return null;
    const v = parseFloat(st.state);
    return Number.isFinite(v) ? v : null;
  }

  /** Raw register value of enum style sensors (the integration's `raw_value` attribute). */
  raw(slot) {
    const st = this.stateObj(slot);
    if (this._missing(st)) return null;
    const a = st.attributes && st.attributes.raw_value;
    if (typeof a === "number" && Number.isFinite(a)) return a;
    const v = parseFloat(st.state);
    return Number.isFinite(v) ? v : null;
  }

  /** On/off for binary sensors, switches and 0/1 sensors; null when unknown. */
  on(slot) {
    const st = this.stateObj(slot);
    if (this._missing(st)) return null;
    const s = String(st.state).toLowerCase();
    if (s === "on" || s === "true") return true;
    if (s === "off" || s === "false") return false;
    const raw = this.raw(slot);
    return raw === null ? null : raw > 0;
  }

  unit(slot) {
    const st = this.stateObj(slot);
    return st && st.attributes ? st.attributes.unit_of_measurement || "" : "";
  }

  /** Power in watts, honouring the entity's unit. */
  watts(slot) {
    const v = this.num(slot);
    if (v === null) return null;
    const unit = this.unit(slot);
    return unit === "kW" ? v * 1000 : unit === "MW" ? v * 1e6 : v;
  }

  /** Any slot or explicit entity id used for the PV block. */
  pvEntity(key) {
    const pv = this.config.pv || {};
    return pv[key];
  }

  pvState(key) {
    const id = this.pvEntity(key);
    return id && this.hass ? this.hass.states[id] : undefined;
  }

  pvNum(key) {
    const st = this.pvState(key);
    if (this._missing(st)) return null;
    const v = parseFloat(st.state);
    return Number.isFinite(v) ? v : null;
  }

  pvWatts(key) {
    const v = this.pvNum(key);
    if (v === null) return null;
    const unit = (this.pvState(key).attributes || {}).unit_of_measurement;
    return unit === "kW" ? v * 1000 : unit === "MW" ? v * 1e6 : v;
  }

  /** Signature of everything the drawing reads, to skip redraws that change nothing. */
  signature() {
    const parts = [];
    for (const slot of Object.keys(SLOT_POINTS)) {
      const st = this.stateObj(slot);
      parts.push(st ? `${st.state}|${st.attributes && st.attributes.raw_value}` : "-");
    }
    for (const key of ["power", "battery", "grid"]) {
      const st = this.pvState(key);
      parts.push(st ? st.state : "-");
    }
    return parts.join("\u0001");
  }

  /* ---- derived values ------------------------------------------------- */

  priority() {
    const raw = this.raw("priority");
    return raw === null ? null : PRIORITY[raw] || null;
  }

  compressorRunning() {
    const flag = this.on("compressor_running");
    if (flag !== null) return flag;
    const hz = this.num("compressor_hz");
    if (hz !== null) return hz > 0;
    const state = this.raw("compressor_state");
    return state === null ? null : state === 40 || state === 60;
  }

  cooling() {
    return this.priority() === "cooling" || this.on("cooling_pump") === true;
  }

  /** Cooling with the compressor running (active cooling); without it the ground loop does the work. */
  activeCooling() {
    return this.cooling() && this.compressorRunning() === true;
  }

  hotWaterCharging() {
    return this.priority() === "hot_water" || (this.on("valve_hw") === true && this.compressorRunning() === true);
  }

  heating() {
    return this.priority() === "heating";
  }

  /** Start or stop temperature ("start" / "stop") of the selected hot water demand (Small / Medium / Large). */
  hotWaterLimit(kind) {
    const demand = this.raw("demand");
    // Smart control (4) has no fixed temperatures, the pump decides; unknown codes are not guessed
    const size = demand === 0 ? "low" : demand === 1 ? "normal" : demand === 2 ? "high" : null;
    return size ? this.num(`hw_${kind}_${size}`) : null;
  }

  hotWaterStop() {
    return this.hotWaterLimit("stop");
  }

  hotWaterStart() {
    return this.hotWaterLimit("start");
  }

  /** Coefficient of performance of the last hour from the pump's own energy log. */
  cop() {
    const sum = (slots) => {
      let total = 0;
      let seen = false;
      for (const slot of slots) {
        const v = this.num(slot);
        if (v !== null) {
          total += v;
          seen = true;
        }
      }
      return seen ? total : null;
    };
    const produced = sum(["produced_heating", "produced_hw", "produced_cooling"]);
    const used = sum(["used_heating", "used_hw", "used_cooling", "used_aux_heating", "used_aux_hw"]);
    if (produced === null || used === null || used < 0.1) return null;
    // passive cooling uses only pumps: the ratio of the energy log says nothing about it
    if (this.cooling() && !this.activeCooling()) return null;
    return produced / used;
  }

  /** Underfloor, radiator or both, from the pump's flow setting unless configured. */
  emitter() {
    const configured = this.config.circuit && this.config.circuit.type;
    if (configured === "underfloor" || configured === "radiator" || configured === "both") return configured;
    const raw = this.raw("flow_setting");
    return raw === 1 ? "radiator" : raw === 3 ? "both" : "underfloor";
  }

  alarm() {
    const v = this.raw("alarm");
    return v !== null && v > 0 ? v : null;
  }
}

/* ---- number formatting -------------------------------------------------- */

function formatNumber(hass, value, decimals) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "–";
  const lang = hass && hass.locale && hass.locale.language ? hass.locale.language : undefined;
  try {
    return value.toLocaleString(lang, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  } catch (err) {
    return value.toFixed(decimals);
  }
}

function fmt(hass, value, decimals, unit) {
  const text = formatNumber(hass, value, decimals);
  return text === "–" || !unit ? text : `${text} ${unit}`;
}

/* =========================================================================
 * Scene and building blocks
 * ========================================================================= */

let uid = 0;

/**
 * Where one pipe passes under another: the lower pipe is cut open this far to either side of the crossing
 * point along its own direction (the pipes are 8 wide, so 4 of that is the other pipe and the rest is the gap),
 * and a little wider than the pipe across it, so the cut is clean.
 */
const PIPE_GAP = 11;
const PIPE_GAP_SIDE = 8;

class Scene {
  constructor(card, plant, width, height) {
    this.card = card;
    this.plant = plant;
    this.width = width;
    this.height = height;
    this.updaters = [];
    this.svg = svgEl("svg", {
      class: "npc-svg",
      viewBox: `0 0 ${width} ${height}`,
      role: "img",
    });
    this.defs = svgEl("defs");
    this.panelLayer = svgEl("g", { class: "npc-panels" });
    this.pipeLayer = svgEl("g", { class: "npc-pipes" });
    this.root = svgEl("g", { class: "npc-nodes" });
    this.svg.append(this.defs, this.panelLayer, this.pipeLayer, this.root);
  }

  add(fn) {
    this.updaters.push(fn);
  }

  update() {
    for (const fn of this.updaters) fn(this.plant, this.plant.hass);
  }

  get t() {
    return textsFor(this.plant.hass);
  }
}

/** Makes an SVG node open the more-info dialog of a slot's entity. */
function attachMoreInfo(scene, node, slotOrEntity) {
  node.classList.add("npc-clickable");
  node.setAttribute("tabindex", "0");
  node.setAttribute("role", "button");
  const open = () => {
    const key = typeof slotOrEntity === "function" ? slotOrEntity(scene.plant) : slotOrEntity;
    const id = scene.plant.entityId(key) || (String(key).includes(".") ? key : undefined);
    if (id) fireEvent(scene.card, "hass-more-info", { entityId: id });
  };
  node.addEventListener("click", (event) => {
    event.stopPropagation();
    open();
  });
  node.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      open();
    }
  });
}

/** Rounded container with an optional heading. */
function drawPanel(scene, box, title, options) {
  const opts = options || {};
  const group = svgEl("g", { class: `npc-node${opts.className ? ` ${opts.className}` : ""}` });
  scene.panelLayer.appendChild(
    svgEl("rect", { x: box.x, y: box.y, width: box.w, height: box.h, rx: 16, class: "npc-panel" })
  );
  if (title) group.appendChild(svgText(box.x + 14, box.y + 22, title, { class: "npc-title" }));
  scene.root.appendChild(group);
  return group;
}

/** Small label above a value; the value is produced by `read(plant, hass)`. */
function drawReadout(scene, group, x, y, label, read, options) {
  const opts = options || {};
  const anchor = opts.anchor || "start";
  const block = svgEl("g", { class: "npc-readout" });
  const labelNode = svgText(x, y, label, { class: "npc-label", "text-anchor": anchor });
  const valueNode = svgText(x, y + 17, "–", {
    class: opts.strong ? "npc-value npc-value-strong" : "npc-value",
    "text-anchor": anchor,
  });
  block.append(labelNode, valueNode);
  group.appendChild(block);
  if (opts.slot) attachMoreInfo(scene, block, opts.slot);
  scene.add((plant, hass) => {
    const out = read(plant, hass);
    const text = out && typeof out === "object" ? out.text : out;
    valueNode.textContent = text === undefined || text === null ? "–" : text;
    block.classList.toggle("npc-unset", !text || text === "–");
    const color = out && typeof out === "object" ? out.color : null;
    valueNode.style.fill = color || "";
    if (opts.label) labelNode.textContent = opts.label(plant, hass);
  });
  return block;
}

/** Pill shaped value badge that sits on a pipe. */
function drawBadge(scene, x, y, read, options) {
  const opts = options || {};
  const group = svgEl("g", { class: "npc-badge" });
  const rect = svgEl("rect", { x: x - 27, y: y - 11, width: 54, height: 22, rx: 11 });
  const text = svgText(x, y + 4, "–", { "text-anchor": "middle" });
  group.append(rect, text);
  scene.root.appendChild(group);
  if (opts.slot) attachMoreInfo(scene, group, opts.slot);
  scene.add((plant, hass) => {
    const out = read(plant, hass);
    const label = out && out.text ? out.text : "–";
    text.textContent = label;
    const width = Math.max(46, label.length * 6.6 + 16);
    rect.setAttribute("x", String(x - width / 2));
    rect.setAttribute("width", String(width));
    rect.style.fill = (out && out.color) || "";
    group.classList.toggle("npc-badge-plain", !(out && out.color));
    group.classList.toggle("npc-unset", label === "–");
  });
  return group;
}

/**
 * A pipe: coloured base line plus dashes that travel along the path while the medium
 * moves. The path direction is the flow direction.
 *
 * options: points, from(plant) / to(plant) temperatures for the colour gradient,
 * fallback colour, active(plant) -> bool, visible(plant) -> bool, energy (thin dashed),
 * gaps: [[x, y, axis]] where this pipe passes under another one at (x, y) and runs along `axis` ("x" or
 * "y"); it is cut open there, so the crossing reads as a bridge and not as a junction
 */
function drawPipe(scene, options) {
  const d = roundedPath(options.points, options.radius);
  const group = svgEl("g", { class: `npc-pipe-group${options.energy ? " npc-energy" : ""}` });
  const id = `npc-grad-${++uid}`;
  if (options.gaps && options.gaps.length) {
    const xs = options.points.map((p) => p[0]);
    const ys = options.points.map((p) => p[1]);
    const pad = 16;
    const x0 = Math.min(...xs) - pad;
    const y0 = Math.min(...ys) - pad;
    const w = Math.max(...xs) - x0 + pad;
    const h = Math.max(...ys) - y0 + pad;
    // an explicit region: the default one is relative to the bounding box, which has no height for a straight line
    const cuts = options.gaps.map(([gx, gy, axis]) =>
      svgEl("rect", {
        x: axis === "x" ? gx - PIPE_GAP : gx - PIPE_GAP_SIDE,
        y: axis === "x" ? gy - PIPE_GAP_SIDE : gy - PIPE_GAP,
        width: axis === "x" ? PIPE_GAP * 2 : PIPE_GAP_SIDE * 2,
        height: axis === "x" ? PIPE_GAP_SIDE * 2 : PIPE_GAP * 2,
        fill: "#000",
      })
    );
    scene.defs.appendChild(
      svgEl("mask", { id: `${id}-mask`, maskUnits: "userSpaceOnUse", x: x0, y: y0, width: w, height: h }, [
        svgEl("rect", { x: x0, y: y0, width: w, height: h, fill: "#fff" }),
        ...cuts,
      ])
    );
    group.setAttribute("mask", `url(#${id}-mask)`);
  }
  const first = options.points[0];
  const last = options.points[options.points.length - 1];
  const stopA = svgEl("stop", { offset: "0%" });
  const stopB = svgEl("stop", { offset: "100%" });
  scene.defs.appendChild(
    svgEl("linearGradient", { id, gradientUnits: "userSpaceOnUse", x1: first[0], y1: first[1], x2: last[0], y2: last[1] }, [stopA, stopB])
  );
  const base = svgEl("path", { d, class: "npc-pipe", stroke: `url(#${id})`, fill: "none" });
  const dots = svgEl("path", { d, class: "npc-dots", fill: "none" });
  group.append(base, dots);
  scene.pipeLayer.appendChild(group);
  if (options.dots !== false && scene.animation === false) dots.style.display = "none";

  scene.add((plant) => {
    // `tone` ("warm" or "cold") gives the fixed red / blue flow colours; `from` / `to` colour by temperature
    const from = options.tone ? toneColor(options.tone(plant)) : options.from ? tempColor(options.from(plant)) : null;
    const to = options.toneTo ? toneColor(options.toneTo(plant)) : options.to ? tempColor(options.to(plant)) : null;
    const start = from || options.fallback || COLOR_FLOW;
    stopA.setAttribute("stop-color", start);
    stopB.setAttribute("stop-color", to || start);
    const visible = options.visible ? options.visible(plant) : true;
    group.style.display = visible ? "" : "none";
    const running = options.active ? Boolean(options.active(plant)) : true;
    group.classList.toggle("npc-idle", !running);
    dots.style.display = running && scene.animation !== false ? "" : "none";
  });
  return group;
}

function spinner(cx, cy, radius, children, className) {
  const inner = svgEl("g", { class: `npc-spin${className ? ` ${className}` : ""}` }, [
    svgEl("circle", { cx: 0, cy: 0, r: radius, fill: "none", stroke: "none" }),
    ...children,
  ]);
  return { outer: svgEl("g", { transform: `translate(${cx} ${cy})` }, [inner]), inner };
}

/**
 * Circulation pump, drawn like the in-line wet rotor circulators of a heat pump (the S1155 has two of the UPM
 * type): the casing with a flange at each pipe connection, and the impeller as if the motor were cut away,
 * a closed centrifugal impeller with seven backward-curved blades inside its shroud. Backward-curved: going
 * outwards, each blade trails behind the sense of rotation (clockwise).
 * `orient` is "v" when the pipe the pump sits on runs vertically (the default is horizontal).
 */
const PUMP_BLADES = 7;
const PUMP_SWEEP = 55; // degrees a blade bends back between hub and rim

function pumpBlade(index, from, to) {
  let d = "";
  for (let k = 0; k <= 8; k++) {
    const f = k / 8;
    const r = from + (to - from) * f;
    const a = ((index * 360) / PUMP_BLADES - PUMP_SWEEP * f) * (Math.PI / 180);
    d += `${k ? " L" : "M"} ${(r * Math.cos(a)).toFixed(2)} ${(r * Math.sin(a)).toFixed(2)}`;
  }
  return svgEl("path", { class: "npc-blade", d });
}

function drawPump(scene, cx, cy, running, options) {
  const opts = options || {};
  const radius = opts.radius || 14;
  const wrap = svgEl("g", { class: "npc-pump" });
  const flange = (side) =>
    svgEl("rect", {
      class: "npc-flange",
      x: side < 0 ? -radius - radius * 0.25 : radius - radius * 0.04,
      y: -radius * 0.68,
      width: radius * 0.29,
      height: radius * 1.36,
      rx: 1.5,
    });
  const blades = Array.from({ length: PUMP_BLADES }, (_, i) => pumpBlade(i, radius * 0.24, radius * 0.67));
  const hub = svgEl("circle", { r: radius * 0.2, class: "npc-hub" });
  const spin = spinner(0, 0, radius - 3, [...blades, hub], "npc-impeller");
  wrap.appendChild(
    svgEl("g", { transform: `translate(${cx} ${cy})${opts.orient === "v" ? " rotate(90)" : ""}` }, [
      flange(-1),
      flange(1),
      svgEl("circle", { r: radius, class: "npc-pump-body" }),
      svgEl("circle", { r: radius * 0.77, class: "npc-shroud" }),
      spin.outer,
      svgEl("circle", { r: radius * 0.07, class: "npc-shaft" }),
    ])
  );
  const title = svgEl("title");
  title.textContent = opts.label || "";
  wrap.appendChild(title);
  scene.root.appendChild(wrap);
  let caption = null;
  if (opts.caption) {
    caption =
      opts.captionAt === "right"
        ? svgText(cx + radius + 5, cy + 4, "", { class: "npc-caption", "text-anchor": "start" })
        : svgText(cx, cy + radius + 13, "", { class: "npc-caption", "text-anchor": "middle" });
    scene.root.appendChild(caption);
  }
  if (opts.slot) attachMoreInfo(scene, wrap, opts.slot);
  scene.add((plant, hass) => {
    wrap.classList.toggle("npc-running", Boolean(running(plant)));
    if (caption) caption.textContent = opts.caption(plant, hass) || "";
  });
  return wrap;
}

function drawStatusDot(scene, group, cx, cy, resolver) {
  const dot = svgEl("circle", { cx, cy, r: 5, class: "npc-status" });
  group.appendChild(dot);
  scene.add((plant) => {
    dot.setAttribute("class", `npc-status npc-status-${resolver(plant)}`);
  });
  return dot;
}

/** Small rounded label whose text and tone come from `resolve(plant, hass)`. */
function drawChip(scene, group, box, resolve, options) {
  const opts = options || {};
  const chip = svgEl("g", { class: "npc-chip" });
  const rect = svgEl("rect", { x: box.x, y: box.y, width: box.w, height: box.h, rx: box.h / 2 });
  const text = svgText(box.x + box.w / 2, box.y + box.h / 2 + 4, "", { "text-anchor": "middle" });
  chip.append(rect, text);
  group.appendChild(chip);
  if (opts.slot) attachMoreInfo(scene, chip, opts.slot);
  scene.add((plant, hass) => {
    const info = resolve(plant, hass) || {};
    chip.style.display = info.hidden ? "none" : "";
    text.textContent = info.text || "";
    chip.setAttribute("class", `npc-chip${info.mode ? ` npc-mode-${info.mode}` : ""}${opts.slot ? " npc-clickable" : ""}`);
  });
  return chip;
}

/* =========================================================================
 * Components
 * ========================================================================= */

const tempReadout = (slot, decimals = 1) => (plant, hass) => {
  const v = plant.num(slot);
  return v === null ? "–" : { text: fmt(hass, v, decimals, "°C"), color: tempTextColor(v) };
};

const plainReadout = (slot, decimals, unit) => (plant, hass) => fmt(hass, plant.num(slot), decimals, unit);

function wattsText(hass, watts) {
  if (watts === null) return "–";
  return `${formatNumber(hass, Math.round(watts), 0)} W`;
}

function percentText(hass, value) {
  return value === null ? "" : `${formatNumber(hass, Math.round(value), 0)} %`;
}

/** PV panel: photovoltaic power, optional battery, surplus handed to the pump. */
function drawPv(scene, box) {
  const group = drawPanel(scene, box, scene.t.pv, { className: "npc-pv" });
  // module with cells and a sun
  const px = box.x + 16;
  const py = box.y + 40;
  const panel = svgEl("g", { class: "npc-pv-art" });
  panel.appendChild(svgEl("path", { d: `M ${px + 12} ${py} L ${px + 82} ${py} L ${px + 70} ${py + 46} L ${px} ${py + 46} Z`, class: "npc-pv-panel" }));
  for (let i = 1; i < 4; i++) {
    const k = i / 4;
    panel.appendChild(svgEl("line", { x1: px + 12 - 12 * k, y1: py + 46 * k, x2: px + 82 - 12 * k, y2: py + 46 * k, class: "npc-pv-cell" }));
    panel.appendChild(svgEl("line", { x1: px + 12 + 70 * k, y1: py, x2: px + 70 * k, y2: py + 46, class: "npc-pv-cell" }));
  }
  group.appendChild(panel);
  const sun = svgEl("g", { class: "npc-sun" });
  sun.appendChild(svgEl("circle", { r: 11, class: "npc-sun-core" }));
  const rays = svgEl("g", { class: "npc-rays" });
  for (let i = 0; i < 8; i++) {
    rays.appendChild(svgEl("line", { x1: 0, y1: -16, x2: 0, y2: -21, transform: `rotate(${i * 45})` }));
  }
  sun.appendChild(rays);
  group.appendChild(svgEl("g", { transform: `translate(${box.x + box.w - 46} ${box.y + 66})` }, [sun]));
  scene.add((plant) => {
    const w = pvPower(plant);
    group.classList.toggle("npc-running", w !== null && w > 20);
  });

  const col2 = box.x + box.w / 2 + 6;
  drawReadout(scene, group, box.x + 16, box.y + box.h - 38, scene.t.power, (plant, hass) => wattsText(hass, pvPower(plant)), { strong: true });
  drawReadout(
    scene,
    group,
    col2,
    box.y + box.h - 38,
    scene.t.excess,
    (plant, hass) => {
      if (plant.pvEntity("battery")) {
        const v = plant.pvNum("battery");
        return v === null ? "–" : `${formatNumber(hass, Math.round(v), 0)} %`;
      }
      return wattsText(hass, plant.num("pv_surplus") === null ? null : plant.watts("pv_surplus"));
    },
    { slot: "pv_surplus", label: (plant) => (plant.pvEntity("battery") ? scene.t.battery : scene.t.excess) }
  );
  return group;
}

/** PV production in watts: the configured entity, else what the pump itself reports. */
function pvPower(plant) {
  if (plant.pvEntity("power")) return plant.pvWatts("power");
  return plant.watts("pv_pump");
}

/**
 * Ground loop: collector field in the soil. In the wide layout both open ends leave on
 * the right edge, in the narrow layout at the bottom edge (aligned with the brine pipes).
 */
function drawGround(scene, box, orient) {
  const group = drawPanel(scene, box, scene.t.ground, { className: "npc-ground" });
  const rows = 4;
  const step = 15;
  const pts = [];
  let soil;
  if (orient === "bottom") {
    const left = box.x + (box.w - (rows - 1) * step) / 2;
    const top = box.y + 58;
    const bottom = box.y + 118;
    soil = svgEl("rect", { x: box.x + 14, y: box.y + 44, width: box.w - 28, height: 86, rx: 10, class: "npc-soil" });
    pts.push([left, box.y + box.h]);
    for (let i = 0; i < rows; i++) {
      const x = left + i * step;
      if (i % 2 === 0) pts.push([x, bottom], [x, top]);
      else pts.push([x, top], [x, bottom]);
    }
    pts.push([left + (rows - 1) * step, box.y + box.h]);
  } else {
    const x0 = box.x + 30;
    const x1 = box.x + box.w - 26;
    const top = box.y + 65;
    soil = svgEl("rect", { x: box.x + 14, y: box.y + 44, width: box.w - 28, height: 86, rx: 10, class: "npc-soil" });
    pts.push([box.x + box.w, top]);
    for (let i = 0; i < rows; i++) {
      const y = top + i * step;
      if (i % 2 === 0) pts.push([x1, y], [x0, y]);
      else pts.push([x0, y], [x1, y]);
    }
    pts.push([box.x + box.w, top + (rows - 1) * step]);
  }
  group.appendChild(soil);
  const d = roundedPath(pts, 7);
  const loop = svgEl("path", { d, class: "npc-collector", fill: "none" });
  const flow = svgEl("path", { d, class: "npc-dots npc-dots-slim", fill: "none" });
  group.append(loop, flow);
  // the brine enters at the first row (or column) and leaves at the last one: cold to warm when
  // heating, warm to cold when cooling
  const gradId = `npc-ground-${++uid}`;
  const stops = [svgEl("stop", { offset: "0%" }), svgEl("stop", { offset: "100%" })];
  const span = (rows - 1) * step;
  const along =
    orient === "bottom"
      ? { x1: pts[1][0], y1: 0, x2: pts[1][0] + span, y2: 0 }
      : { x1: 0, y1: pts[0][1], x2: 0, y2: pts[0][1] + span };
  scene.defs.appendChild(svgEl("linearGradient", { id: gradId, gradientUnits: "userSpaceOnUse", ...along }, stops));
  loop.style.stroke = `url(#${gradId})`;
  scene.add((plant) => {
    const running = (plant.num("gp2") || 0) > 0;
    flow.style.display = running && scene.animation !== false ? "" : "none";
    const cooling = Boolean(plant.cooling());
    stops[0].setAttribute("stop-color", cooling ? COLOR_WARM : COLOR_CHILL);
    stops[1].setAttribute("stop-color", cooling ? COLOR_CHILL : COLOR_WARM);
  });
  const y = box.y + box.h - 52;
  if (orient === "bottom") {
    const left = box.x + (box.w - (rows - 1) * step) / 2;
    drawReadout(scene, group, box.x + 16, y, scene.t.brineOut, tempReadout("brine_out"), { slot: "brine_out" });
    drawReadout(scene, group, left + (rows - 1) * step + 12, y, scene.t.brineIn, tempReadout("brine_in"), { slot: "brine_in" });
  } else {
    drawReadout(scene, group, box.x + 16, y, scene.t.brineIn, tempReadout("brine_in"), { slot: "brine_in" });
    drawReadout(scene, group, box.x + box.w / 2 + 6, y, scene.t.brineOut, tempReadout("brine_out"), { slot: "brine_out" });
  }
  return group;
}

/**
 * The compressor, drawn as a scroll compressor: two identical spiral walls, one fixed and one that orbits around
 * it without turning. Where the walls touch they close off pockets of gas; as the orbiting wall moves on, the
 * pockets travel towards the middle and shrink, so the gas is squeezed (blue = suction pressure at the rim,
 * red = discharge pressure at the centre port).
 *
 * Both walls are involutes of one circle, so the gap between neighbouring flanks is the same all the way along:
 * the pitch of the spiral is pi * a on either side, split into the wall and the channel. The orbiting wall is
 * shifted by exactly that channel width (less a hair line), which is what makes the walls just touch. The motion
 * is a plain translation along a small circle, run backwards, so the pockets move inwards.
 *
 * (NIBE does not state which compressor type the S1155 has; this is the common one for heat pumps of this class.)
 */
const SCROLL = { a: 2, wall: 3, from: 1.2, to: 14.5, clearance: 0.3, rim: 40 };

function scrollWall(rotation) {
  const { a, from, to } = SCROLL;
  const cos = Math.cos(rotation);
  const sin = Math.sin(rotation);
  let d = "";
  for (let t = from; t < to + 0.06; t += 0.12) {
    const x = a * (Math.cos(t) + t * Math.sin(t));
    const y = a * (Math.sin(t) - t * Math.cos(t));
    d += `${d ? " L" : "M"} ${(x * cos - y * sin).toFixed(2)} ${(x * sin + y * cos).toFixed(2)}`;
  }
  return d;
}

function drawCompressor(scene, cx, cy) {
  const orbit = Math.PI * SCROLL.a - SCROLL.wall - SCROLL.clearance;
  const gasId = `npc-gas-${++uid}`;
  scene.defs.appendChild(
    svgEl("radialGradient", { id: gasId }, [
      svgEl("stop", { offset: "0%", class: "npc-gas-high" }),
      svgEl("stop", { offset: "100%", class: "npc-gas-low" }),
    ])
  );
  const group = svgEl("g", { class: "npc-compressor" });
  group.style.setProperty("--npc-orbit", `${orbit.toFixed(2)}px`);
  const wall = { "stroke-width": SCROLL.wall, fill: "none" };
  const orbiting = svgEl("g", { class: "npc-orbit" }, [svgEl("path", { d: scrollWall(Math.PI), class: "npc-scroll npc-scroll-orbit", ...wall })]);
  group.append(
    svgEl("circle", { cx, cy, r: SCROLL.rim, class: "npc-comp-ring" }),
    svgEl("g", { transform: `translate(${cx} ${cy})` }, [
      svgEl("circle", { r: SCROLL.rim - 7, fill: `url(#${gasId})`, class: "npc-gas" }),
      svgEl("path", { d: scrollWall(0), class: "npc-scroll npc-scroll-fixed", ...wall }),
      orbiting,
      svgEl("circle", { r: 1.7, class: "npc-discharge" }),
    ])
  );
  attachMoreInfo(scene, group, "compressor_hz");
  scene.add((plant) => {
    group.classList.toggle("npc-running", plant.compressorRunning() === true);
    // one turn takes longer than the real thing (50 turns a second) by far; faster when the compressor is
    const hz = plant.num("compressor_hz");
    orbiting.style.animationDuration = `${hz && hz > 0 ? clamp(2.4 - hz / 60, 0.5, 2.4) : 2}s`;
  });
  return group;
}

/** Heat pump: compressor, mode, power, COP, outside temperature, auxiliary heater. */
function drawHeatPump(scene, box, name) {
  const group = drawPanel(scene, box, name, { className: "npc-hp" });
  drawStatusDot(scene, group, box.x + box.w - 18, box.y + 18, (plant) =>
    plant.alarm() !== null ? "alarm" : plant.compressorRunning() === null ? "unknown" : plant.compressorRunning() ? "on" : "off"
  );
  drawChip(
    scene,
    group,
    { x: box.x + 14, y: box.y + 36, w: 112, h: 24 },
    (plant) => {
      const mode = plant.priority();
      if (mode === null) return { text: "–" };
      const active = plant.compressorRunning() === true;
      const text = scene.t.modes[mode] || mode;
      return { text, mode: mode === "off" || !active ? "idle" : mode === "hot_water" ? "water" : mode === "cooling" ? "cool" : mode === "pool" ? "pool" : "heat" };
    },
    { slot: "priority" }
  );
  drawChip(
    scene,
    group,
    { x: box.x + box.w - 14 - 108, y: box.y + 36, w: 108, h: 24 },
    (plant, hass) => {
      const alarm = plant.alarm();
      if (alarm !== null) return { text: `${scene.t.alarm} ${alarm}`, mode: "alarm" };
      const kw = plant.num("aux_power");
      if (kw !== null && kw > 0) return { text: `${scene.t.heater} ${formatNumber(hass, kw, 1)} kW`, mode: "aux" };
      return { hidden: true };
    },
    { slot: "aux_power" }
  );

  // compressor
  const cx = box.x + box.w / 2;
  const cy = box.y + 120;
  const compressor = drawCompressor(scene, cx, cy);
  const label = svgText(cx, cy + 58, scene.t.compressor, { class: "npc-subtitle", "text-anchor": "middle" });
  group.append(compressor, label);

  const y1 = box.y + 218;
  const y2 = box.y + 262;
  const colB = box.x + box.w / 2 + 6;
  drawReadout(scene, group, box.x + 16, y1, scene.t.power, (plant, hass) => wattsText(hass, plant.watts("power")), { strong: true, slot: "power" });
  drawReadout(scene, group, colB, y1, scene.t.compressor, plainReadout("compressor_hz", 0, "Hz"), { slot: "compressor_hz" });
  drawReadout(
    scene,
    group,
    box.x + 16,
    y2,
    scene.t.cop,
    (plant, hass) => {
      const cop = plant.cop();
      return cop === null ? "–" : formatNumber(hass, cop, 1);
    }
  );
  drawReadout(scene, group, colB, y2, scene.t.outside, tempReadout("outdoor"), { slot: "outdoor" });
  return group;
}

/**
 * Where the KNV Greenwater is drawn inside its panel and where the heating water pipes meet it:
 * the supply from the heat pump enters at the upper left, the return leaves at the bottom left.
 */
function tankGeometry(box, compact) {
  const w = 104;
  const h = compact ? 160 : 170;
  // phone layout: two pipes run down the left side of the panel, so the tank sits right of them
  // and the heading goes below the drawing
  const x = compact ? box.x + 56 : Math.round(box.x + (box.w - w) / 2);
  const y = compact ? box.y + 38 : box.y + 68;
  return { x, y, w, h, supplyY: Math.round(y + h * 0.24), returnY: y + h - 14, sensorTopY: Math.round(y + h * 0.1), sensorBottomY: y + h - 52 };
}

/**
 * The Greenwater tank, simplified from the manufacturer's drawing: a stainless hot water vessel with
 * domed ends in the upper part of a heating water jacket, wrapped in insulation. Cold water comes in
 * and hot water leaves at the top; below the vessel is the heating water zone with its round flange.
 */
function drawTank(scene, box, cfg) {
  const t = scene.t;
  const compact = Boolean(cfg.compact);
  const group = drawPanel(scene, box, "", { className: "npc-tank" });
  const subtitle =
    cfg.subtitle !== undefined ? cfg.subtitle : `${cfg.hot_water_l} L ${t.hotWaterTank} · ${cfg.jacket_l} L ${t.jacket}`;
  const headY = compact ? box.y + 216 : box.y + 22;
  if (cfg.name) group.appendChild(svgText(box.x + 14, headY, cfg.name, { class: "npc-title" }));
  group.appendChild(svgText(box.x + 14, headY + (compact ? 16 : 18), subtitle, { class: "npc-subtitle" }));
  drawStatusDot(scene, group, box.x + box.w - 18, headY - 4, (plant) => (plant.hotWaterCharging() ? "on" : plant.num("hw_top") === null ? "unknown" : "off"));

  const g = tankGeometry(box, compact);
  const body = { x: g.x, y: g.y, w: g.w, h: g.h };
  const mid = body.x + body.w / 2;
  const wall = 7; // insulation
  const gap = 4; // heating water between the jacket wall and the vessel
  const id = `npc-tank-${++uid}`;
  const stops = [svgEl("stop", { offset: "0%" }), svgEl("stop", { offset: "100%" })];
  scene.defs.appendChild(svgEl("linearGradient", { id, x1: "0", y1: "0", x2: "0", y2: "1" }, stops));

  const insulation = svgEl("rect", { x: body.x, y: body.y, width: body.w, height: body.h, rx: 16, class: "npc-insulation" });
  const jacket = svgEl("rect", {
    x: body.x + wall, y: body.y + wall, width: body.w - 2 * wall, height: body.h - 2 * wall, rx: 11, class: "npc-jacket",
  });

  // connections of the jacket on both sides (the heating water lines meet the left ones), then the
  // sensor pockets BT7 and BT6 on the left
  const ports = svgEl("g", { class: "npc-ports" });
  for (const y of [g.supplyY, g.returnY]) {
    for (const left of [true, false]) {
      ports.appendChild(
        svgEl("rect", { x: left ? body.x - 3 : body.x + body.w - wall - gap - 1, y: y - 3.5, width: wall + gap + 4, height: 7, rx: 1.5, class: "npc-port" })
      );
    }
  }
  for (const y of [g.sensorTopY, g.sensorBottomY]) {
    ports.appendChild(svgEl("path", { d: `M ${body.x - 3} ${y} L ${body.x + wall + 1} ${y}`, class: "npc-port-line" }));
    ports.appendChild(svgEl("circle", { cx: body.x - 6, cy: y, r: 3.4, class: "npc-sensor" }));
  }

  // hot water vessel: domed top and bottom, in the upper part of the jacket
  const vx0 = body.x + wall + gap;
  const vx1 = body.x + body.w - wall - gap;
  const vTop = body.y + wall + gap;
  const vApex = body.y + body.h - 66;
  const dome = 14;
  const vessel = svgEl("path", {
    d:
      `M ${vx0} ${vTop + dome} Q ${vx0} ${vTop} ${mid} ${vTop} Q ${vx1} ${vTop} ${vx1} ${vTop + dome} ` +
      `L ${vx1} ${vApex - dome} Q ${vx1} ${vApex} ${mid} ${vApex} Q ${vx0} ${vApex} ${vx0} ${vApex - dome} Z`,
    class: "npc-dhw",
    fill: `url(#${id})`,
  });

  // cold water in (long dip tube) and hot water out (short tube) on top, with arrows
  const kwX = Math.round(body.x + body.w * 0.3);
  const wwX = Math.round(body.x + body.w * 0.7);
  const necks = svgEl("g", { class: "npc-necks" });
  for (const x of [kwX, wwX]) {
    necks.appendChild(svgEl("rect", { x: x - 3.5, y: body.y - 10, width: 7, height: vTop - body.y + 12, rx: 1.5, class: "npc-port" }));
  }
  necks.appendChild(svgEl("path", { d: `M ${kwX - 4.5} ${body.y - 18} L ${kwX + 4.5} ${body.y - 18} L ${kwX} ${body.y - 11} Z`, class: "npc-arrow" }));
  necks.appendChild(svgEl("path", { d: `M ${wwX - 4.5} ${body.y - 11} L ${wwX + 4.5} ${body.y - 11} L ${wwX} ${body.y - 18} Z`, class: "npc-arrow" }));
  necks.appendChild(svgText(kwX - 8, body.y - 8, t.coldIn, { class: "npc-caption", "text-anchor": "end" }));
  necks.appendChild(svgText(wwX + 8, body.y - 8, t.hotOut, { class: "npc-caption", "text-anchor": "start" }));
  const tubes = svgEl("g", { class: "npc-tubes" });
  tubes.appendChild(svgEl("path", { d: `M ${kwX} ${vTop} L ${kwX} ${vApex - dome - 6}`, class: "npc-tube" }));
  tubes.appendChild(svgEl("path", { d: `M ${wwX} ${vTop} L ${wwX} ${vTop + 22}`, class: "npc-tube" }));

  // round flange in the heating water zone below the vessel
  const flange = svgEl("g", { class: "npc-flange" });
  const fy = body.y + body.h - 22;
  flange.append(svgEl("circle", { cx: mid, cy: fy, r: 10.5, class: "npc-flange-ring" }), svgEl("circle", { cx: mid, cy: fy, r: 7, class: "npc-flange-dots" }));

  group.append(insulation, jacket, ports, vessel, necks, tubes, flange);

  const pill = (y, slot, tip, jacketSide) => {
    const gp = svgEl("g", { class: "npc-pill" });
    const r = svgEl("rect", { x: vx0 + 6, y: y - 11, width: vx1 - vx0 - 12, height: 22, rx: 11 });
    if (jacketSide) r.setAttribute("class", "npc-pill-jacket");
    const tx = svgText(mid, y + 4, "–", { "text-anchor": "middle" });
    const title = svgEl("title");
    title.textContent = tip;
    gp.append(r, tx, title);
    group.appendChild(gp);
    attachMoreInfo(scene, gp, slot);
    scene.add((plant, hass) => {
      tx.textContent = fmt(hass, plant.num(slot), 1, "°C");
    });
  };
  // BT7 measures the hot water in the vessel; BT6 sits in the heating water of the jacket, low down
  pill(body.y + 34, "hw_top", "BT7");
  pill(g.sensorBottomY, "hw_charge", "BT6", true);

  scene.add((plant) => {
    // the vessel holds the hot water, so its colour is the hot water temperature at the top (BT7);
    // BT6 measures the heating water around it
    const top = tempColor(plant.num("hw_top")) || "#94a3b8";
    stops[0].setAttribute("stop-color", top);
    stops[1].setAttribute("stop-color", top);
    const charging = plant.hotWaterCharging();
    jacket.style.fill = charging ? COLOR_WARM : "";
    jacket.classList.toggle("npc-jacket-on", Boolean(charging));
  });

  // hot water circulation loop on the right, only for a plant that has a circulation pump
  // (`tank.circulation: true`)
  if (cfg.circulation === true) {
    const xr = compact ? body.x + body.w + 28 : box.x + box.w - 30;
    const hotY = body.y + 36;
    const coldY = body.y + body.h - 30;
    drawPipe(scene, {
      points: [[body.x + body.w, hotY], [xr, hotY], [xr, coldY], [body.x + body.w, coldY]],
      tone: () => "warm",
      toneTo: () => "cold",
      fallback: COLOR_FLOW,
      active: (plant) => plant.on("circ_pump") === true,
      radius: 12,
    });
    drawPump(scene, xr, (hotY + coldY) / 2, (plant) => plant.on("circ_pump") === true, { slot: "circ_pump", label: t.circ, radius: 12, orient: "v" });
    group.appendChild(svgText(box.x + box.w - 12, hotY - 12, t.tank, { class: "npc-caption", "text-anchor": "end" }));
  }

  const y = compact ? box.y + 256 : box.y + box.h - 52;
  // the temperatures at which the pump starts and stops charging the hot water (BT7 itself is in the vessel)
  [[box.x + 14, t.start, "hotWaterStart"], [box.x + 92, t.stop, "hotWaterStop"]].forEach(([x, label, read]) =>
    drawReadout(
      scene,
      group,
      x,
      y,
      label,
      (plant, hass) => {
        const v = plant[read]();
        return v === null ? "–" : { text: fmt(hass, v, 1, "°C"), color: tempTextColor(v) };
      },
      { slot: "demand" }
    )
  );
  drawChip(
    scene,
    group,
    compact
      ? { x: box.x + 14, y: box.y + box.h - 34, w: box.w - 28, h: 22 }
      : { x: box.x + box.w - 14 - 84, y: box.y + box.h - 46, w: 84, h: 24 },
    (plant, hass) => {
      const minutes = plant.num("boost_minutes");
      if (minutes !== null && minutes > 0) return { text: `${t.boost} ${formatNumber(hass, minutes, 0)} min`, mode: "boost" };
      const status = plant.raw("boost_status");
      if (status !== null && status > 0) return { text: t.boost, mode: "boost" };
      return { hidden: true };
    },
    { slot: "boost_minutes" }
  );
  return group;
}

/**
 * Heating circuit with its emitter graphic. Like the ground loop, the pipe of the emitter is one
 * continuous line from panel edge to panel edge: it starts where the supply pipe ends (`gate.supply`),
 * winds through the floor, ceiling or radiator and ends where the return pipe begins (`gate.ret`).
 * `gate.edge` is "left" for the wide layout (rows) and "top" for the phone layout (columns).
 */
function drawCircuit(scene, box, cfg, gate) {
  const t = scene.t;
  const tall = gate.edge === "top";
  const group = drawPanel(scene, box, "", { className: "npc-circuit" });
  // phone layout: the pipes come in from above, so the heading sits below the drawing
  const headY = tall ? box.y + 112 : box.y + 22;
  const title = svgText(box.x + 14, headY, "", { class: "npc-title" });
  const sub = svgText(box.x + 14, headY + 18, "", { class: "npc-subtitle" });
  group.append(title, sub);
  drawStatusDot(scene, group, box.x + box.w - 18, headY - 4, (plant) =>
    plant.heating() && plant.compressorRunning() ? "on" : plant.priority() === null ? "unknown" : "off"
  );
  const art = svgEl("g", { class: "npc-emitter" });
  group.appendChild(art);

  // all drawings exist; the pump's flow setting (or `circuit.type`) decides which one shows
  const drawings = {
    underfloor: svgEl("g"),
    radiator: svgEl("g"),
    both: svgEl("g"),
    ceiling: svgEl("g"),
  };
  art.append(drawings.underfloor, drawings.radiator, drawings.both, drawings.ceiling);

  // lanes (rows in the wide layout, columns on the phone) run from the supply port to the return port
  const [sx, sy] = gate.supply;
  const [rx, ry] = gate.ret;
  const count = tall ? 6 : 4;
  const lanes = Array.from({ length: count }, (_, i) => (tall ? sx + ((rx - sx) * i) / (count - 1) : sy + ((ry - sy) * i) / (count - 1)));
  const edge = tall ? box.y : box.x; // where the water crosses the panel edge
  const inner = tall ? box.y + 24 : box.x + 26; // turns near the edge
  const outer = tall ? box.y + 84 : box.x + box.w - 26; // turns at the far end
  const at = (lane, along) => (tall ? [lane, along] : [along, lane]);
  const first = lanes[0];
  const last = lanes[count - 1];
  const lo = Math.min(first, last);
  const hi = Math.max(first, last);
  // zone behind the pipes (floor or ceiling slab); the pipes enter and leave through its edge
  const slab = tall
    ? { x: lo - 16, y: box.y + 10, w: hi - lo + 32, h: outer - box.y - 10 + 14 }
    : { x: box.x + 14, y: lo - 12, w: box.w - 28, h: hi - lo + 24 };

  const flows = [];
  const flowLine = (parent, d) => {
    const id = `npc-emit-${++uid}`;
    const stops = [svgEl("stop", { offset: "0%" }), svgEl("stop", { offset: "100%" })];
    const axis = tall ? { x1: sx, y1: 0, x2: rx, y2: 0 } : { x1: 0, y1: sy, x2: 0, y2: ry };
    scene.defs.appendChild(svgEl("linearGradient", { id, gradientUnits: "userSpaceOnUse", ...axis }, stops));
    // same pipe and the same moving dots as the ground loop
    const line = svgEl("path", { d, class: "npc-emitter-line", fill: "none" });
    const dots = svgEl("path", { d, class: "npc-dots npc-dots-slim", fill: "none" });
    parent.append(line, dots);
    flows.push({ id, line, dots, stops });
  };
  // serpentine: out along the first lane, back along the next one, and so on; the last lane
  // comes back to the edge at the return port
  const coil = (parent) => {
    const pts = [at(first, edge)];
    lanes.forEach((lane, i) => {
      if (i % 2 === 0) pts.push(at(lane, i === 0 ? edge : inner), at(lane, outer));
      else pts.push(at(lane, outer), at(lane, i === count - 1 ? edge : inner));
    });
    flowLine(parent, roundedPath(pts, Math.min(7, Math.abs(lanes[1] - lanes[0]) / 2 - 1)));
  };
  // radiator: the two outer lanes joined at the far end, the fins sit between them
  const rails = (parent) => flowLine(parent, roundedPath([at(first, edge), at(first, outer), at(last, outer), at(last, edge)], 7));
  const fins = (parent, x, y, w, h, faint) => {
    // fins stand across the pipes: columns in the wide layout, bars on the phone
    const n = Math.max(3, Math.floor((tall ? h : w) / 14));
    const gap = (tall ? h : w) / n;
    for (let i = 0; i < n; i++) {
      const r = tall ? { x, y: y + i * gap + 1, width: w, height: gap - 4 } : { x: x + i * gap + 2, y, width: gap - 5, height: h };
      parent.appendChild(svgEl("rect", { ...r, rx: 3, class: faint ? "npc-fin npc-fin-bg" : "npc-fin" }));
    }
  };
  const slabRect = (parent, strip) => {
    parent.appendChild(svgEl("rect", { ...slab, rx: 8, class: "npc-slab" }));
    const s = { x: slab.x, y: strip === "top" ? slab.y : slab.y + slab.h - 6, width: slab.w, height: 6, rx: 3 };
    parent.appendChild(svgEl("rect", { ...s, class: "npc-floor" }));
  };
  const finZone = tall
    ? { x: lo + 8, y: inner + 2, w: hi - lo - 16, h: outer - inner - 6 }
    : { x: box.x + 28, y: lo + 6, w: box.w - 56, h: hi - lo - 12 };

  slabRect(drawings.ceiling, "top");
  coil(drawings.ceiling);
  slabRect(drawings.underfloor, "bottom");
  coil(drawings.underfloor);
  fins(drawings.radiator, finZone.x, finZone.y, finZone.w, finZone.h);
  rails(drawings.radiator);
  // radiator and floor in series: fins on the half next to the supply port, the slab behind the rest
  slabRect(drawings.both, "bottom");
  fins(drawings.both, finZone.x, finZone.y, tall ? finZone.w : finZone.w / 2 - 6, tall ? finZone.h / 2 - 6 : finZone.h, true);
  coil(drawings.both);

  scene.add((plant, hass) => {
    const active = plant.heating() === true && (plant.compressorRunning() === true || (plant.num("aux_power") || 0) > 0);
    const cooling = plant.cooling();
    // water moves when the pump heats, or in cooling when the cooling pump (passive) or the compressor (active) runs
    const flowing = Boolean(active) || (Boolean(cooling) && (plant.on("cooling_pump") === true || plant.activeCooling() === true));
    art.classList.toggle("npc-running", flowing);
    art.style.setProperty("--npc-emitter-color", cooling ? COLOR_CHILL : COLOR_WARM);
    for (const flow of flows) {
      // supply is the warm end when heating and the cold end when cooling
      flow.stops[0].setAttribute("stop-color", cooling ? COLOR_CHILL : COLOR_WARM);
      flow.stops[1].setAttribute("stop-color", cooling ? COLOR_WARM : COLOR_CHILL);
      flow.line.style.stroke = flowing ? `url(#${flow.id})` : "";
      flow.dots.style.display = flowing && scene.animation !== false ? "" : "none";
    }
    // in summer the circuit is the cooling circuit, by default one in the ceiling
    const ceilingCooling = Boolean(cooling) && cfg.cooling_type !== "same";
    const kind = ceilingCooling ? "ceiling" : plant.emitter();
    for (const name of Object.keys(drawings)) drawings[name].style.display = name === kind ? "" : "none";
    title.textContent = ceilingCooling
      ? cfg.cooling_name || t.ceiling
      : cfg.name || (kind === "radiator" ? t.radiator : kind === "both" ? t.both : t.underfloor);
    const dm = plant.num("degree_minutes");
    sub.textContent = cooling ? (plant.activeCooling() ? t.active : t.passive) : dm === null ? "" : `${t.dm} ${formatNumber(hass, dm, 0)}`;
  });

  // target supply temperature: the cooling curve's value while cooling
  const targetSlot = (plant) => (plant.cooling() && plant.num("calc_supply_cooling") !== null ? "calc_supply_cooling" : "calc_supply");
  const targetRead = (plant, hass) => {
    const v = plant.num(targetSlot(plant));
    return v === null ? "–" : { text: fmt(hass, v, 1, "°C"), color: tempTextColor(v) };
  };
  if (box.h > 260) {
    // tall variant (phone layout): the three temperatures stacked
    drawReadout(scene, group, box.x + 14, box.y + 160, t.flow, tempReadout("supply"), { strong: true, slot: "supply" });
    drawReadout(scene, group, box.x + 14, box.y + 210, t.ret, tempReadout("return"), { slot: "return" });
    drawReadout(scene, group, box.x + 14, box.y + 260, t.target, targetRead, { slot: targetSlot });
    return group;
  }
  const y = box.y + box.h - 52;
  const w3 = (box.w - 28) / 3;
  drawReadout(scene, group, box.x + 14, y, t.flow, tempReadout("supply"), { strong: true, slot: "supply" });
  drawReadout(scene, group, box.x + 14 + w3, y, t.ret, tempReadout("return"), { slot: "return" });
  drawReadout(scene, group, box.x + 14 + 2 * w3, y, t.target, targetRead, { slot: targetSlot });
  return group;
}

/** Three way valve (QN10): hot water position tints it. */
function drawValve(scene, cx, cy) {
  const g = svgEl("g", { class: "npc-valve" });
  g.appendChild(svgEl("path", { d: `M ${cx - 11} ${cy - 9} L ${cx} ${cy} L ${cx - 11} ${cy + 9} Z`, class: "npc-valve-body" }));
  g.appendChild(svgEl("path", { d: `M ${cx + 11} ${cy - 9} L ${cx} ${cy} L ${cx + 11} ${cy + 9} Z`, class: "npc-valve-body" }));
  g.appendChild(svgEl("path", { d: `M ${cx - 9} ${cy - 11} L ${cx} ${cy} L ${cx + 9} ${cy - 11} Z`, class: "npc-valve-body" }));
  const title = svgEl("title");
  title.textContent = "QN10";
  g.appendChild(title);
  scene.root.appendChild(g);
  attachMoreInfo(scene, g, "valve_hw");
  scene.add((plant) => g.classList.toggle("npc-running", plant.on("valve_hw") === true));
  return g;
}

/* =========================================================================
 * Styles (adapted from heatpump-flow-card)
 * ========================================================================= */

// sixteen steps round a circle are a close enough circle for an orbit this small (the error is under 0.1 px)
const ORBIT_KEYFRAMES = Array.from({ length: 17 }, (_, k) => {
  const angle = -(k / 16) * 2 * Math.PI;
  const at = (n) => (Math.abs(n) < 1e-9 ? 0 : n).toFixed(4);
  return `${(k / 16) * 100}% { transform: translate(calc(var(--npc-orbit) * ${at(Math.cos(angle))}), calc(var(--npc-orbit) * ${at(Math.sin(angle))})); }`;
}).join("\n");

const CARD_STYLES = `
:host { display: block; }
ha-card { overflow: hidden; padding: 10px 8px 6px; }
ha-card.npc-has-title { padding-top: 4px; }
.npc-header {
  font-size: var(--ha-card-header-font-size, 22px);
  font-weight: 400;
  color: var(--ha-card-header-color, var(--primary-text-color));
  padding: 10px 12px 2px;
  line-height: 1.2;
}
.npc-note { padding: 10px 14px 4px; color: var(--secondary-text-color, #757575); font-size: 13px; }
.npc-svg {
  display: block;
  width: 100%;
  height: auto;
  font-family: var(--paper-font-body1_-_font-family, var(--ha-font-family-body, Roboto, sans-serif));
  --npc-stroke: var(--divider-color, #d5d5d5);
  --npc-text: var(--primary-text-color, #212121);
  --npc-muted: var(--secondary-text-color, #757575);
  --npc-surface: var(--card-background-color, #fff);
  --npc-panel-bg: rgba(127, 127, 127, 0.10);
}
/* wide layout: never taller than the window (room is left for the header and the margins around the card);
   the picture keeps its proportions and is centred. The floor keeps it readable in a very short window. */
ha-card.npc-fit .npc-svg {
  max-height: max(380px, calc(100vh - 160px));
  max-height: max(380px, calc(100dvh - 160px));
}

/* panels ---------------------------------------------------------------- */
.npc-panel { fill: var(--npc-panel-bg); stroke: var(--npc-stroke); stroke-width: 1; }
.npc-title { font-size: 14px; font-weight: 600; fill: var(--npc-text); }
.npc-subtitle { font-size: 11px; fill: var(--npc-muted); }
.npc-caption { font-size: 10px; fill: var(--npc-muted); }
.npc-label { font-size: 9.5px; fill: var(--npc-muted); letter-spacing: 0.4px; text-transform: uppercase; }
.npc-value { font-size: 13.5px; font-weight: 600; fill: var(--npc-text); font-variant-numeric: tabular-nums; }
.npc-value-strong { font-size: 15px; }
.npc-unset { opacity: 0.42; }
.npc-clickable { cursor: pointer; outline: none; }
.npc-clickable:hover { filter: brightness(1.12); }
.npc-clickable:focus-visible { outline: 2px solid var(--primary-color, #03a9f4); outline-offset: 2px; }

/* pipes ----------------------------------------------------------------- */
.npc-pipe {
  stroke-width: 8;
  stroke-linecap: round;
  stroke-linejoin: round;
  transition: stroke 0.8s ease, opacity 0.4s ease;
}
.npc-dots {
  stroke: #ffffff;
  stroke-opacity: 0.9;
  stroke-width: 3.6;
  stroke-linecap: round;
  stroke-dasharray: 0.1 17.9;
  animation: npc-dash var(--npc-dash, 4s) linear infinite;
}
.npc-dots-slim { stroke-width: 2.6; stroke-dasharray: 0.1 13.9; }
.npc-pipe-group.npc-idle .npc-pipe { opacity: 0.32; }
.npc-energy .npc-pipe { stroke-width: 5; stroke-dasharray: 8 5; }
.npc-energy .npc-dots { stroke: #fff8dc; stroke-width: 3; }
@keyframes npc-dash { to { stroke-dashoffset: -180; } }

/* rotating parts -------------------------------------------------------- */
.npc-spin { transform-origin: center; transform-box: fill-box; animation: npc-spin 2s linear infinite; animation-play-state: paused; }
.npc-running .npc-spin { animation-play-state: running; }
@keyframes npc-spin { to { transform: rotate(360deg); } }

/* heat pump ------------------------------------------------------------- */
.npc-comp-ring { fill: var(--npc-surface); stroke: var(--npc-stroke); stroke-width: 1.5; transition: stroke 0.5s ease; }
.npc-gas-high { stop-color: #ef4444; stop-opacity: 0.6; }
.npc-gas-low { stop-color: #3b82f6; stop-opacity: 0.28; }
.npc-gas { opacity: 0.45; transition: opacity 0.5s ease; }
.npc-scroll { stroke-linecap: round; stroke-linejoin: round; transition: stroke 0.5s ease; }
.npc-scroll-fixed, .npc-scroll-orbit { stroke: var(--npc-muted); }
.npc-discharge { fill: var(--npc-muted); transition: fill 0.5s ease; }
.npc-compressor.npc-running .npc-scroll-orbit { stroke: var(--info-color, #39b0e5); }
.npc-compressor.npc-running .npc-comp-ring { stroke: var(--info-color, #39b0e5); }
.npc-compressor.npc-running .npc-gas { opacity: 1; }
.npc-compressor.npc-running .npc-discharge { fill: #ef4444; }
/* the orbiting scroll moves on a small circle without turning, against the sense in which the spiral winds out:
   that is the direction in which the pockets of gas travel inwards and get compressed */
.npc-orbit { animation: npc-orbit 2s linear infinite; animation-play-state: paused; }
.npc-running .npc-orbit { animation-play-state: running; }
@keyframes npc-orbit {
${ORBIT_KEYFRAMES}
}

.npc-status { fill: var(--npc-muted); opacity: 0.4; }
.npc-status-on { fill: var(--success-color, #43a047); opacity: 1; }
.npc-status-unknown { fill: var(--warning-color, #ffa726); opacity: 0.9; }
.npc-status-alarm { fill: var(--error-color, #db4437); opacity: 1; }

.npc-chip rect { fill: rgba(127, 127, 127, 0.18); }
.npc-chip text { font-size: 11px; font-weight: 600; fill: var(--npc-muted); }
.npc-mode-heat rect { fill: rgba(249, 115, 22, 0.2); } .npc-mode-heat text { fill: #f97316; }
.npc-mode-cool rect { fill: rgba(14, 165, 233, 0.2); } .npc-mode-cool text { fill: #0ea5e9; }
.npc-mode-water rect { fill: rgba(245, 158, 11, 0.22); } .npc-mode-water text { fill: #d97706; }
.npc-mode-pool rect { fill: rgba(20, 184, 166, 0.2); } .npc-mode-pool text { fill: #0d9488; }
.npc-mode-boost rect { fill: rgba(245, 158, 11, 0.22); } .npc-mode-boost text { fill: #d97706; }
.npc-mode-aux rect { fill: rgba(249, 115, 22, 0.2); } .npc-mode-aux text { fill: #f97316; }
.npc-mode-alarm rect { fill: rgba(219, 68, 55, 0.2); } .npc-mode-alarm text { fill: var(--error-color, #db4437); }
.npc-mode-idle rect { fill: rgba(127, 127, 127, 0.18); }

/* badges and pills ------------------------------------------------------ */
.npc-badge rect { fill: var(--npc-muted); stroke: var(--npc-surface); stroke-width: 2; transition: fill 0.8s ease; }
.npc-badge text { font-size: 11px; font-weight: 700; fill: #ffffff; }
.npc-badge-plain rect { fill: rgba(127, 127, 127, 0.22); }
.npc-badge-plain text { fill: var(--npc-text); }
.npc-pill rect { fill: rgba(0, 0, 0, 0.5); }
.npc-pill text { font-size: 11px; font-weight: 700; fill: #ffffff; font-variant-numeric: tabular-nums; }

/* tank ------------------------------------------------------------------ */
.npc-insulation { fill: rgba(250, 204, 21, 0.5); stroke: rgba(180, 140, 0, 0.45); stroke-width: 1; }
.npc-jacket { fill: rgba(127, 127, 127, 0.2); stroke: var(--npc-stroke); stroke-width: 1.5; transition: fill 1s ease; }
.npc-jacket-on { fill-opacity: 0.8; }
.npc-dhw { stroke: rgba(0, 0, 0, 0.35); stroke-width: 1.4; }
.npc-port { fill: var(--npc-surface); stroke: var(--npc-muted); stroke-width: 1; }
.npc-port-line { stroke: var(--npc-muted); stroke-width: 1.4; fill: none; }
.npc-sensor { fill: var(--npc-surface); stroke: var(--npc-muted); stroke-width: 1.4; }
.npc-arrow { fill: var(--npc-muted); }
.npc-tube { stroke: rgba(255, 255, 255, 0.85); stroke-width: 2.4; stroke-linecap: round; fill: none; }
.npc-flange-ring { fill: none; stroke: var(--npc-muted); stroke-width: 1.6; }
.npc-flange-dots { fill: none; stroke: var(--npc-muted); stroke-width: 3; stroke-linecap: round; stroke-dasharray: 0.1 5.5; }

/* PV -------------------------------------------------------------------- */
.npc-pv-panel { fill: #1e3a8a; stroke: var(--npc-stroke); }
.npc-pv-cell { stroke: rgba(255, 255, 255, 0.35); stroke-width: 1; }
.npc-sun-core { fill: #fbbf24; }
.npc-rays line { stroke: #fbbf24; stroke-width: 2; stroke-linecap: round; }
.npc-sun { opacity: 0.35; transition: opacity 0.6s ease; transform-origin: center; transform-box: fill-box; }
.npc-running .npc-sun { opacity: 1; animation: npc-pulse 2.8s ease-in-out infinite; }
@keyframes npc-pulse { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.12); } }

/* ground loop ----------------------------------------------------------- */
.npc-soil { fill: rgba(146, 108, 70, 0.20); stroke: none; }
.npc-collector { stroke: var(--npc-muted); stroke-width: 5; stroke-linecap: round; stroke-linejoin: round; transition: stroke 0.8s ease; }

/* emitters -------------------------------------------------------------- */
.npc-fin { fill: #94a3b8; transition: fill 1s ease, opacity 0.5s ease; }
.npc-emitter:not(.npc-running) .npc-fin { opacity: 0.45; }
.npc-running .npc-fin { fill: var(--npc-emitter-color, #ef4444); }
.npc-emitter .npc-fin.npc-fin-bg { opacity: 0.28; }
.npc-floor { fill: rgba(127, 127, 127, 0.35); }
.npc-emitter-line { stroke: var(--npc-muted); stroke-width: 5; stroke-linecap: round; stroke-linejoin: round; transition: stroke 0.8s ease; }
.npc-slab { fill: rgba(127, 127, 127, 0.14); stroke: none; }

/* pump & valve ---------------------------------------------------------- */
.npc-pump-body { fill: var(--npc-surface); stroke: var(--npc-stroke); stroke-width: 1.5; transition: stroke 0.5s ease; }
.npc-shroud { fill: rgba(127, 127, 127, 0.12); stroke: var(--npc-muted); stroke-width: 0.8; transition: fill 0.5s ease, stroke 0.5s ease; }
.npc-blade { fill: none; stroke: var(--npc-muted); stroke-width: 1.7; stroke-linecap: round; transition: stroke 0.5s ease; }
.npc-hub { fill: var(--npc-muted); transition: fill 0.5s ease; }
.npc-shaft { fill: var(--npc-surface); }
.npc-flange { fill: var(--npc-muted); transition: fill 0.5s ease; }
.npc-pump.npc-running .npc-blade { stroke: var(--info-color, #39b0e5); }
.npc-pump.npc-running .npc-hub, .npc-pump.npc-running .npc-flange { fill: var(--info-color, #39b0e5); }
.npc-pump.npc-running .npc-shroud { fill: rgba(57, 176, 229, 0.14); stroke: var(--info-color, #39b0e5); }
.npc-pump.npc-running .npc-pump-body { stroke: var(--info-color, #39b0e5); }
.npc-valve-body { fill: var(--npc-muted); transition: fill 0.5s ease; }
.npc-valve.npc-running .npc-valve-body { fill: #d97706; }

@media (prefers-reduced-motion: reduce) {
  .npc-spin, .npc-orbit, .npc-dots, .npc-sun { animation: none !important; }
}
.npc-svg:not(.npc-animated) .npc-spin, .npc-svg:not(.npc-animated) .npc-orbit { animation: none; }
`;

/* =========================================================================
 * Layouts
 * ========================================================================= */

function hasPv(plant) {
  return Boolean(plant.pvEntity("power") || plant.entityId("pv_surplus") || plant.entityId("pv_pump"));
}

const WARM = "warm";
const COLD = "cold";

/**
 * Colour of each water line: red is the warm side, blue the cold side. Heating and hot water
 * send warm water out and take cold water back; in cooling it is the other way round, and the
 * ground loop swaps as well (it dumps heat into the ground when cooling).
 */
const TONES = {
  supplyTrunk: (p) => (p.hotWaterCharging() ? WARM : p.activeCooling() ? COLD : WARM),
  returnTrunk: (p) => (p.hotWaterCharging() ? COLD : p.activeCooling() ? WARM : COLD),
  circuitSupply: (p) => (p.cooling() ? COLD : WARM),
  circuitReturn: (p) => (p.cooling() ? WARM : COLD),
  toGround: (p) => (p.cooling() ? WARM : COLD),
  fromGround: (p) => (p.cooling() ? COLD : WARM),
  warm: () => WARM,
  cold: () => COLD,
};

const heatDelivering = (plant) => plant.compressorRunning() === true || (plant.num("aux_power") || 0) > 0;

/** Wide layout: ground loop | heat pump | tank and heating circuit. */
function buildWide(scene, cfg) {
  const t = scene.t;
  const pv = { x: 20, y: 20, w: 200, h: 150 };
  const ground = { x: 20, y: 300, w: 200, h: 240 };
  const hp = { x: 360, y: 140, w: 270, h: 300 };
  const tank = { x: 700, y: 20, w: 260, h: 310 };
  const circuit = { x: 700, y: 350, w: 260, h: 190 };

  // pipes first, so the nodes sit on top of them; returns before supplies
  const hotWater = (plant) => plant.hotWaterCharging() === true;
  // the circuit lanes move water when heating, and also in active cooling (compressor running)
  const heating = (plant) => (plant.heating() === true && heatDelivering(plant)) || plant.activeCooling();
  const gp2 = (p) => (p.num("gp2") || 0) > 0;

  // the tank: supply from the heat pump at its upper left port, return from its bottom left port
  const tankAt = tankGeometry(tank, false);
  // the heating circuit: the water enters its panel at the upper end of the left edge and leaves at the lower
  // one. That way the circuit's return does not have to cross its own supply on the way to the heat pump.
  const gate = { edge: "left", supply: [circuit.x, 412], ret: [circuit.x, 457] };
  // passive cooling: the circuit is fed from the ground loop and the heat pump takes no part
  const passive = (p) => p.cooling() && !p.activeCooling();
  const notPassive = (p) => !passive(p);

  // returns: one branch per consumer, joined in a common line into the heat pump
  const returning = (plant) => hotWater(plant) || heating(plant);
  // The tank's return has to get from the right of the circuit's supply lane to the heat pump on its left. With two
  // consumers on the same side of the heat pump one crossing cannot be avoided, so this pipe passes under the lane.
  drawPipe(scene, {
    points: [[tankAt.x, tankAt.returnY], [645, tankAt.returnY], [645, 340]],
    tone: TONES.cold,
    active: hotWater,
    gaps: [[690, tankAt.returnY, "x"]],
  });
  drawPipe(scene, { points: [gate.ret, [645, gate.ret[1]], [645, 340]], tone: TONES.circuitReturn, active: heating, visible: notPassive });
  drawPipe(scene, { points: [[645, 340], [630, 340]], tone: TONES.returnTrunk, active: returning });
  drawPipe(scene, { points: [[630, 170], [690, 170]], tone: TONES.supplyTrunk, active: heatDelivering });
  drawPipe(scene, { points: [[690, 170], [690, tankAt.supplyY], [tankAt.x, tankAt.supplyY]], tone: TONES.warm, active: hotWater });
  drawPipe(scene, { points: [[690, 170], [690, gate.supply[1]], gate.supply], tone: TONES.circuitSupply, active: heating, visible: notPassive });

  drawPipe(scene, { points: [[360, 365], [220, 365]], tone: TONES.toGround, active: gp2 });
  drawPipe(scene, { points: [[220, 410], [360, 410]], tone: TONES.fromGround, active: gp2 });
  // passive cooling: cold ground water runs into the circuit's supply port (the upper one), the warm water
  // leaves at its return port and goes back to the ground loop. The cold line takes the outer lane, so the
  // two do not cross.
  const coolingPump = (p) => p.on("cooling_pump") === true;
  drawPipe(scene, { points: [[220, 497], [672, 497], [672, gate.supply[1]], gate.supply], tone: TONES.cold, visible: passive, active: coolingPump });
  drawPipe(scene, { points: [gate.ret, [690, gate.ret[1]], [690, 520], [220, 520]], tone: TONES.warm, visible: passive, active: coolingPump });

  if (hasPv(scene.plant)) {
    drawPipe(scene, {
      points: [[220, 95], [495, 95], [495, 140]],
      fallback: COLOR_PV,
      energy: true,
      active: (p) => (pvPower(p) || 0) > 20 && (p.watts("power") || 0) > 20,
    });
  }

  if (hasPv(scene.plant)) drawPv(scene, pv);
  drawGround(scene, ground);
  drawHeatPump(scene, hp, cfg.heatpump.name);
  drawTank(scene, tank, cfg.tank);
  drawCircuit(scene, circuit, cfg.circuit, gate);

  drawValve(scene, 690, 170);
  drawPump(scene, 258, 410, (p) => (p.num("gp2") || 0) > 0, {
    slot: "gp2", label: "GP2", caption: (p, h) => percentText(h, p.num("gp2")),
  });
  drawPump(scene, 653, 170, (p) => (p.num("gp1") || 0) > 0 && heatDelivering(p), {
    slot: "gp1", label: "GP1", caption: (p, h) => percentText(h, p.num("gp1")),
  });
  if (cfg.cooling_label !== false) {
    const note = svgText(460, 482, t.passive, { class: "npc-caption", "text-anchor": "middle" });
    scene.root.appendChild(note);
    scene.add((p) => {
      note.style.display = p.cooling() && !p.activeCooling() ? "" : "none";
    });
  }
}

/** Narrow layout for phones: PV and ground loop on top, heat pump, tank and circuit below. */
function buildNarrow(scene, cfg) {
  const t = scene.t;
  const pv = { x: 10, y: 10, w: 205, h: 190 };
  const ground = { x: 225, y: 10, w: 205, h: 190 };
  const hp = { x: 10, y: 270, w: 420, h: 300 };
  const tank = { x: 10, y: 684, w: 205, h: 316 };
  const circuit = { x: 225, y: 684, w: 205, h: 316 };
  const tankAt = tankGeometry(tank, true);
  // the water enters the circuit panel from above, at its top edge
  const gate = { edge: "top", supply: [290, circuit.y], ret: [380, circuit.y] };
  const hotWater = (plant) => plant.hotWaterCharging() === true;
  // the circuit lanes move water when heating, and also in active cooling (compressor running)
  const heating = (plant) => (plant.heating() === true && heatDelivering(plant)) || plant.activeCooling();

  // returns first, supplies on top
  const returning = (plant) => hotWater(plant) || heating(plant);
  // passive cooling: the circuit is fed from the ground loop and the heat pump takes no part
  const passive = (p) => p.cooling() && !p.activeCooling();
  const notPassive = (p) => !passive(p);
  // The two returns join above the supplies' branches, so the only place where the pipes meet is the tank's
  // return passing the supply line from the heat pump (one crossing cannot be avoided with two consumers on the
  // same side of the heat pump); the return passes under it. The circulation pump and the valve sit below.
  const joinY = 588;
  const branchY = 648;
  // the tank's heating water lines run down the left side of its panel to its ports: the supply to the upper
  // one on the inner lane, the return from the lower one on the outer lane
  drawPipe(scene, {
    points: [[tankAt.x, tankAt.returnY], [tank.x + 12, tankAt.returnY], [tank.x + 12, joinY], [340, joinY]],
    tone: TONES.cold,
    active: hotWater,
    gaps: [[260, joinY, "x"]],
  });
  drawPipe(scene, { points: [gate.ret, [gate.ret[0], joinY], [340, joinY]], tone: TONES.circuitReturn, active: heating, visible: notPassive });
  drawPipe(scene, { points: [[340, joinY], [340, 570]], tone: TONES.returnTrunk, active: returning });
  drawPipe(scene, { points: [[260, 570], [260, branchY]], tone: TONES.supplyTrunk, active: heatDelivering });
  drawPipe(scene, { points: [[260, branchY], [tank.x + 30, branchY], [tank.x + 30, tankAt.supplyY], [tankAt.x, tankAt.supplyY]], tone: TONES.warm, active: hotWater });
  drawPipe(scene, { points: [[260, branchY], [gate.supply[0], branchY], gate.supply], tone: TONES.circuitSupply, active: heating, visible: notPassive });

  const gp2 = (p) => (p.num("gp2") || 0) > 0;
  drawPipe(scene, { points: [[305, 270], [305, 200]], tone: TONES.toGround, active: gp2 });
  drawPipe(scene, { points: [[350, 200], [350, 270]], tone: TONES.fromGround, active: gp2 });
  // passive cooling along the right edge: the inner line brings cold water to the circuit's supply port,
  // the outer one takes the warm water from its return port back to the ground loop
  const coolingPump = (p) => p.on("cooling_pump") === true;
  drawPipe(scene, { points: [gate.ret, [gate.ret[0], 674], [462, 674], [462, 130], [430, 130]], tone: TONES.warm, visible: passive, active: coolingPump });
  drawPipe(scene, { points: [[430, 160], [444, 160], [444, 662], [gate.supply[0], 662], gate.supply], tone: TONES.cold, visible: passive, active: coolingPump });
  if (hasPv(scene.plant)) {
    drawPipe(scene, {
      points: [[112, 200], [112, 270]],
      fallback: COLOR_PV,
      energy: true,
      active: (p) => (pvPower(p) || 0) > 20 && (p.watts("power") || 0) > 20,
    });
    drawPv(scene, pv);
  }
  drawGround(scene, ground, "bottom");
  drawHeatPump(scene, hp, cfg.heatpump.name);
  drawTank(scene, tank, { ...cfg.tank, compact: true });
  drawCircuit(scene, circuit, cfg.circuit, gate);

  drawValve(scene, 260, branchY);
  drawPump(scene, 350, 235, (p) => (p.num("gp2") || 0) > 0, {
    slot: "gp2", label: "GP2", orient: "v", captionAt: "right", caption: (p, h) => percentText(h, p.num("gp2")),
  });
  drawPump(scene, 260, 614, (p) => (p.num("gp1") || 0) > 0 && heatDelivering(p), {
    slot: "gp1", label: "GP1", orient: "v", captionAt: "right", caption: (p, h) => percentText(h, p.num("gp1")),
  });
}

const LAYOUTS = {
  wide: { width: 980, height: 560, build: buildWide },
  narrow: { width: 480, height: 1010, build: buildNarrow },
};

/* =========================================================================
 * Configuration
 * ========================================================================= */

function normalizeConfig(raw) {
  const config = raw && typeof raw === "object" ? raw : {};
  const tank = config.tank || {};
  const hot = tank.hot_water_l !== undefined ? tank.hot_water_l : 450;
  const jacket = tank.jacket_l !== undefined ? tank.jacket_l : 300;
  return {
    ...config,
    layout: config.layout === "wide" || config.layout === "narrow" ? config.layout : "auto",
    animation: config.animation !== false,
    fit_height: config.fit_height !== false,
    entities: config.entities && typeof config.entities === "object" ? config.entities : {},
    pv: config.pv && typeof config.pv === "object" ? config.pv : {},
    heatpump: { name: "NIBE S1155", ...(config.heatpump || {}) },
    tank: { name: "Greenwater 450/300", ...tank, hot_water_l: hot, jacket_l: jacket },
    circuit: { ...(config.circuit || {}) },
  };
}

/* =========================================================================
 * The card
 * ========================================================================= */

const NARROW_BELOW = 560;

class NibePlantCard extends HTMLElement {
  static getStubConfig() {
    return { type: "custom:nibe-plant-card" };
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._scene = null;
    this._hass = undefined;
    this._signature = "";
    this._language = undefined;
    this._layout = "wide";
    this._observer = null;
  }

  setConfig(config) {
    if (!config || typeof config !== "object") throw new Error("Invalid configuration");
    this._config = normalizeConfig(config);
    this._plant = new Plant(this._config);
    this._scene = null;
    this._signature = "";
    if (this._hass) {
      this._plant.setHass(this._hass);
      this._render();
    }
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) return;
    this._plant.setHass(hass);
    const language = hass.locale ? hass.locale.language : hass.language;
    if (!this._scene || language !== this._language) {
      this._language = language;
      this._render();
      return;
    }
    const signature = this._plant.signature();
    if (signature === this._signature) return;
    this._signature = signature;
    this._scene.update();
    this._updateNote();
  }

  get hass() {
    return this._hass;
  }

  getCardSize() {
    return this._layout === "narrow" ? 12 : 6;
  }

  getGridOptions() {
    return { columns: 12, rows: 6, min_columns: 6, min_rows: 4 };
  }

  connectedCallback() {
    if (typeof ResizeObserver === "undefined" || this._observer) return;
    this._observer = new ResizeObserver(() => {
      if (!this._config || !this._hass || this._config.layout !== "auto") return;
      const width = this.clientWidth;
      if (!width) return;
      const wanted = width < NARROW_BELOW ? "narrow" : "wide";
      if (wanted !== this._layout && this._scene) this._render();
    });
    this._observer.observe(this);
    if (this._config && this._hass && !this._scene) this._render();
  }

  disconnectedCallback() {
    if (this._observer) {
      this._observer.disconnect();
      this._observer = null;
    }
  }

  _pickLayout() {
    if (this._config.layout !== "auto") return this._config.layout;
    const width = this.clientWidth || 0;
    return width && width < NARROW_BELOW ? "narrow" : "wide";
  }

  _render() {
    const root = this.shadowRoot;
    while (root.firstChild) root.removeChild(root.firstChild);
    root.appendChild(Object.assign(document.createElement("style"), { textContent: CARD_STYLES }));
    const card = document.createElement("ha-card");
    root.appendChild(card);
    if (this._config.title) {
      card.classList.add("npc-has-title");
      const header = document.createElement("div");
      header.className = "npc-header";
      header.textContent = this._config.title;
      card.appendChild(header);
    }
    this._layout = this._pickLayout();
    // the wide picture is scaled to the window height as well, so it fits on one screen without scrolling
    if (this._layout === "wide" && this._config.fit_height) card.classList.add("npc-fit");
    const layout = LAYOUTS[this._layout];
    const scene = new Scene(this, this._plant, layout.width, layout.height);
    scene.animation = this._config.animation;
    scene.svg.classList.toggle("npc-animated", scene.animation !== false);
    layout.build(scene, this._config);
    card.appendChild(scene.svg);
    this._note = document.createElement("div");
    this._note.className = "npc-note";
    card.appendChild(this._note);
    this._scene = scene;
    this._signature = this._plant.signature();
    scene.update();
    this._updateNote();
  }

  _updateNote() {
    if (!this._note) return;
    const found = this._plant.entityId("outdoor") || this._plant.entityId("supply") || this._plant.entityId("power");
    this._note.style.display = found ? "none" : "";
    if (!found) {
      this._note.textContent =
        "No NIBE Local REST API entities found. Check that the integration is set up and the sensors are enabled, " +
        "or map slots with the entities: option.";
    }
  }
}

customElements.define(CARD_TAG, NibePlantCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: CARD_TAG,
  name: "NIBE heating plant",
  description: "Animated overview of a NIBE S1155 ground source heat pump with the Greenwater tank, fed by the NIBE Local REST API integration.",
  preview: false,
});

})();
