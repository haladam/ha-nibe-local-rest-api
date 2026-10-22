
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
  drawPump(scene, 656, 170, (p) => (p.num("gp1") || 0) > 0 && heatDelivering(p), {
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
  const branchY = 644;
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
    slot: "gp2", label: "GP2", captionAt: "right", caption: (p, h) => percentText(h, p.num("gp2")),
  });
  drawPump(scene, 260, 614, (p) => (p.num("gp1") || 0) > 0 && heatDelivering(p), {
    slot: "gp1", label: "GP1", captionAt: "right", caption: (p, h) => percentText(h, p.num("gp1")),
  });
}

const LAYOUTS = {
  wide: { width: 980, height: 560, build: buildWide },
  narrow: { width: 480, height: 1010, build: buildNarrow },
};
