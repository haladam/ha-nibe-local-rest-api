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

CI (`.github/workflows`) runs hassfest and the HACS validation, all tests, and the release.
The HACS validation needs the repository to be public and to have a description and topics.

## Licence

No licence has been chosen yet. The card contains code adapted from heatpump-flow-card
(MIT, see the notice above).
