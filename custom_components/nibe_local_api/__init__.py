from __future__ import annotations

import asyncio
import csv
import logging
import os
import time
from collections.abc import Callable, Iterable
from datetime import timedelta
from typing import Any

import voluptuous as vol
from aiohttp import BasicAuth
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME, Platform
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    NibeApiError, NibeAuthError, NibeLocalApi, firmware_version, parse_device, raw_value,
    scaled_value, version_label,
)
from .aux import AUX_FUNCTIONS, async_set_aux
from .catalog import build_infos, load_data
from .const import (
    CONF_FAST_INTERVAL, CONF_HTTPS, CONF_SCAN_INTERVAL, DEFAULT_FAST_INTERVAL,
    DEFAULT_SCAN_INTERVAL, DOMAIN, FAST_POLL_TIMEOUT, MAX_FAST_INTERVAL, MIN_FAST_INTERVAL,
)
from .exceptions import translated_error
from .fastpoll import is_point_payload, selected_point_ids
from .kpi import CopTracker, Settings as KpiSettings, available as kpi_available, build_sample
from .card import async_register_card

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [
    Platform.SENSOR, Platform.BINARY_SENSOR, Platform.NUMBER,
    Platform.SWITCH, Platform.SELECT, Platform.BUTTON, Platform.TIME,
]
SERVICE_SET_AUX = "set_aux"
SET_AUX_SCHEMA = vol.Schema({
    vol.Required("function"): vol.In(list(AUX_FUNCTIONS)),
    vol.Required("state"): cv.boolean,
})
CSV_HEADER = [
    "point_id", "modbus_register", "register_type", "nibe_title", "name", "platform",
    "unit", "device_class", "state_class", "category", "enabled_by_default", "live",
    "firmware_writable", "api_divisor", "min_raw", "max_raw", "raw_value", "value",
    "enum_labels", "mapping_status", "reason", "menu", "menu_range", "menu_note",
    "description", "firmware_description", "effective_min_raw", "effective_max_raw",
    "range_note",
]


def _csv_row(pid: int, i, point: dict) -> list:
    """One line of nibe_local_api_points.csv (same order as CSV_HEADER)."""
    meta = point.get("metadata", {})
    v = scaled_value(pid, point)
    labels = "; ".join(f"{k}={t}" for k, t in (i.options or {}).items())
    number = i.kind == "number"
    return [
        pid, meta.get("modbusRegisterID"), meta.get("modbusRegisterType"), i.title,
        i.name, i.kind, i.unit or "", i.device_class or "", i.state_class or "",
        i.category or "", i.enabled, i.live, bool(meta.get("isWritable")),
        meta.get("divisor"), meta.get("minValue"), meta.get("maxValue"),
        raw_value(point), "" if v is None else v, labels,
        i.mapping_status, i.reason, i.menu_path, i.menu_range, i.menu_note,
        i.description, i.fw_description, i.min_raw if number else "",
        i.max_raw if number else "", i.range_note,
    ]


def _write_csv(path: str, rows: list) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CSV_HEADER)
        w.writerows(rows)


