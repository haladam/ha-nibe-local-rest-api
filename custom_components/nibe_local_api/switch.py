from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .entity import NibePointEntity, enable_live_entities, point_entities


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    entities = point_entities(coordinator, "switch", NibePointSwitch)
    enable_live_entities(
        hass, "switch", [e.unique_id for e in entities if e.info.enabled]
    )
    async_add_entities([NibeAidSwitch(coordinator), *entities])


class NibePointSwitch(NibePointEntity, SwitchEntity):
    @property
    def is_on(self):
        value = self._value
        return None if value is None else round(value) == 1

    async def async_turn_on(self, **kwargs):
        await self._write_raw(1)

    async def async_turn_off(self, **kwargs):
        await self._write_raw(0)


class NibeAidSwitch(CoordinatorEntity, SwitchEntity):
    _attr_has_entity_name = True
    _attr_name = "Aid mode"

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.serial}_aidmode"
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self):
        mode = self.coordinator.device_state.get("aidMode")
        return None if mode is None else mode == "on"

    async def _set(self, value: str):
        await self.coordinator.async_set_mode("aidmode", "aidMode", value)

    async def async_turn_on(self, **kwargs):
        await self._set("on")

    async def async_turn_off(self, **kwargs):
        await self._set("off")
