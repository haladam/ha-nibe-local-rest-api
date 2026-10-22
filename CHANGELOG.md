# Changelog

Newest first. The version in `custom_components/nibe_local_api/manifest.json` and the version of the
card always match. Per-release notes before 0.9.7 were not kept, the entries below list what each
release is known to have changed.

## 0.9.14 - 2026-10-22

* Card: the circulation pumps look like the real thing. The three-bladed fan is replaced by an in-line
  circulator: casing with a flange at each pipe connection and, as if the motor were cut away, a
  closed impeller with seven backward-curved blades that turns while the pump runs. The pumps are turned
  to match their pipe (vertical on the phone layout and for the hot water circulation pump).
  On the phone the branch point and its valve moved down a little to make room.

## 0.9.13 - 2026-10-22

* Card: below the tank, the readout of the top temperature (BT7) is replaced by the hot water start
  temperature, so "Start" and "Stop" sit next to each other. BT7 was shown twice (in the vessel and
  below the tank); it stays in the vessel. Start follows the selected hot water demand like Stop does
  (points 3699, 3700, 3701 for large, medium, small) and shows a dash with smart control.

## 0.9.12 - 2026-10-22

* Card: fewer crossing pipes. The heating circuit's supply and return ports are swapped (supply
  above, return below), so the circuit's return no longer crosses its own supply line. With the tank
  and the circuit on the same side of the heat pump one crossing cannot be avoided (the tank's
  return has to pass the supply line to the circuit); it is drawn as a bridge, with a gap in the
  lower pipe, so it does not look like a junction. The phone layout is rerouted the same way (two
  crossings down to one). In passive cooling the circuit's heating pipes are no longer drawn, so
  the cooling lines from and to the ground loop cross nothing.
* Card: the compressor is drawn as a scroll compressor, a fixed and an orbiting spiral wall with
  the gas pressure rising from rim to centre, instead of a spinning spiral. The orbiting wall moves
  on a small circle without turning, in the direction in which the pockets of gas are compressed;
  it runs while the compressor runs, faster at a higher frequency. (NIBE does not state the
  compressor type of the S1155; scroll is the usual type for this class.)
* Card: `animation: false` now also stops the compressor and the pump fans, as the documentation
  always said (before, it only hid the moving dots in the pipes).

## 0.9.11 - 2026-10-22

* Card: the wide layout is scaled to fit the window height, so on a wide, short screen the card no
  longer needs scrolling (before, its height simply followed its width). The picture keeps its
  proportions and is centred. `fit_height: false` restores the old behaviour. The phone layout is
  unchanged.

## 0.9.10 - 2026-10-22

* Card: the bottom hot water sensor (BT6) is drawn where it really sits, in the outer
  (heating water) layer of the tank, further down. The colour of the hot water vessel follows
  BT7 only.
* The repository is set up: MIT licence, HACS metadata, CI, release workflow. No change to the integration itself apart
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
