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
animation: true                   # false switches the moving pipes and fans off
fit_height: true                  # false lets the wide layout grow to the full card width (taller than a short window)
device: <device id>               # only if two NIBE heat pumps are set up
pv:
  power: sensor.pv_power          # PV production, W or kW (the card shows the pump's own PV value without it)
  battery: sensor.battery_soc     # optional: shows this battery level instead of "Excess solar"
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
`valve_hw`, `circ_pump`, `cooling_pump`, `degree_minutes`, `alarm`, `boost_minutes`.

Notes

* In the wide layout the picture is scaled down to fit the window height (window height minus 160 px
  for the header and margins, but never below 380 px), so a wide card does not need scrolling. It
  keeps its proportions and is centred. `fit_height: false` turns that off. The phone layout always
  keeps its full height and scrolls.
* The heating circuit is drawn as underfloor heating. The card only follows the pump's flow
  setting if the entity "Flow setting climate system 1" (point 3976, disabled by default) is
  enabled; otherwise set `circuit.type`.
* "COP (1 h)" is the heat produced divided by the energy used in the last full hour, from the
  pump's own hourly energy log. It is an estimate and shows a dash when the pump used almost
  nothing in that hour.
* "Stop" is the hot water stop temperature of the selected hot water demand (small, medium or
  large). With smart control the pump decides and the card shows a dash.
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
* "Excess solar" is the PV surplus power that was passed to the heat pump (point 14314, enabled
  by default, filled by your own automation). It is replaced by the battery level if `pv.battery` is set.
* The tank is drawn after the KNV Greenwater: insulation, a domed hot water vessel with cold water
  in and hot water out on top, and the heating water zone with the round flange below. The heat
  pump's supply meets the upper left connection and the return leaves from the bottom left one.
  BT7 is shown inside the hot water vessel, BT6 in the heating water of the jacket, low down.
* The hot water circulation loop (point 1829) is off by default, because most plants have no circulation pump.
  Set `tank.circulation: true` if yours does.
* Click any value to open the entity's details.
