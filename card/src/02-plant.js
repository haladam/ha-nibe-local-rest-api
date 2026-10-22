
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