class NibeCoordinator(DataUpdateCoordinator[dict[int, dict]]):
    def __init__(self, hass, entry, api: NibeLocalApi, info: dict) -> None:
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(hass, _LOGGER, name=DOMAIN, config_entry=entry,
                         update_interval=timedelta(seconds=interval))
        self.api = api
        self.serial = info["serial"]
        self.device_state: dict = {}
        self.alarms: list[dict] = []
        self.infos: dict = {}
        self.aux_lock = asyncio.Lock()
        # Serialises the full-table update and the fast single-point reads, so a slow
        # table can never overwrite a newer fast reading with an older one.
        self._poll_lock = asyncio.Lock()
        self.fast_points: list[int] = []
        self._fast_failures = 0
        self._sw_version: str | None = None
        self._scan_interval = interval
        # Calculated COP and heat output (kpi.py); created from the first table that has the points.
        self.kpi: CopTracker | None = None
        self._kpi_failed = False
        # point id -> callbacks of the entities that show it (see async_add_listener)
        self._point_callbacks: dict[int, set[CALLBACK_TYPE]] = {}
        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, info["serial"])},
            manufacturer=info["manufacturer"],
            name=info["name"],
            model=info["name"],
            serial_number=info["serial"],
            sw_version=version_label(info["firmware"]),
        )

    @callback
    def async_add_listener(
        self, update_callback: CALLBACK_TYPE, context: Any = None
    ) -> Callable[[], None]:
        """Register a listener; a set of point ids as context ties it to those points.

        A listener without context only hears about full updates. One with a set of
        point ids is also told when just those points change (fast polling, write
        read-back), so a single reading no longer refreshes every entity.
        """
        remove = super().async_add_listener(update_callback, context)
        points = set(context) if isinstance(context, (set, frozenset)) else set()
        for pid in points:
            self._point_callbacks.setdefault(pid, set()).add(update_callback)

        @callback
        def release() -> None:
            remove()
            for pid in points:
                callbacks = self._point_callbacks.get(pid)
                if callbacks is not None:
                    callbacks.discard(update_callback)
                    if not callbacks:
                        del self._point_callbacks[pid]

        return release

    @callback
    def async_update_point_listeners(self, point_ids: Iterable[int]) -> None:
        """Refresh only the entities that show one of these points."""
        targets: set[CALLBACK_TYPE] = set()
        for pid in point_ids:
            targets |= self._point_callbacks.get(pid, set())
        for update_callback in targets:
            update_callback()

    async def _async_update_data(self) -> dict[int, dict]:
        async with self._poll_lock:
            points = await self._fetch_all()
        self._apply_sw_version(points)
        self._update_kpi(points)
        return points

    def _update_kpi(self, points: dict[int, dict]) -> None:
        """Feed the COP tracker one reading per full table. Never allowed to break the update."""
        if self._kpi_failed:
            return
        try:
            if self.kpi is None:
                if not kpi_available(points):
                    return
                # A reading older than ~2.5 update intervals is not part of the same run of data.
                self.kpi = CopTracker(KpiSettings(max_gap_s=max(150.0, 2.5 * self._scan_interval)))

            def value(pid: int) -> float | None:
                point = points.get(pid)
                return scaled_value(pid, point) if point else None

            self.kpi.update(build_sample(time.monotonic(), value))
        except Exception:  # noqa: BLE001 - a bug here must not take the regular sensors down
            self._kpi_failed = True
            _LOGGER.exception("COP calculation stopped after an unexpected error")

    def _apply_sw_version(self, points: dict[int, dict]) -> None:
        """Keep the device's software version in step with the pump (it changes on update)."""
        version = firmware_version(points)
        if not version or version == self._sw_version:
            return
        previous, self._sw_version = self._sw_version, version
        # Entities created later read this dict; the registry entry is updated below.
        self.device_info["sw_version"] = version
        if previous:
            _LOGGER.info("Heat pump software changed from %s to %s", previous, version)
        registry = dr.async_get(self.hass)
        device = registry.async_get_device(identifiers={(DOMAIN, self.serial)})
        if device:
            registry.async_update_device(device.id, sw_version=version)

    async def _fetch_all(self) -> dict[int, dict]:
        try:
            points = await self.api.get_points()
        except NibeAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except NibeApiError as err:
            raise UpdateFailed(str(err)) from err
        # The small device-state call must not throw away a good points table.
        try:
            dev = await self.api.get_device()
        except NibeAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except NibeApiError as err:
            _LOGGER.debug("Could not read device state, keeping the last one: %s", err)
        else:
            if isinstance(dev, dict):
                self.device_state = dev
        try:
            self.alarms = await self.api.get_notifications()
        except NibeApiError:
            self.alarms = []
        return points

    async def async_fast_poll(self, _now=None) -> None:
        """Re-read the chosen points, one small request each, and publish them at once.

        Skipped while a full update is running or the last one failed; one bad round
        never marks the entities unavailable (the regular update decides that).
        """
        if (
            not self.fast_points or not self.data or not self.last_update_success
            or self._poll_lock.locked()
        ):
            return
        async with self._poll_lock:
            fresh: dict[int, dict] = {}
            try:
                async with asyncio.timeout(FAST_POLL_TIMEOUT):
                    for pid in self.fast_points:
                        payload = await self.api.get_point(pid)
                        if is_point_payload(payload, pid):
                            fresh[pid] = payload
            except NibeAuthError:
                self.config_entry.async_start_reauth(self.hass)
                return
            except (NibeApiError, TimeoutError) as err:
                self._fast_failures += 1
                if self._fast_failures == 3:
                    _LOGGER.warning(
                        "Fast polling failed 3 times in a row (%s); the regular update "
                        "keeps running", err,
                    )
                else:
                    _LOGGER.debug("Fast polling failed: %s", err)
            else:
                if self._fast_failures >= 3:
                    _LOGGER.info("Fast polling works again")
                self._fast_failures = 0
            if fresh:
                self.data.update(fresh)
                self.async_update_point_listeners(fresh)

    async def async_set_mode(self, endpoint: str, key: str, value: str) -> None:
        """Set aid/smart mode; the API layer verifies the pump applied it."""
        try:
            state = await self.api.set_mode(endpoint, key, value)
        except NibeApiError as err:
            raise translated_error("mode_failed", endpoint=endpoint, value=value, error=err) from err
        if isinstance(state, dict):
            self.device_state = state
            self.async_update_listeners()
        else:
            await self.async_request_refresh()


