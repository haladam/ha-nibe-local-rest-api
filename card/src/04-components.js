
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
