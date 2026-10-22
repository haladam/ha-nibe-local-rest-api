"""Serves the bundled Lovelace card and loads it in the dashboard.

The card (frontend/nibe-plant-card.js) finds this integration's entities by NIBE point id, so it
needs no resource entry and no entity configuration. Registering it is a convenience: if anything
here fails the integration itself is not affected, the card just is not available.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from typing import Any

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CARD_FILE = "nibe-plant-card.js"
CARD_URL = f"/{DOMAIN}/{CARD_FILE}"
_REGISTERED = f"{DOMAIN}_card_registered"
_LOCK = f"{DOMAIN}_card_lock"


def card_path() -> str:
    return os.path.join(os.path.dirname(__file__), "frontend", CARD_FILE)


def _content_hash(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha1(f.read()).hexdigest()[:10]


async def async_register_card(hass: Any) -> bool:
    """Make the card available once per Home Assistant run. Never raises."""
    # several config entries are set up at the same time: the lock makes the second wait for the first
    async with hass.data.setdefault(_LOCK, asyncio.Lock()):
        if hass.data.get(_REGISTERED):
            return True
        path = card_path()
        try:
            # imported here so that a Home Assistant without the frontend or http component, or one
            # that renamed these helpers, only loses the card
            from homeassistant.components.frontend import add_extra_js_url
            from homeassistant.components.http import StaticPathConfig

            if getattr(hass, "http", None) is None:
                _LOGGER.debug("No http server, the card %s is not registered", CARD_FILE)
                return False
            version = await hass.async_add_executor_job(_content_hash, path)
            await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, path, False)])
            add_extra_js_url(hass, f"{CARD_URL}?v={version}")
        except Exception as err:  # noqa: BLE001 - the card is optional, the integration must still load
            _LOGGER.warning("Could not register the NIBE plant card (%s: %s)", type(err).__name__, err)
            return False
        hass.data[_REGISTERED] = True
        _LOGGER.debug("Registered %s", CARD_URL)
        return True
