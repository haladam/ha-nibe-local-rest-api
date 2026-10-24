from __future__ import annotations

from datetime import date, timedelta

from homeassistant.components.sensor import (
    SensorDeviceClass, SensorEntity, SensorStateClass,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import (
    firmware_version, heater_load_percent, heater_max_steps, heater_power_kw, scaled_value,
)
from .const import (
    HEATER_MAX_POINT, HEATER_STEP_KW, HEATER_STEPS_POINT, KPI_COUNTERS, VERSION_POINT,
)
from .entity import NibePointEntity, enable_live_entities
from .kpi import HEATING, HOT_WATER
from .kpi_totals import TOTAL, season_start


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    entities = []
    for pid, info in coordinator.infos.items():
        if info.kind != "sensor":
            continue
        cls = NibeSensor
        if pid == HEATER_STEPS_POINT:
            cls = NibeHeaterStepsSensor
        elif pid == VERSION_POINT:
            cls = NibeVersionSensor
        entities.append(cls(coordinator, pid))
    enable_live_entities(
        hass, "sensor", [e.unique_id for e in entities if e.info.enabled]
    )
    extra = [NibeAlarmSensor(coordinator)]
    if HEATER_STEPS_POINT in coordinator.data:
        extra += [NibeHeaterPowerSensor(coordinator), NibeHeaterLoadSensor(coordinator)]
    if coordinator.kpi is not None and coordinator.totals is not None:
        # the pump reports what the COP calculation needs
        extra += [
            NibeCopSensor(coordinator, HEATING, long=False),
            NibeCopSensor(coordinator, HOT_WATER, long=False),
            NibeCopSensor(coordinator, HEATING, long=True),
            NibeCopSensor(coordinator, HOT_WATER, long=True),
            NibeHeatOutputSensor(coordinator),
        ]
        extra += [
            NibeEnergyTotalSensor(coordinator, kind, mode)
            for kind in ("electricity", "heat") for mode in (HEATING, HOT_WATER)
        ]
        extra += [
            NibeCopPeriodSensor(coordinator, mode, scope)
            for scope in ("season", "lifetime") for mode in (HEATING, HOT_WATER, TOTAL)
        ]
        if KPI_COUNTERS["total_heat"] in coordinator.data and KPI_COUNTERS["total_el"] in coordinator.data:
            extra += [NibeCopPumpSensor(coordinator, "season"), NibeCopPumpSensor(coordinator, "lifetime")]
        if KPI_COUNTERS["starts"] in coordinator.data:
            extra += [NibeStartsSensor(coordinator), NibeRunTimeSensor(coordinator)]
    async_add_entities([*extra, *entities])


def _heater_values(coordinator):
    steps = scaled_value(HEATER_STEPS_POINT, coordinator.data.get(HEATER_STEPS_POINT) or {})
    max_kw = None
    if HEATER_MAX_POINT in coordinator.data:
        max_kw = scaled_value(HEATER_MAX_POINT, coordinator.data[HEATER_MAX_POINT])
    return steps, max_kw


class NibeAlarmSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Active alarms"
    _attr_icon = "mdi:alert-circle-outline"

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.serial}_alarms"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self):
        return len(self.coordinator.alarms)

    @property
    def extra_state_attributes(self):
        return {"alarms": self.coordinator.alarms}


class NibeHeaterPowerSensor(CoordinatorEntity, SensorEntity):
    """Internal electric heater power, calculated from its step count (0.5 kW/step)."""

    _attr_has_entity_name = True
    _attr_name = "Internal additional heat power (from steps)"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = "kW"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _unrecorded_attributes = frozenset({"steps", "kw_per_step"})

    def __init__(self, coordinator):
        super().__init__(coordinator, {HEATER_STEPS_POINT})
        self._attr_unique_id = f"{coordinator.serial}_internal_heater_power_calc"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self):
        steps, _ = _heater_values(self.coordinator)
        return heater_power_kw(steps)

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None

    @property
    def extra_state_attributes(self):
        steps, _ = _heater_values(self.coordinator)
        return {"steps": steps, "kw_per_step": HEATER_STEP_KW}


