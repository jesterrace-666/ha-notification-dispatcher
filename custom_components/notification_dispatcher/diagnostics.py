"""Diagnostics support for Notification Dispatcher."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_NOTIFY_TARGETS, CONF_PERSON_ENTITY_ID

TO_REDACT = [CONF_NOTIFY_TARGETS, CONF_PERSON_ENTITY_ID]


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    return {"options": async_redact_data(entry.options, TO_REDACT)}
