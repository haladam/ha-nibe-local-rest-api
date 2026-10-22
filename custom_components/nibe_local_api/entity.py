from __future__ import annotations

import logging

from homeassistant.const import EntityCategory
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import NibeApiError, divisor, raw_value, scaled_value
from .const import DOMAIN, MULTIPLIERS
from .exceptions import translated_error

_LOGGER = logging.getLogger(__name__)

CATEGORY = {"diagnostic": EntityCategory.DIAGNOSTIC, "config": EntityCategory.CONFIG}


class NibePointEntity(CoordinatorEntity):
    _attr_has_entity_name = True
    # Static text and the raw value are shown in the UI but not stored with every state
    # change (they would make each recorded state a new attribute row).
    _unrecorded_attributes = frozenset({
        "point_id", "modbus_register", "nibe_title", "divisor", "multiplier",
        "default_value", "description", "firmware_description", "menu", "menu_range",
        "menu_note", "menu_warning", "raw_value",
    })

    # Other points the entity's state or attributes also depend on (besides its own).
    _also_depends_on: tuple[int, ...] = ()

    def __init__(self, coordinator, point_id: int) -> None:
        super().__init__(coordinator, {point_id, *self._also_depends_on})
        self.point_id = point_id
        self.info = coordinator.infos[point_id]
        point = coordinator.data[point_id]
        meta = point.get("metadata", {})
        self._div = divisor(point_id, point)
        self._attr_unique_id = f"{coordinator.serial}_{point_id}"
        self._attr_name = self.info.name
        self._attr_device_info = coordinator.device_info
        self._attr_entity_registry_enabled_default = self.info.enabled
        self._attr_entity_category = CATEGORY.get(self.info.category)
        i = self.info
        attrs = {
            "point_id": point_id,
            "modbus_register": meta.get("modbusRegisterID"),
            "nibe_title": i.title,
            "divisor": self._div,
        }
        if point_id in MULTIPLIERS:
            attrs["multiplier"] = MULTIPLIERS[point_id]
        default = meta.get("intDefaultValue")
        if default is not None and not i.options and meta.get("variableType") == "integer":
            attrs["default_value"] = default / self._div
        for key, value in (
            ("description", i.description),
            ("firmware_description", i.fw_description),
            ("menu", i.menu_path),
            ("menu_range", i.menu_range),
            ("menu_note", i.menu_note),
            ("menu_warning", i.menu_warning),
        ):
            if value:
                attrs[key] = value
        self._static_attrs = attrs

    @property
    def extra_state_attributes(self):
        p = self._point
        raw = raw_value(p) if p else None
        return {**self._static_attrs, "raw_value": raw}

    @property
    def _point(self) -> dict | None:
        return self.coordinator.data.get(self.point_id)

    @property
    def _value(self) -> float | None:
        p = self._point
        return scaled_value(self.point_id, p) if p else None

    @property
    def available(self) -> bool:
        return super().available and self._value is not None

    async def _write_raw(self, raw: int) -> None:
        try:
            result = await self.coordinator.api.patch_points({self.point_id: raw})
        except NibeApiError as err:
            raise translated_error("write_failed", point_id=self.point_id, error=err) from err
        if isinstance(result, dict):
            status = result.get(str(self.point_id))
            if isinstance(status, str) and status.startswith("error"):
                raise translated_error("write_rejected", point_id=self.point_id, status=status)
        await self._read_back(raw)

    async def _read_back(self, expected: int) -> None:
        """Re-read just the written point and publish it right away.

        One small request replaces a full 1 MB table refresh, and it avoids the
        refresh debounce that could otherwise show the old value after a write.
        """
        try:
            fresh = await self.coordinator.api.get_point(self.point_id)
        except NibeApiError:
            fresh = None
        if not fresh or "metadata" not in fresh:
            await self.coordinator.async_request_refresh()
            return
        self.coordinator.data[self.point_id] = fresh
        self.coordinator.async_update_point_listeners([self.point_id])
        got = raw_value(fresh)
        if got != expected:
            _LOGGER.warning(
                "Point %s reads raw %s after writing raw %s. Menu 7.5.15 may be set to "
                "read-only, the controller may not have applied the value yet, or it "
                "adjusted it. The next poll shows the settled value.",
                self.point_id, got, expected,
            )


def enable_live_entities(hass, platform: str, unique_ids: list[str]) -> None:
    """Re-enable entities the integration itself had disabled."""
    reg = er.async_get(hass)
    for uid in unique_ids:
        entity_id = reg.async_get_entity_id(platform, DOMAIN, uid)
        if not entity_id:
            continue
        entry = reg.async_get(entity_id)
        if entry and entry.disabled_by == er.RegistryEntryDisabler.INTEGRATION:
            reg.async_update_entity(entity_id, disabled_by=None)


def point_entities(coordinator, kind: str, cls) -> list:
    return [
        cls(coordinator, pid)
        for pid, info in coordinator.infos.items()
        if info.kind == kind
    ]
