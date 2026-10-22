from homeassistant.components.select import SelectEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .entity import NibePointEntity, enable_live_entities, point_entities


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    entities = point_entities(coordinator, "select", NibePointSelect)
    enable_live_entities(
        hass, "select", [e.unique_id for e in entities if e.info.enabled]
    )
    async_add_entities([NibeSmartModeSelect(coordinator), *entities])


class NibePointSelect(NibePointEntity, SelectEntity):
    def __init__(self, coordinator, point_id: int) -> None:
        super().__init__(coordinator, point_id)
        self._labels = dict(self.info.options)
        self._attr_options = list(self._labels.values())

    @property
    def current_option(self):
        value = self._value
        if value is None:
            return None
        return self._labels.get(int(round(value)))

    async def async_select_option(self, option: str) -> None:
        for key, label in self._labels.items():
            if label == option:
                await self._write_raw(key * self._div)
                return


class NibeSmartModeSelect(CoordinatorEntity, SelectEntity):
    _attr_has_entity_name = True
    _attr_name = "Smart mode"
    _attr_options = ["normal", "away"]

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.serial}_smartmode"
        self._attr_device_info = coordinator.device_info

    @property
    def current_option(self):
        return self.coordinator.device_state.get("smartMode")

    async def async_select_option(self, option: str):
        await self.coordinator.async_set_mode("smartmode", "smartMode", option)