class NibeHeaterLoadSensor(CoordinatorEntity, SensorEntity):
    """Heater power as a percentage of the 'Max. internal additional heat' setting."""

    _attr_has_entity_name = True
    _attr_name = "Internal additional heat load"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _unrecorded_attributes = frozenset({"steps", "max_kw", "max_steps"})

    def __init__(self, coordinator):
        super().__init__(coordinator, {HEATER_STEPS_POINT, HEATER_MAX_POINT})
        self._attr_unique_id = f"{coordinator.serial}_internal_heater_load"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self):
        steps, max_kw = _heater_values(self.coordinator)
        return heater_load_percent(steps, max_kw)

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None

    @property
    def extra_state_attributes(self):
        steps, max_kw = _heater_values(self.coordinator)
        return {"steps": steps, "max_kw": max_kw, "max_steps": heater_max_steps(max_kw)}


_COP_LABEL = {HEATING: "heating", HOT_WATER: "hot water", TOTAL: "total"}


class NibeCopSensor(CoordinatorEntity, SensorEntity):
    """COP of the compressor for heating or hot water, from kpi.CopTracker.

    The short one covers the last 15 minutes and is only shown while the pump is producing
    in that mode and has settled (unknown otherwise). The 24 h one is the energy-weighted COP
    of everything that counted in the last day and stays while the pump is idle.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:heat-pump"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    # these change on every update; they stay visible but are not written to the database
    _unrecorded_attributes = frozenset({
        "status", "settling_seconds_left", "counted_minutes", "heat_kwh", "electricity_kwh",
        "rejected_readings", "window_minutes",
    })

    def __init__(self, coordinator, mode: str, long: bool) -> None:
        super().__init__(coordinator)
        self._mode, self._long = mode, long
        suffix = "_24h" if long else ""
        self._attr_unique_id = f"{coordinator.serial}_cop_{mode}{suffix}"
        self._attr_name = f"COP {_COP_LABEL[mode]}" + (" (24 h)" if long else "")
        self._attr_device_info = coordinator.device_info

    @property
    def _window_s(self) -> float:
        cfg = self.coordinator.kpi.cfg
        return cfg.long_window_s if self._long else cfg.live_window_s

    @property
    def native_value(self):
        tracker = self.coordinator.kpi
        return tracker.long_cop(self._mode) if self._long else tracker.live_cop(self._mode)

    @property
    def extra_state_attributes(self):
        tracker = self.coordinator.kpi
        valid, heat, power = tracker.window(self._mode, self._window_s)
        last = tracker.last
        if self._long:
            enough = power >= tracker.cfg.min_long_energy_kwh
            status = "ok" if enough else (
                f"collecting data: {power:.2f} of {tracker.cfg.min_long_energy_kwh:g} kWh of electricity")
        else:
            status = last.status if last else None
        return {
            "status": status,
            "settling_seconds_left": None if self._long or not last else round(last.settle_left_s),
            "window_minutes": round(self._window_s / 60),
            "counted_minutes": round(valid / 60, 1),
            "heat_kwh": round(heat, 3),
            "electricity_kwh": round(power, 3),
            "rejected_readings": tracker.rejected[self._mode],
        }


class NibeHeatOutputSensor(CoordinatorEntity, SensorEntity):
    """Heat the compressor delivers right now: flow x temperature rise across the condenser."""

    _attr_has_entity_name = True
    _attr_name = "Heat output (calculated)"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = "kW"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _unrecorded_attributes = frozenset({"status"})

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.serial}_heat_output_calc"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self):
        last = self.coordinator.kpi.last
        return None if last is None or last.heat_kw is None else round(last.heat_kw, 3)

    @property
    def extra_state_attributes(self):
        last = self.coordinator.kpi.last
        return {"status": last.status if last else None}


def _yesterday(today: str) -> str:
    return (date.fromisoformat(today) - timedelta(days=1)).isoformat()


class NibeEnergyTotalSensor(CoordinatorEntity, SensorEntity):
    """Heat produced or compressor electricity used in one mode, summed from the pump's readings.

    Lifetime counters for the Energy dashboard and long-term statistics: they start at 0 when the
    integration first sees the pump and are restored after a restart.
    """

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = "kWh"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 1
    _unrecorded_attributes = frozenset({
        "counting_since", "counted_hours", "coverage", "pump_counter_kwh", "calculated_vs_pump",
    })

    def __init__(self, coordinator, kind: str, mode: str) -> None:
        super().__init__(coordinator)
        self._kind, self._mode = kind, mode
        self._attr_unique_id = f"{coordinator.serial}_calc_{kind}_{mode}"
        what = "Compressor electricity" if kind == "electricity" else "Heat produced"
        self._attr_name = f"{what}, {_COP_LABEL[mode]} (calculated)"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self):
        heat, electricity = self.coordinator.totals.lifetime_sums(self._mode)
        return round(heat if self._kind == "heat" else electricity, 3)

    @property
    def extra_state_attributes(self):
        totals = self.coordinator.totals
        coverage = totals.coverage()
        attrs = {
            "counting_since": totals.since,
            "counted_hours": round(totals.counted_s / 3600, 1),
            "coverage": None if coverage is None else round(coverage, 3),
        }
        if self._kind == "heat":
            pump = totals.pump_delta(self._mode)
            attrs["pump_counter_kwh"] = None if pump is None else round(pump, 1)
            attrs["calculated_vs_pump"] = (
                round(self.native_value / pump, 3) if pump is not None and pump >= 1 else None
            )
        return attrs


class NibeCopPeriodSensor(CoordinatorEntity, SensorEntity):
    """COP over a season or since counting began, from the running totals (start-ups included)."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:heat-pump"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2
    _unrecorded_attributes = frozenset({
        "status", "heat_kwh", "electricity_kwh", "since", "season_start", "previous_season_cop",
    })

    def __init__(self, coordinator, mode: str, scope: str) -> None:
        super().__init__(coordinator)
        self._mode, self._scope = mode, scope
        self._attr_unique_id = f"{coordinator.serial}_cop_{mode}_{scope}"
        self._attr_name = f"COP {_COP_LABEL[mode]} ({scope})"
        self._attr_device_info = coordinator.device_info

    def _sums(self, previous: bool = False):
        totals = self.coordinator.totals
        if self._scope == "lifetime":
            return totals.lifetime_sums(self._mode)
        return totals.season_sums(self._mode, self.coordinator._today(), previous)

    @property
    def native_value(self):
        return self.coordinator.totals.cop(*self._sums())

    @property
    def extra_state_attributes(self):
        totals, today = self.coordinator.totals, self.coordinator._today()
        heat, electricity = self._sums()
        attrs = {
            "status": totals.collecting(electricity),
            "heat_kwh": round(heat, 2), "electricity_kwh": round(electricity, 2),
        }
        if self._scope == "lifetime":
            attrs["since"] = totals.since
            return attrs
        previous = totals.cop(*self._sums(previous=True))
        attrs.update({
            "season_start": season_start(date.fromisoformat(today), totals.season_month).isoformat(),
            "since": totals.season_since(today),
            "previous_season_cop": None if previous is None else round(previous, 2),
        })
        return attrs