def _loaded_coordinators(hass: HomeAssistant) -> list:
    return [
        e.runtime_data for e in hass.config_entries.async_entries(DOMAIN)
        if e.state is ConfigEntryState.LOADED and getattr(e, "runtime_data", None) is not None
    ]


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_SET_AUX):
        return

    async def handle_set_aux(call: ServiceCall) -> None:
        loaded = _loaded_coordinators(hass)
        if not loaded:
            raise translated_error("not_loaded")
        await async_set_aux(loaded[0], call.data["function"], call.data["state"])

    hass.services.async_register(
        DOMAIN, SERVICE_SET_AUX, handle_set_aux, schema=SET_AUX_SCHEMA
    )


def _start_fast_polling(hass: HomeAssistant, entry: ConfigEntry, coordinator: NibeCoordinator) -> None:
    """Schedule the extra single-point reads chosen in the options (off by default)."""
    coordinator.fast_points = selected_point_ids(entry.options, coordinator.data)
    if not coordinator.fast_points:
        return
    seconds = entry.options.get(CONF_FAST_INTERVAL, DEFAULT_FAST_INTERVAL)
    seconds = min(max(int(seconds), MIN_FAST_INTERVAL), MAX_FAST_INTERVAL)
    entry.async_on_unload(async_track_time_interval(
        hass, coordinator.async_fast_poll, timedelta(seconds=seconds),
        name="nibe_local_api fast poll",
    ))
    _LOGGER.info(
        "Fast polling %d point(s) every %d s: %s",
        len(coordinator.fast_points), seconds, coordinator.fast_points,
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    d = entry.data
    # auto_cleanup=False: the session is closed with the config entry, so reloads do not
    # leave their old sessions open until Home Assistant stops.
    session = async_create_clientsession(
        hass, verify_ssl=False, auto_cleanup=False,
        auth=BasicAuth(d[CONF_USERNAME], d[CONF_PASSWORD]),
    )
    entry.async_on_unload(session.close)
    api = NibeLocalApi(session, d[CONF_HOST], d[CONF_PORT], d.get(CONF_HTTPS, True))
    try:
        info = parse_device(await api.get_devices())
    except NibeAuthError as err:
        await session.close()
        raise ConfigEntryAuthFailed(str(err)) from err
    except NibeApiError as err:
        await session.close()
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = NibeCoordinator(hass, entry, api, info)
    await coordinator.async_config_entry_first_refresh()
    data_path = os.path.join(os.path.dirname(__file__), "data.json")
    catalog_data = await hass.async_add_executor_job(load_data, data_path)
    coordinator.infos = build_infos(coordinator.data, catalog_data)

    rows = [_csv_row(pid, i, coordinator.data[pid]) for pid, i in sorted(coordinator.infos.items())]
    await hass.async_add_executor_job(
        _write_csv, hass.config.path("nibe_local_api_points.csv"), rows
    )

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_reload))
    _register_services(hass)
    await async_register_card(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _start_fast_polling(hass, entry, coordinator)
    return True


async def _reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded and not any(
        e.entry_id != entry.entry_id and e.state is ConfigEntryState.LOADED
        for e in hass.config_entries.async_entries(DOMAIN)
    ):
        hass.services.async_remove(DOMAIN, SERVICE_SET_AUX)
    return unloaded
