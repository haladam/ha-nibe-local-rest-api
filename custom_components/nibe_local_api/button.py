from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import NibeApiError, scaled_value
from .const import ALARM_NUMBER_POINT
from .exceptions import translated_error
from .entity import NibePointEntity, enable_live_entities, point_entities


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    entities = point_entities(coordinator, "button", NibePointButton)
    enable_live_entities(
        hass, "button", [e.unique_id for e in entities if e.info.enabled]
    )
    async_add_entities([NibeResetAlarmsButton(coordinator), *entities])


class NibePointButton(NibePointEntity, ButtonEntity):
    async def async_press(self) -> None:
        await self._write_raw(1)


class NibeResetAlarmsButton(CoordinatorEntity, ButtonEntity):
    _attr_has_entity_name = True
    _attr_name = "Reset alarms"

    def __init__(self, coordinator):
        super().__init__(coordinator, {ALARM_NUMBER_POINT})
        self._attr_unique_id = f"{coordinator.serial}_reset_alarms"
        self._attr_device_info = coordinator.device_info

    @property
    def available(self) -> bool:
        """Only offered while the heat pump reports an alarm (notifications or alarm number)."""
        if not super().available:
            return False
        if self.coordinator.alarms:
            return True
        number = scaled_value(ALARM_NUMBER_POINT, self.coordinator.data.get(ALARM_NUMBER_POINT) or {})
        return bool(number)

    async def async_press(self) -> None:
        try:
            await self.coordinator.api.reset_notifications()
        except NibeApiError as err:
            raise translated_error("alarm_reset_failed", error=err) from err
        await self.coordinator.async_request_refresh()
