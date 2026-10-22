# Changelog

Newest first. The version in `custom_components/nibe_local_api/manifest.json` and the version of the
card always match. Per-release notes before 0.9.7 were not kept, the entries below list what each
release is known to have changed.

## 0.9.10 - 2026-10-22

* Card: the bottom hot water sensor (BT6) is drawn where it really sits, in the outer
  (heating water) layer of the tank, further down. The colour of the hot water vessel follows
  BT7 only.
* The repository is set up: HACS metadata, CI, release workflow. No change to the integration itself apart
  from the manifest links (`documentation`, `issue_tracker`, `codeowners`).

## 0.9.9 - 2026-10-22

* Card: the tank is redrawn after the KNV Greenwater heating schema: insulation, heating water
  jacket, domed hot water vessel with cold/hot connections, dip tubes and flange. The heat pump's
  supply meets the upper left port and the return leaves the bottom left port.

## 0.9.8 - 2026-10-22

* Card: the hot water circulation loop is only drawn with `tank.circulation: true`, for plants that
  have a circulation pump.

## 0.9.7 - 2026-10-22

* Card: the underfloor heating / ceiling cooling pipe is drawn as one continuous line, like the
  ground loop. The passive cooling pipes join the same ports. Layouts for wide and phone widths.

## 0.9.1 - 0.9.6 - 2026-10-21 to 2026-10-22

* Refinements of the bundled card (layout, colours, readouts).

## 0.9.0 - 2026-10-21

* The integration serves and registers the Lovelace card `nibe-plant-card` itself; no dashboard
  resource is needed.

## 0.8.6 - 2026-10-21

* Firmware 4.14.6: titles that arrive in German are mapped to the English names, and 0 bar on pressure
  points of sensors the model lacks counts as "not connected".

## 0.8.5 - 2026-10-21

* Entities declare the points they depend on, so updates of single points refresh only what they
  need. Error messages are translated. The "Reset alarms" button follows the alarm state. The
  config flow handles unexpected errors. Manifest `integration_type` is `device`.

## 0.8.4 - 2026-10-21

* New diagnostic sensor "Software version" (point 2509, decoded as major.minor).

## 0.8.3 - 2026-10-21

* Value ranges (effective minimum and maximum) and selectable options are checked against what the
  pump reports. Optional fast polling of chosen points and its options page.

## 0.8.2 - 2026-10-21

* First version in this repository: verified `set_mode` writes, AUX function lock, entity writes with
  read-back, coordinator polling and the `set_aux` service.
