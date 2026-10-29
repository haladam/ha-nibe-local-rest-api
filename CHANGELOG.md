# Changelog

Newest first. The version in `custom_components/nibe_local_api/manifest.json` and the version of the
card always match. Per-release notes before 0.9.7 were not kept, the entries below list what each
release is known to have changed.

## 0.14.0 - 2026-10-29

* Card: new `pv.grid_import` and `pv.battery_discharge` entities (for example the Fronius SolarNet sensors
  `sensor.solarnet_power_grid_import` and `sensor.solarnet_power_battery_discharge`, W or kW). Each source
  is drawn as a chip with its power and its own pipe into the heat pump (violet for the grid, green for the
  battery, amber stays the solar line), so you see where the pump's electricity comes from. The `pv.battery`
  level keeps working as before.
* Card: the PV and ground loop panels of the wide layout are wider, which closes the empty space between
  them and the heat pump, so both sides of the picture match.

## 0.13.1 - 2026-10-24

* "Brine pump dT current" and "Brine pump dT set point value" now have the unit K and the state class
  measurement. They were plain numbers without a unit, so Home Assistant neither drew a graph nor kept
  long-term statistics for them, and every change of the current value (about 360 a day) was listed in the
  Activity feed. They are temperature differences, so the unit is kelvin and not a temperature device class
  (that would convert the value as if it were a temperature). Entity ids are unchanged. These were the only
  enabled sensors with a decimal value and no unit.

## 0.13.0 - 2026-10-24

* The card's COP readout shows the calculated COP now. While the compressor heats or charges hot water it
  shows the COP of that mode over the last 15 minutes ("COP"). Until that value exists (the first minutes
  after a start, a defrost or a change of mode) it shows the COP of the last 24 hours ("COP (24 h)"), on
  standby the 24 h COP of heating, or of hot water if there is none for heating. If nothing has been
  calculated yet it falls back to what the card showed before: "COP (1 h)" from the pump's hourly energy
  log. Hovering over the value says which one it is and tapping it opens that sensor. Cooling still uses the
  energy log, because the calculation does not cover it. The four slots can be named under `entities`
  (`cop_heating`, `cop_hot_water`, `cop_heating_24h`, `cop_hot_water_24h`).
* The four steady-state COP sensors have a `nibe_calc` attribute that the card uses to find them (kept out
  of the database like the other changing attributes). The card comes with the integration, so there is
  nothing to configure.

## 0.12.2 - 2026-10-24

* Fixes the calculated COP, heat output, energy totals and compressor starts staying Unknown on a real Home
  Assistant (0.10.0 to 0.12.1). Only "COP pump counters (lifetime)" worked, because it reads the pump's own
  counters. The cause was a name clash: this integration has a `time.py` (the platform for time-of-day
  settings), and once Home Assistant had loaded it, the name `time` inside `__init__.py` pointed at that file
  instead of Python's clock. The first update worked, every later one failed on `time.monotonic()` and
  switched the calculation off ("COP calculation stopped after an unexpected error" in the log). The tests
  used a stand-in clock, so they could not see it. A new test imports the platform and runs the updates with
  the real clock, and another checks that `__init__.py` never imports a module whose name is also a file of
  the package.
* After updating, restart Home Assistant. The live COP shows a value about 10 minutes after the compressor
  starts, the 24 h COP after about 35 minutes of running, and the season and lifetime COPs after about 75
  minutes of running at minimum speed (0.25 kWh of electricity). Hot water COP follows the first hot water
  run.
* 0.12.0 and 0.12.1 have the same code as 0.11.1 apart from the version number.

## 0.12.1 - 2026-10-24

* Brings the version numbers back in line: nothing in the code changed since 0.11.1. The GitHub release
  v0.12.0 was created by hand on the 0.11.1 commit, so its manifest still said 0.11.1, the release workflow
  refused to build it (tag and manifest version must match) and it has no zip and no notes. From this
  release on the manifest, the tag and HACS all say the same version again. Treat 0.12.0 as 0.11.1.
* What 0.11.1 changed (no release of it was published): the seasonal and lifetime COP sensors show a value
  from 0.25 kWh of counted electricity (the 24 h COP from 0.1 kWh) instead of 1 kWh, which took hours on a
  pump that mostly runs at minimum speed. The COP sensors have a `status` attribute that says why there is
  no value yet, for example `collecting data: 0.12 of 0.25 kWh of electricity`. The COP from the pump's own
  counters keeps 1 kWh, as those counters only change in steps of 0.1 kWh.

## 0.11.1 - 2026-10-24

* The seasonal and lifetime COP sensors stayed unknown for hours on a pump that mostly runs at minimum speed
  (it draws about 0.2 kWh an hour), because they waited for 1 kWh of counted electricity. They now show a value
  from 0.25 kWh (the 24 h COP from 0.1 kWh, was 0.2). The COP from the pump's own counters keeps 1 kWh, as
  those counters only change in steps of 0.1 kWh.
* The COP sensors say why they have no value: the `status` attribute reads `collecting data: 0.12 of 0.25 kWh
  of electricity` until there is enough, `ok` afterwards. On the 24 h sensors `status` now describes the 24 h
  value; the state of the current reading is only on the 15-minute sensors.
