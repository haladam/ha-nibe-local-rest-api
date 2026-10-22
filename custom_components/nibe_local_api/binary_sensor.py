from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass, BinarySensorEntity,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import pump_running, scaled_value
from .const import PUMP_POINTS
from .entity import NibePointEntity, enable_live_entities, point_entities


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    entities = point_entities(coordinator, "binary_sensor", NibeBinarySensor)
    enable_live_entities(
        hass, "binary_sensor", [e.unique_id for e in entities if e.info.enabled]
    )
    pumps = [
        NibePumpRunningSensor(coordinator, key, point_id, name)
        for key, (point_id, name) in PUMP_POINTS.items()
        if point_id in coordinator.data
    ]
    async_add_entities([NibeAlarmBinarySensor(coordinator), *pumps, *entities])


class NibeAlarmBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Alarm active"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.serial}_alarm_active"
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self):
        return bool(self.coordinator.alarms)


class NibePumpRunningSensor(CoordinatorEntity, BinarySensorEntity):
    """On while the pump speed is above zero (the heating medium pump idles at its
    wait-mode speed, so it reads on almost all the time; the brine pump follows the
    compressor)."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _unrecorded_attributes = frozenset({"speed_point_id", "speed_percent"})

    def __init__(self, coordinator, key: str, point_id: int, name: str):
        super().__init__(coordinator, {point_id})
        self._point_id = point_id
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.serial}_pump_running_{key}"
        self._attr_device_info = coordinator.device_info

    def _speed(self):
        point = self.coordinator.data.get(self._point_id)
        return scaled_value(self._point_id, point) if point else None

    @property
    def is_on(self):
        return pump_running(self._speed())

    @property
    def available(self) -> bool:
        return super().available and self._speed() is not None

    @property
    def extra_state_attributes(self):
        return {"speed_point_id": self._point_id, "speed_percent": self._speed()}


class NibeBinarySensor(NibePointEntity, BinarySensorEntity):
    def __init__(self, coordinator, point_id: int) -> None:
        super().__init__(coordinator, point_id)
        if self.info.device_class:
            try:
                self._attr_device_class = BinarySensorDeviceClass(self.info.device_class)
            except ValueError:
                pass

    @property
    def is_on(self):
        value = self._value
        return None if value is None else bool(round(value))
