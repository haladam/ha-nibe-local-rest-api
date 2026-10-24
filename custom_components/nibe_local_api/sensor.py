from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass, SensorEntity, SensorStateClass,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import (
    firmware_version, heater_load_percent, heater_max_steps, heater_power_kw, scaled_value,
)
from .const import HEATER_MAX_POINT, HEATER_STEP_KW, HEATER_STEPS_POINT, VERSION_POINT
from .entity import NibePointEntity, enable_live_entities
from .kpi import HEATING, HOT_WATER


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
    if coordinator.kpi is not None:  # the pump reports what the COP calculation needs
        extra += [
            NibeCopSensor(coordinator, HEATING, long=False),
            NibeCopSensor(coordinator, HOT_WATER, long=False),
            NibeCopSensor(coordinator, HEATING, long=True),
            NibeCopSensor(coordinator, HOT_WATER, long=True),
            NibeHeatOutputSensor(coordinator),
        ]
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


_COP_LABEL = {HEATING: "heating", HOT_WATER: "hot water"}


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
        return {
            "status": last.status if last else None,
            "settling_seconds_left": round(last.settle_left_s) if last else None,
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
