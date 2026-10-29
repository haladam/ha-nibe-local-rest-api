# NIBE plant card

`nibe-plant-card` is an animated overview of the heating plant: ground loop, NIBE S1155, the
Greenwater tank (hot water cylinder inside a heating water jacket), one heating circuit and
the photovoltaic input. The integration loads it by itself; there is no resource to add.

```yaml
type: custom:nibe-plant-card
```

The card finds the integration's entities by NIBE point id, so no entity has to be named.
Everything below is optional.

```yaml
type: custom:nibe-plant-card
title: Heating plant              # header above the picture
layout: auto                      # auto (default), wide or narrow; auto switches below 560 px
animation: true                   # false switches the moving pipes, fans and compressor off
fit_height: true                  # false lets the wide layout grow to the full card width (taller than a short window)
device: <device id>               # only if two NIBE heat pumps are set up
pv:
  power: sensor.pv_power          # PV production, W or kW (the card shows the pump's own PV value without it)
  battery: sensor.battery_soc     # optional: shows this battery level instead of "Excess solar"
  grid_import: sensor.solarnet_power_grid_import          # optional: power drawn from the grid, W or kW
  battery_discharge: sensor.solarnet_power_battery_discharge  # optional: power drawn from the battery, W or kW
heatpump:
  name: NIBE S1155
tank:
  name: Greenwater 450/300
  hot_water_l: 450                # litres of the inner hot water cylinder
  jacket_l: 300                   # litres of the heating water jacket
  circulation: false              # true draws a hot water circulation loop with its pump (only if you have one)
circuit:
  type: underfloor                # underfloor, radiator or both (heating)
  name: Underfloor heating
  cooling_type: ceiling           # ceiling (default) or same: how the circuit is drawn while cooling
  cooling_name: Ceiling cooling
entities:                         # replace what the card would find
  outdoor: sensor.my_outdoor_sensor
```

Slots for `entities`: `outdoor`, `supply`, `return`, `calc_supply`, `calc_supply_cooling`, `hw_top`, `hw_charge`,
`brine_in`, `brine_out`, `compressor_hz`, `power`, `gp1`, `gp2`, `priority`, `aux_power`,
`valve_hw`, `circ_pump`, `cooling_pump`, `degree_minutes`, `alarm`, `boost_minutes`, and for the COP readout
`cop_heating`, `cop_hot_water`, `cop_heating_24h`, `cop_hot_water_24h`.

Notes

* In the wide layout the picture is scaled down to fit the window height (window height minus 160 px
  for the header and margins, but never below 380 px), so a wide card does not need scrolling. It
  keeps its proportions and is centred. `fit_height: false` turns that off. The phone layout always
  keeps its full height and scrolls.
* The heating circuit is drawn as underfloor heating. The card only follows the pump's flow
  setting if the entity "Flow setting climate system 1" (point 3976, disabled by default) is
  enabled; otherwise set `circuit.type`.
* The COP readout shows the calculated COP of the integration (sensors *COP heating*, *COP hot water* and
  their 24 h versions, from version 0.13.0 of the integration; the card finds them by themselves). While the
  pump heats or charges hot water it shows the COP of that mode over the last 15 minutes, labelled "COP".
  That value is unknown for the first minutes after a start, a defrost or a change of mode; the card then
  shows the COP of the last 24 hours ("COP (24 h)"), and on standby the 24 h COP of heating, or of hot water
  if there is none for heating. If nothing has been calculated yet (for example right after a restart) or the
  integration is older, it shows "COP (1 h)": the heat produced divided by the energy used in the last full
  hour, from the pump's own hourly energy log. That one is an estimate, includes standby and the
  controller, and shows a dash when the pump used almost nothing in that hour. Hover (or tap) the value
  to see which one it is; tapping opens the sensor. During cooling the calculated COP is not used.
* "Start" and "Stop" below the tank are the hot water start and stop temperatures of the selected
  hot water demand (small, medium or large): the temperatures at which the pump starts and stops
  charging. With smart control the pump decides and the card shows a dash. The top temperature
  (BT7) is shown once, inside the hot water vessel.
* In summer the circuit panel turns into the cooling circuit ("Ceiling cooling" by default,
  `circuit.cooling_type: same` keeps the heating drawing). Flow and return are the pump's
  supply and return line sensors (BT2, BT3), the target is the calculated cooling supply
  temperature (point 2695). With the compressor off the ground loop is drawn straight into
  the circuit (passive cooling); with the compressor running the card says "Active cooling"
  and shows the circuit lanes instead. COP is not shown during passive cooling.
* The pipe of the emitter (underfloor, ceiling, radiator) is drawn as one continuous line, like
  the ground loop: it begins where the supply pipe ends and ends where the return pipe begins.
  In passive cooling the two ground loop lines join the circuit at those same two points.
* Water lines follow one rule: red is the warm side, blue the cold side. Heating and hot water
  have a red supply and a blue return. The ground loop sends cold brine into the ground (blue)
  and takes warmer brine back (red); in cooling it is the other way round. The cooling circuit
  has a blue supply and a red return, and with passive cooling two extra lines show cold water
  to the circuit and warm water back. Only the solar line has its own colour (amber). The
  numbers keep a temperature colour scale.
* With the tank and the heating circuit on the same side of the heat pump, one pipe crossing
  cannot be avoided: the tank's return has to get past the supply line to the circuit. The card
  keeps it to that one place and draws it as a bridge (the return passes under the supply, with a
  gap in it). In passive cooling the circuit is fed from the ground loop alone, so the heating
  pipes to it are not drawn then.
* The circulation pumps (GP1 heating medium, GP2 brine) are drawn as in-line circulators with a flange
  at each pipe connection and, as if the motor were cut away, a closed impeller with seven
  backward-curved blades. The impeller turns while the pump runs. GP2 sits on the line that brings the
  brine back from the ground loop into the heat pump ("brine in", before the evaporator), which is where
  NIBE's service manual puts it (the brine in sensor BT10 is "before" it).
* The compressor is drawn as a scroll compressor: a fixed spiral wall and an identical one that
  orbits around it without turning. Where the walls touch they close off pockets of gas that
  move towards the middle and shrink, which is how the gas is compressed (blue at the rim,
  red at the discharge port in the centre). It moves while the compressor runs, faster at a
  higher frequency, and stands still when it stops. NIBE does not state the compressor type of
  the S1155 in its documents; a scroll is the usual choice for heat pumps of this size, so
  take the drawing as a faithful picture of how that kind works, not as a photo of your unit.
* "Excess solar" is the PV surplus power that was passed to the heat pump (point 14314, enabled
  by default, filled by your own automation). It is replaced by the battery level if `pv.battery` is set.
* `pv.grid_import` and `pv.battery_discharge` add a chip with the power for each source above the heat
  pump (between the top panels and the heat pump in the narrow layout), with its own pipe into the heat
  pump: violet for the grid, green for the battery, next to the amber solar line. A pipe moves while its
  source delivers more than 20 W and the pump draws power; at 0 W the chip is dimmed. Click a chip for
  the entity's history. Without the key the chip is not drawn.
* The tank is drawn after the KNV Greenwater: insulation, a domed hot water vessel with cold water
  in and hot water out on top, and the heating water zone with the round flange below. The heat
  pump's supply meets the upper left connection and the return leaves from the bottom left one.
  BT7 is shown inside the hot water vessel, BT6 in the heating water of the jacket, low down.
* The hot water circulation loop (point 1829) is off by default, because most plants have no circulation pump.
  Set `tank.circulation: true` if yours does.
* Click any value to open the entity's details.