class NibeCopPumpSensor(CoordinatorEntity, SensorEntity):
    """COP from the pump's own lifetime counters (Tot. production / Tot. consumption).

    The lifetime value covers everything since the pump was commissioned; the season value
    covers the time since the season began or since this integration first read the counters.
    The pump's consumption figure is an estimate and includes additional heat.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:heat-pump"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2
    _unrecorded_attributes = frozenset({"status", "heat_kwh", "electricity_kwh", "since", "season_start"})

    def __init__(self, coordinator, scope: str) -> None:
        super().__init__(coordinator)
        self._scope = scope
        self._attr_unique_id = f"{coordinator.serial}_cop_pump_{scope}"
        self._attr_name = f"COP pump counters ({scope})"
        self._attr_device_info = coordinator.device_info

    def _sums(self):
        totals = self.coordinator.totals
        if self._scope == "lifetime":
            return totals.pump_now.get("total_heat"), totals.pump_now.get("total_el")
        return totals.pump_delta("total_heat", season=True), totals.pump_delta("total_el", season=True)

    @property
    def native_value(self):
        heat, electricity = self._sums()
        if heat is None or electricity is None:
            return None
        totals = self.coordinator.totals
        return totals.cop(heat, electricity, totals.cfg.min_pump_energy_kwh)

    @property
    def extra_state_attributes(self):
        totals = self.coordinator.totals
        heat, electricity = self._sums()
        attrs = {
            "status": "no data" if electricity is None else totals.collecting(electricity, totals.cfg.min_pump_energy_kwh),
            "heat_kwh": None if heat is None else round(heat, 1),
            "electricity_kwh": None if electricity is None else round(electricity, 1),
        }
        if self._scope == "season":
            today = self.coordinator._today()
            attrs["season_start"] = season_start(date.fromisoformat(today), totals.season_month).isoformat()
            attrs["since"] = totals.season_from
        return attrs


class NibeStartsSensor(CoordinatorEntity, SensorEntity):
    """Compressor starts since midnight (the pump's own start counter, read while Home Assistant runs)."""

    _attr_has_entity_name = True
    _attr_name = "Compressor starts today"
    _attr_icon = "mdi:restart"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _unrecorded_attributes = frozenset({"yesterday"})

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.serial}_compressor_starts_today"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self):
        return self.coordinator.totals.today(self.coordinator._today())["starts"]

    @property
    def extra_state_attributes(self):
        days = self.coordinator.totals.days
        yesterday = days.get(_yesterday(self.coordinator._today()))
        return {"yesterday": None if yesterday is None else yesterday["starts"]}


