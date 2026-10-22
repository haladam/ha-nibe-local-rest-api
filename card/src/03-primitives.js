
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
