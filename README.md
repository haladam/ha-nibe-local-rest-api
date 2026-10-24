# NIBE Local REST API for Home Assistant

A Home Assistant integration for NIBE S-series heat pumps (developed on an **S1155** ground source
heat pump) that talks to the pump's **local REST API**: no cloud, no myUplink account. It also
ships an animated Lovelace overview card, `nibe-plant-card`.

* Reads the whole points table of the pump and turns the useful points into sensors, binary
  sensors, numbers, selects, switches, time entities and a "Reset alarms" button. Points that
  are rarely useful or that the pump reports as "not connected" start disabled.
* Writes settings back (with a read-back check), including the "AUX via Modbus" functions
  through the `nibe_local_api.set_aux` service (needs pump software 2.4.3 or later).
* Optional **fast polling** of up to 10 chosen points (for example compressor frequency or
  additional heat steps) between the regular full-table reads.
* Calculates the **COP of the compressor for heating and for hot water**, and the heat output, from the
  pump's own flow, temperature and power readings, leaving out start-up, mode changes and spikes
  (see [COP and heat output](#cop-and-heat-output-calculated)).
* Writes `nibe_local_api_points.csv` into the Home Assistant config folder at start-up: every
  point with its entity name, unit, range and menu path, which is handy for finding things.
* Bundles the **`nibe-plant-card`**, loaded by the integration itself (see [the card](#the-card)).

> **Status:** developed against recorded exports of an S1155 (software 4.13.12 and 4.14.6) and
> run against a stand-in for Home Assistant, not against a live Home Assistant in CI. Other
> models may work but are unverified. Please check each AUX function against NIBE's Modbus
> manual before using it.

## Installation

### HACS (recommended)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/haladam/ha-nibe-local-rest-api`,
   category **Integration**.
2. Install **NIBE Local REST API** and restart Home Assistant.
3. Settings → Devices & services → **Add integration** → *NIBE Local REST API*.

Updates then appear in HACS whenever a new release is published here.

### Manual

Copy `custom_components/nibe_local_api` into the `custom_components` folder of your Home
Assistant configuration (or unpack the `nibe_local_api.zip` of a release into
`custom_components/nibe_local_api`) and restart.

Requires Home Assistant 2024.12 or newer.

## Setup

On the pump enable the local API in menu **7.5.15** and note the username and password you set
there. In Home Assistant enter:

| Field | Value |
|---|---|
| IP address | the pump's address |
| Port | `8443` (HTTPS) |
| Use HTTPS | on |
| Username / Password | from menu 7.5.15 |

The pump uses a self-signed certificate; the integration does not verify it. Connection
settings can be changed later with *Reconfigure*, a rejected login starts the re-authentication
flow.

### Options

*Update interval* (default 30 s) is how often the full points table (about 1 MB) is read.
*Fast-polled points* and *Fast polling interval* (5 s or more) re-read a few chosen points
with one small request each; leave the list empty to switch it off.

## COP and heat output (calculated)

If the pump reports the compressor state (or the "compressor running" flag), the operating priority, the
compressor power input, the heating medium flow and the condenser and return line temperatures
(points 2556 or 1973, 1758, 1801 or 1932, 58, 15 and 10), the integration adds five sensors:

| Sensor | Shows |
| --- | --- |
| **COP heating**, **COP hot water** | COP of the last 15 minutes, only while the pump is producing in that mode and has settled. Unknown while it is idle, starting up or changing mode. |
| **COP heating (24 h)**, **COP hot water (24 h)** | COP over everything that counted in the last 24 hours. It stays while the pump is idle. |
| **Heat output (calculated)** | Heat the compressor delivers right now, in kW; 0 while the compressor is stopped. |

Heat is the flow times 4.15 kJ/(L K) times the temperature rise across the condenser (supply line BT12
minus return line BT3), and the COP is that heat divided by the compressor's power input. BT12 sits
before the internal electric heater, so this is the compressor's own COP: additional heat is on neither
side of the ratio. Every COP is energy over energy (heat summed over electricity summed), never an
average of single readings.

A reading is left out when:

* the compressor is not running, or it started less than **5 minutes** ago (the heat at the condenser
  lags the power while the circuits warm up). The same 5 minutes apply after a defrost and after a
  change between heating and hot water;
* the priority and the hot water reversing valve (QN10) disagree (the valve is moving), or the pump is
  off, heating the pool or cooling;
* something jumped since the previous reading, which is a transition and not a trend: compressor
  frequency by more than 20 Hz, power by more than 40 % (and 300 W), flow by more than 30 %, or the
  temperature rise by more than 3 K. The pump then has to be steady for **2 minutes** again;
* the flow is under 2 L/min, the power under 100 W or the temperature rise outside 1 to 25 K;
* the COP of that single reading is under 0.8 or over 15, which is a sensor spike and not a heat pump
  (a reading from an S1155 at minimum speed on low-temperature underfloor heating came to about 10).
  These are counted in the `rejected_readings` attribute.

The attributes of the COP sensors say why there is, or is not, a number: `status` (`ok`, `idle`,
`settling`, `unsteady`, `other operation`, `out of range`, `implausible`, `defrost` or `no data`), the
seconds left of the waiting time, the minutes that counted in the window and the heat and electricity in
kWh behind the value.

Things to know:

* The tracker is fed once per full table (every 30 s by default), so a short run gives no number. The
  15-minute value appears after 2 minutes of counted data, the 24 h value after 0.2 kWh of electricity.
* The readings are kept in memory only, so the 24 h values start empty after a restart of Home Assistant.
* The compressor's power input is the only electricity in the ratio, so the COP reads higher than one built
  on the pump's own hourly energy log, which also counts standby (about 36 W) and the controller.
* The temperature rise is small (2 to 8 K) and measured by two sensors, so a 0.5 K error is
  already 6 to 12 % of the heat. Read the figures as good for comparing modes, days and settings, not as a
  laboratory COP.
* For kWh of heat, add an *Integral* helper (right Riemann sum, kW, time unit hours) on *Heat output
  (calculated)*. The pump's own heat counters (heating and hot water, compressor only) are also available
  as sensors for comparison.
* Not yet confirmed on a running pump: that point 1801 is the best power reading (1932 is the average),
  and the waiting times. Reports are welcome.

## The card

The integration registers the card by itself, so there is no dashboard resource to add:

```yaml
type: custom:nibe-plant-card
```

It shows the ground loop, the heat pump, the KNV Greenwater tank, the heating/cooling circuit and
PV, with flow animation, red/blue warm/cold colouring and a phone layout. It finds the
integration's entities by NIBE point id, so no entity has to be named. All options are
described in [`custom_components/nibe_local_api/frontend/README.md`](custom_components/nibe_local_api/frontend/README.md).

The card started from [heatpump-flow-card](https://github.com/Xerolux/heatpump-flow-card) by
Xerolux (MIT); see [`THIRD_PARTY_NOTICES.md`](custom_components/nibe_local_api/THIRD_PARTY_NOTICES.md).

## Example: hot water boost before the solar peak

Writing **2** into **More hot water** starts the pump's one-time hot water increase. The pump then sets
*More hot water, minutes remaining* to 120 and counts it down by itself (the card shows it as "Boost"
while it runs). *More hot water* is created disabled, so enable it first (Settings, Devices, the
integration's entities). It is the only one of the two you can write over REST: the pump answers a write to
*minutes remaining* with "bad request", so the length of the boost is the pump's own 120 minutes.

This automation starts the increase 45 minutes before the Solcast peak, once a day, on days with a
worthwhile forecast and a tank that is not already hot. It checks that the pump took it and cancels it
after 2 hours 15 minutes if it is still on. Adjust the entity ids to yours:

```yaml
alias: Hot water boost before solar peak
mode: single
triggers:
  - trigger: time
    at:
      entity_id: sensor.solcast_peak_time_today    # a timestamp sensor
      offset: "-00:45:00"
conditions:
  - condition: template        # once a day, even if the forecast moves the peak later
    value_template: >
      {{ this.attributes.last_triggered is none
         or as_local(this.attributes.last_triggered).date() != now().date() }}
  - condition: numeric_state   # a day with a real forecast
    entity_id: sensor.solcast_forecast_today
    above: 8
  - condition: numeric_state   # tank not already hot
    entity_id: sensor.nibe_s1155_hot_water_top_bt7
    below: 52
  - condition: state           # no increase running
    entity_id: sensor.nibe_s1155_more_hot_water_status
    state: "0"
actions:
  - action: number.set_value
    target:
      entity_id: number.nibe_s1155_more_hot_water
    data:
      value: 2
  - wait_template: "{{ is_state('sensor.nibe_s1155_more_hot_water_status', '1') }}"
    timeout: "00:02:00"        # the status sensor followed within half a minute in a test
    continue_on_timeout: true
  - if:
      - condition: template
        value_template: "{{ not wait.completed }}"
    then:
      - action: persistent_notification.create
        data:
          title: Hot water boost did not start
          message: The pump did not report a running increase two minutes after More hot water was set to 2.
      - stop: "The pump did not start the hot water increase"
  - wait_template: "{{ is_state('sensor.nibe_s1155_more_hot_water_status', '0') }}"
    timeout: "02:15:00"        # the pump ends it itself; this only makes sure it cannot stay on
    continue_on_timeout: true
  - if:
      - condition: template
        value_template: "{{ not wait.completed }}"
    then:
      - action: number.set_value
        target:
          entity_id: number.nibe_s1155_more_hot_water
        data:
          value: 0
```

The pump finishes its current heating period (menu 7.1.10.1, 30 minutes by default) before it switches to
hot water, which is why the boost is started a little ahead of the peak.

## Development

```
custom_components/nibe_local_api/   the integration (what HACS installs)
  frontend/nibe-plant-card.js       the built card: do not edit by hand
card/src/                           card source, concatenated by card/build.sh
card/test/                          card tests (Chromium via Playwright) and layout check
tests/                              integration tests on a small Home Assistant stand-in
  fixtures/                         recorded REST exports of the points table
scripts/                            run_tests.sh, sync_card.sh, release.sh
```

* **Card changes:** edit `card/src/*.js`, then `./scripts/sync_card.sh` (builds the card and
  copies it into the integration). CI fails if the two differ.
* **Tests:** `./scripts/run_tests.sh` runs everything (needs Node and
  `pip install playwright==1.56.0 && python -m playwright install chromium`);
  `./scripts/run_tests.sh --no-card` runs only the integration suites, which need nothing but
  Python 3.13.
* **Version:** the single source is `version` in `manifest.json`; the card takes its version from it.

### Releasing an update

1. Add a `## x.y.z - date` section to `CHANGELOG.md`.
2. `./scripts/release.sh x.y.z` bumps the manifest, rebuilds and syncs the card, runs all tests,
   commits and tags `vx.y.z`.
3. `git push && git push --tags`. The *Release* workflow checks that the tag matches the
   manifest, builds the zip and publishes the GitHub release; HACS offers it as an update.
   (Creating the release by hand under *Releases → Draft a new release* for a new tag works as
   well; the workflow then adds the zip and the notes.)

CI (`.github/workflows`) runs hassfest and the HACS validation, all tests, and the release.
The HACS validation needs the repository to be public and to have a description and topics.

## Licence

[MIT](LICENSE). The card contains code adapted from heatpump-flow-card by Xerolux, also MIT;
its notice is in [`THIRD_PARTY_NOTICES.md`](custom_components/nibe_local_api/THIRD_PARTY_NOTICES.md).
