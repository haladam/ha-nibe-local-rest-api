
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
.npc-source-box { fill: var(--npc-panel-bg); stroke-width: 1.5; }
.npc-source-icon { stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }
.npc-source-value { font-size: 12.5px; font-weight: 600; fill: var(--npc-text); font-variant-numeric: tabular-nums; }
.npc-source-idle .npc-source-value { fill: var(--npc-muted); font-weight: 500; }
.npc-source-idle { opacity: 0.7; }
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
