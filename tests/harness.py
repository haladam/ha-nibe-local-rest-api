"""Minimal stand-ins for Home Assistant so the integration's own logic can be exercised."""
import sys, types, asyncio, importlib
from unittest.mock import MagicMock
from typing import Generic, TypeVar

T = TypeVar("T")

def mod(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items(): setattr(m, k, v)
    sys.modules[name] = m
    return m

import json as _json
from paths import SRC
EN_JSON = SRC + "/translations/en.json"
class HomeAssistantError(Exception):
    """Like HA's: with a translation key the message is looked up (and falls back to the key)."""
    def __init__(self, *args, translation_domain=None, translation_key=None, translation_placeholders=None):
        super().__init__(*args)
        self.translation_domain, self.translation_key = translation_domain, translation_key
        self.translation_placeholders = translation_placeholders
    def __str__(self):
        if self.translation_key:
            try:
                message = _json.load(open(EN_JSON, encoding="utf-8"))["exceptions"][self.translation_key]["message"]
                return message.format(**(self.translation_placeholders or {}))
            except Exception:
                return self.translation_key
        return super().__str__()
class ConfigEntryAuthFailed(Exception): pass
class ConfigEntryNotReady(Exception): pass
class UpdateFailed(Exception): pass

class DataUpdateCoordinator(Generic[T]):
    def __init__(self, hass, logger, *, name=None, config_entry=None, update_interval=None):
        self.hass, self.data = hass, None
        self.refreshes = 0; self.listener_updates = 0; self._listeners = {}
    async def async_request_refresh(self): self.refreshes += 1
    def async_add_listener(self, update_callback, context=None):
        key = object(); self._listeners[key] = (update_callback, context)
        return lambda: self._listeners.pop(key, None)
    def async_update_listeners(self):
        self.listener_updates += 1
        for cb, _ in list(self._listeners.values()): cb()

class CoordinatorEntity(Generic[T]):
    def __init__(self, coordinator, context=None):
        self.coordinator, self.coordinator_context = coordinator, context
    @property
    def available(self): return True

class ConfigEntryState:
    LOADED = "loaded"; SETUP_IN_PROGRESS = "setup"

class EntityCategory:
    DIAGNOSTIC = "diagnostic"; CONFIG = "config"

class _Any(types.ModuleType):
    def __getattr__(self, n):
        if n.startswith("__"): raise AttributeError(n)
        return MagicMock(name=n)

def install():
    mod("aiohttp", ClientSession=object, ClientError=Exception, BasicAuth=MagicMock)
    for n in ["homeassistant", "homeassistant.components", "homeassistant.helpers", "homeassistant.components.sensor"]:
        sys.modules[n] = _Any(n)
    mod("homeassistant.exceptions", HomeAssistantError=HomeAssistantError,
        ConfigEntryAuthFailed=ConfigEntryAuthFailed, ConfigEntryNotReady=ConfigEntryNotReady)
    mod("homeassistant.const", EntityCategory=EntityCategory, CONF_HOST="host", CONF_PASSWORD="password",
        CONF_PORT="port", CONF_USERNAME="username", Platform=MagicMock())
    mod("homeassistant.config_entries", ConfigEntry=object, ConfigEntryState=ConfigEntryState)
    mod("homeassistant.core", HomeAssistant=object, ServiceCall=object, callback=lambda f: f, CALLBACK_TYPE=object)
    mod("homeassistant.helpers.update_coordinator", DataUpdateCoordinator=DataUpdateCoordinator,
        CoordinatorEntity=CoordinatorEntity, UpdateFailed=UpdateFailed)
    mod("homeassistant.helpers.entity_registry", RegistryEntryDisabler=MagicMock(), async_get=MagicMock())
    sys.modules["homeassistant.helpers"].entity_registry = sys.modules["homeassistant.helpers.entity_registry"]
    for n in ["homeassistant.helpers.config_validation", "homeassistant.helpers.aiohttp_client",
              "homeassistant.helpers.device_registry", "homeassistant.helpers.event",
              "homeassistant.helpers.selector"]:
        sys.modules[n] = _Any(n)
    sys.modules["homeassistant.helpers.device_registry"].DeviceInfo = dict  # a TypedDict in HA
    sys.modules["voluptuous"] = _Any("voluptuous")
    pkg = types.ModuleType("nibe_local_api"); pkg.__path__ = [SRC]
    sys.modules["nibe_local_api"] = pkg
    return importlib.import_module("nibe_local_api")
