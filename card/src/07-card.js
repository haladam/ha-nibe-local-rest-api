
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
