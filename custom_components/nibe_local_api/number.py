from __future__ import annotations

from homeassistant.components.number import (
    NumberDeviceClass, NumberEntity, NumberMode,
)

from .api import scale_factor, to_raw
from .entity import NibePointEntity, enable_live_entities, point_entities


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    entities = point_entities(coordinator, "number", NibeNumber)
    enable_live_entities(
        hass, "number", [e.unique_id for e in entities if e.info.enabled]
    )
    async_add_entities(entities)


class NibeNumber(NibePointEntity, NumberEntity):
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, point_id: int) -> None:
        super().__init__(coordinator, point_id)
        point = coordinator.data[point_id]
        meta = point["metadata"]
        factor = scale_factor(point_id, point)
        self._attr_native_min_value = round(self.info.min_raw * factor, 10)
        self._attr_native_max_value = round(self.info.max_raw * factor, 10)
        self._attr_native_step = round((meta.get("change") or 1) * factor, 10)
        if self.info.unit:
            self._attr_native_unit_of_measurement = self.info.unit
        if self.info.device_class:
            try:
                self._attr_device_class = NumberDeviceClass(self.info.device_class)
            except ValueError:
                pass

    @property
    def native_value(self):
        return self._value

    async def async_set_native_value(self, value: float) -> None:
        await self._write_raw(to_raw(self.point_id, self._point, value))