* Checked against a real points table of an S1155: with its operating point the pipeline works, the
  thresholds were the problem.

## 0.11.0 - 2026-10-24

* **Seasonal and lifetime COP**, separately for heating, hot water and total: *COP heating (season)*,
  *COP hot water (season)*, *COP total (season)* and the same *(lifetime)*. They count everything the
  compressor did (start-ups and mode changes included), so they are what a yearly performance factor
  looks like. The season starts on the 1st of a month chosen under Configure (*Season starts in month*,
  default October); `previous_season_cop` shows the last one.
* **COP pump counters (season / lifetime)**: the pump's own *Tot. production* over *Tot. consumption*
  (the lifetime figure covers the whole life of the pump; the pump's consumption is an estimate).
* **The missing energy totals**: *Compressor electricity, heating / hot water (calculated)* and *Heat
  produced, heating / hot water (calculated)*, summed from the compressor's power and the heat flow, as
  `total_increasing` kWh sensors for the Energy dashboard and long-term statistics. The heat sensors
  compare themselves with the pump's own heat counters (`calculated_vs_pump`).
* **Compressor starts today** and **Compressor run time per start (today)**, from the pump's start
  counter and the compressor's running time.
* The running totals are kept per day, saved every five minutes and when Home Assistant stops
  (`.storage/nibe_local_api.<serial>.kpi`) and restored at start-up. Time in which the pump could not be
  read counts for neither heat nor electricity (see `coverage`).
* New option: *Season starts in month*.

## 0.10.1 - 2026-10-24

* COP: two limits from 0.10.0 were too tight for real operation. A reading from an S1155 at minimum speed
  (24 Hz, 206 W, 15.1 L/min, 26.1 / 24.0 degC, which is a COP of about 10.6 and agrees with the pump's own hourly
  log of 2.27 kWh produced for 0.24 kWh used) was dropped as "out of range". The minimum power is now 100 W
  (was 250 W) and a single reading counts up to a COP of 15 (was 9). Without this the heating COP stayed
  unknown at low load, which is most of the mild season.
* README: says that the calculated COP uses the compressor's power input only, so it reads higher than a COP
  built on the pump's hourly energy log (which includes standby).

## 0.10.0 - 2026-10-24

* New calculated sensors, created when the pump reports the points they need (compressor state or running
  flag, operating priority, compressor power input, heating medium flow, condenser and return line
  temperatures):
  * **COP heating** and **COP hot water**: COP of the last 15 minutes, only while the pump is producing in
    that mode and has settled (unknown otherwise);
  * **COP heating (24 h)** and **COP hot water (24 h)**: energy-weighted COP of everything that counted in
    the last 24 hours;
  * **Heat output (calculated)**: flow times the temperature rise across the condenser, in kW (0 while the
    compressor is stopped).
* Heating and hot water are separated by the operating priority together with the reversing valve (QN10).
  Readings are left out while the compressor is stopped or less than 5 minutes into a run, a defrost or a
  mode change, while priority and valve disagree, after a sudden step in frequency, power, flow or
  temperature difference (2 minutes), when flow, power or temperature rise are out of range, and when a
  single reading's COP is under 0.8 or over 9 (counted in `rejected_readings`). Details are in the README.
* The COP is always summed heat over summed electricity, never an average of single readings. The sensors
  explain themselves through a `status` attribute.
* The calculation cannot disturb the other sensors: an unexpected error in it is logged once and only
  switches the COP sensors off.
* Not yet checked on a running pump (the available logs contain no numeric readings of a run).

## 0.9.16 - 2026-10-22

* Undoes the 0.9.15 change to "More hot water, minutes remaining" (point 4030): the pump's REST interface
  refuses writes to it with HTTP 400, so it is a read-only sensor again. If you updated to 0.9.15, the
  number entity of that point is left behind as "no longer provided" and can be deleted; the sensor comes
  back (or is created) and the card keeps finding it by itself.
* "More hot water" (point 4564) is the way to start a one-time hot water increase over REST. Tested on an
  S1155: writing 2 made the pump set the minutes remaining to 120 within seconds and count them down. The
  entity is still created disabled; its description now says what to write. The pump's own length (120
  minutes) cannot be changed over REST.
* The README example (hot water boost before the solar peak) now writes 2 into More hot water, checks that
  the pump started, and cancels after 2 hours 15 minutes if it is still on.

## 0.9.15 - 2026-10-22

* "More hot water (minutes)" (point 4030) is now a number you can write, enabled by default. Writing
  minutes starts a one-time hot water increase: the pump sets "More hot water" (point 4564) to 2 and
  counts the minutes down to 0, one per minute (as the owner does with the NIBE Modbus integration).
  Before, it was a read-only "minutes remaining" sensor. The pump's REST interface flags the point
  read-only, so the write is unconfirmed here: if the pump refuses it, the entity reports the error.
  The old sensor entity of the same point is left behind as "no longer provided" and can be deleted;
  the card finds the new one by itself. An example automation (hot water boost before the solar
  peak) is in the README.

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
