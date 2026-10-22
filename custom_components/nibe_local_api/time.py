from __future__ import annotations

from datetime import time as dtime

from homeassistant.components.time import TimeEntity

from .api import time_seconds
from .entity import NibePointEntity, enable_live_entities, point_entities


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    entities = point_entities(coordinator, "time", NibeTime)
    enable_live_entities(
        hass, "time", [e.unique_id for e in entities if e.info.enabled]
    )
    async_add_entities(entities)


class NibeTime(NibePointEntity, TimeEntity):
    """Time-of-day setting; the register holds seconds since midnight (5400 = 01:30)."""

    @property
    def _value(self):
        p = self._point
        return time_seconds(p) if p else None

    @property
    def native_value(self):
        secs = self._value
        if secs is None:
            return None
        return dtime(secs // 3600, (secs % 3600) // 60, secs % 60)

    async def async_set_value(self, value: dtime) -> None:
        await self._write_raw(value.hour * 3600 + value.minute * 60 + value.second)