class NibeRunTimeSensor(CoordinatorEntity, SensorEntity):
    """Average length of a compressor run today: running time divided by starts (short runs wear the pump)."""

    _attr_has_entity_name = True
    _attr_name = "Compressor run time per start (today)"
    _attr_icon = "mdi:timer-outline"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = "min"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _unrecorded_attributes = frozenset({"run_minutes", "starts", "yesterday_minutes"})

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.serial}_compressor_run_per_start"
        self._attr_device_info = coordinator.device_info

    @staticmethod
    def _average(rec):
        if rec is None or rec["starts"] < 1 or rec["run_s"] <= 0:
            return None
        return rec["run_s"] / 60.0 / rec["starts"]

    @property
    def native_value(self):
        average = self._average(self.coordinator.totals.today(self.coordinator._today()))
        return None if average is None else round(average, 1)

    @property
    def extra_state_attributes(self):
        totals, today = self.coordinator.totals, self.coordinator._today()
        rec = totals.today(today)
        yesterday = self._average(totals.days.get(_yesterday(today)))
        return {
            "run_minutes": round(rec["run_s"] / 60, 1),
            "starts": rec["starts"],
            "yesterday_minutes": None if yesterday is None else round(yesterday, 1),
        }


class NibeSensor(NibePointEntity, SensorEntity):
    def __init__(self, coordinator, point_id: int) -> None:
        super().__init__(coordinator, point_id)
        info = self.info
        if info.unit:
            self._attr_native_unit_of_measurement = info.unit
        if info.device_class:
            try:
                self._attr_device_class = SensorDeviceClass(info.device_class)
            except ValueError:
                pass
        if info.state_class:
            self._attr_state_class = SensorStateClass(info.state_class)
        decimal = coordinator.data[point_id].get("metadata", {}).get("decimal")
        if info.unit and decimal is not None and not info.options:
            self._attr_suggested_display_precision = decimal

    @property
    def native_value(self):
        value = self._value
        if value is None:
            return None
        if self.info.options:
            key = int(round(value))
            return self.info.options.get(key, str(key))
        if self.info.integer and (not self.info.unit or self.info.unit == "steps") and float(value).is_integer():
            return int(value)
        return value


class NibeHeaterStepsSensor(NibeSensor):
    """Step count of the internal heater with the highest allowed step as attribute."""

    _unrecorded_attributes = frozenset({"kw_per_step", "max_kw_setting", "max_steps"})
    _also_depends_on = (HEATER_MAX_POINT,)  # its attributes show the maximum heater setting

    @property
    def extra_state_attributes(self):
        attrs = dict(super().extra_state_attributes)
        _, max_kw = _heater_values(self.coordinator)
        attrs["kw_per_step"] = HEATER_STEP_KW
        attrs["max_kw_setting"] = max_kw
        attrs["max_steps"] = heater_max_steps(max_kw)
        return attrs


class NibeVersionSensor(NibeSensor):
    """The heat pump's software version as text ('4.14') instead of the raw register."""

    @property
    def native_value(self):
        return firmware_version(self.coordinator.data)
