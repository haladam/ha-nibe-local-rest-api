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
