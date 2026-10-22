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

const CARD_VERSION = "__VERSION__";
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
