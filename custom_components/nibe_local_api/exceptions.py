"""Translatable errors: the text lives in translations/<language>.json under "exceptions"."""
from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN


def translated_error(key: str, **placeholders: object) -> HomeAssistantError:
    """A HomeAssistantError whose message Home Assistant looks up by key."""
    return HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders={name: str(value) for name, value in placeholders.items()},
    )
