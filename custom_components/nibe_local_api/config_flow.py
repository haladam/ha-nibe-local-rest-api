from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from aiohttp import BasicAuth
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict, SelectSelector, SelectSelectorConfig, SelectSelectorMode,
)

from .api import NibeApiError, NibeAuthError, NibeLocalApi, parse_device
from .const import (
    CONF_FAST_INTERVAL, CONF_FAST_POINTS, CONF_HTTPS, CONF_SCAN_INTERVAL, CONF_SEASON_START,
    DEFAULT_FAST_INTERVAL, DEFAULT_PORT, DEFAULT_SCAN_INTERVAL, DEFAULT_SEASON_START, DOMAIN,
    MAX_FAST_INTERVAL, MAX_FAST_POINTS, MIN_FAST_INTERVAL,
)
from .fastpoll import choice_pairs, selected_point_ids

_LOGGER = logging.getLogger(__name__)


async def _probe(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, str]:
    """Connect with these settings and return the device info.

    Raises NibeAuthError for a wrong login and NibeApiError for anything else.
    The temporary session is always closed.
    """
    session = async_create_clientsession(
        hass, verify_ssl=False, auto_cleanup=False,
        auth=BasicAuth(data[CONF_USERNAME], data[CONF_PASSWORD]),
    )
    try:
        api = NibeLocalApi(
            session, data[CONF_HOST], data[CONF_PORT], data.get(CONF_HTTPS, True)
        )
        return parse_device(await api.get_devices())
    finally:
        await session.close()


def _connection_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    d = defaults or {}
    return vol.Schema({
        vol.Required(CONF_HOST, default=d.get(CONF_HOST, vol.UNDEFINED)): str,
        vol.Required(CONF_PORT, default=d.get(CONF_PORT, DEFAULT_PORT)): int,
        vol.Required(CONF_HTTPS, default=d.get(CONF_HTTPS, True)): bool,
        vol.Required(CONF_USERNAME, default=d.get(CONF_USERNAME, vol.UNDEFINED)): str,
        vol.Required(CONF_PASSWORD, default=d.get(CONF_PASSWORD, vol.UNDEFINED)): str,
    })


class NibeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await _probe(self.hass, user_input)
            except NibeAuthError:
                errors["base"] = "invalid_auth"
            except NibeApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001 - show a form instead of a crashed dialog
                _LOGGER.exception("Unexpected error while connecting to the heat pump")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(info["serial"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=info["name"], data=user_input)
        return self.async_show_form(
            step_id="user", data_schema=_connection_schema(user_input), errors=errors
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]):
        """Home Assistant starts this when the pump rejects the saved login."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await _probe(self.hass, {**entry.data, **user_input})
            except NibeAuthError:
                errors["base"] = "invalid_auth"
            except NibeApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001 - show a form instead of a crashed dialog
                _LOGGER.exception("Unexpected error while connecting to the heat pump")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(info["serial"])
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(entry, data_updates=user_input)
        schema = vol.Schema({
            vol.Required(CONF_USERNAME, default=entry.data.get(CONF_USERNAME, "")): str,
            vol.Required(CONF_PASSWORD): str,
        })
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=schema, errors=errors,
            description_placeholders={"name": entry.title},
        )

    async def async_step_reconfigure(self, user_input=None):
        """Change IP address, port or login without removing the integration."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await _probe(self.hass, user_input)
            except NibeAuthError:
                errors["base"] = "invalid_auth"
            except NibeApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001 - show a form instead of a crashed dialog
                _LOGGER.exception("Unexpected error while connecting to the heat pump")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(info["serial"])
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(entry, data_updates=user_input)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_connection_schema(user_input or entry.data),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return NibeOptionsFlow()


def _enabled_point_ids(hass: HomeAssistant, entry, serial: str) -> set[int]:
    """Point ids that have an entity which is not disabled right now."""
    prefix = f"{serial}_"
    out: set[int] = set()
    for ent in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id):
        if ent.disabled_by is None and ent.unique_id.startswith(prefix):
            tail = ent.unique_id[len(prefix):]
            if tail.isdigit():
                out.add(int(tail))
    return out


class NibeOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        errors: dict[str, str] = {}
        options = self.config_entry.options
        # runtime_data exists only while the entry is loaded; without it the form
        # offers the update interval alone and leaves the fast-polling choice untouched.
        coordinator = getattr(self.config_entry, "runtime_data", None)
        known = coordinator.data if coordinator and coordinator.data else {}
        saved = selected_point_ids(options, known) if known else []
        current = user_input if user_input is not None else options

        choices = []
        if coordinator and known:
            choices = choice_pairs(
                coordinator.infos,
                _enabled_point_ids(self.hass, self.config_entry, coordinator.serial),
                saved,
            )

        if user_input is not None:
            chosen = [int(v) for v in user_input.get(CONF_FAST_POINTS, saved)]
            if len(chosen) > MAX_FAST_POINTS:
                errors[CONF_FAST_POINTS] = "too_many_points"
            else:
                data = {**options, **user_input}
                if choices:
                    data[CONF_FAST_POINTS] = chosen
                return self.async_create_entry(data=data)

        fields: dict[Any, Any] = {
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): vol.All(int, vol.Range(min=15, max=3600)),
            vol.Required(
                CONF_SEASON_START,
                default=current.get(CONF_SEASON_START, DEFAULT_SEASON_START),
            ): vol.All(int, vol.Range(min=1, max=12)),
        }
        if choices:
            # The selector rejects a default that is not among its options.
            offered = {str(pid) for pid, _ in choices}
            wanted = user_input.get(CONF_FAST_POINTS, saved) if user_input is not None else saved
            default_points = [str(v) for v in wanted if str(v) in offered]
            fields[vol.Optional(CONF_FAST_POINTS, default=default_points)] = SelectSelector(
                SelectSelectorConfig(
                    options=[SelectOptionDict(value=str(pid), label=label) for pid, label in choices],
                    multiple=True, mode=SelectSelectorMode.DROPDOWN,
                )
            )
            fields[vol.Required(
                CONF_FAST_INTERVAL,
                default=current.get(CONF_FAST_INTERVAL, DEFAULT_FAST_INTERVAL),
            )] = vol.All(int, vol.Range(min=MIN_FAST_INTERVAL, max=MAX_FAST_INTERVAL))
        return self.async_show_form(
            step_id="init", data_schema=vol.Schema(fields), errors=errors,
        )
