"""The Notification Dispatcher integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_CONTINUE_ON_ERROR,
    ATTR_DATA,
    ATTR_DRY_RUN,
    ATTR_MESSAGE,
    ATTR_RECIPIENTS,
    ATTR_TARGET,
    ATTR_TARGET_ALL,
    ATTR_TITLE,
    ATTR_TYPE,
    DEFAULT_NOTIFICATION_TYPE,
    DOMAIN,
    NAME,
    NOTIFICATION_TYPES,
    SERVICE_SEND,
)
from .dispatcher import NotificationDispatcher

_LOGGER = logging.getLogger(__name__)

SERVICE_SEND_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_TITLE, default=""): cv.string,
        vol.Required(ATTR_MESSAGE): cv.string,
        vol.Optional(ATTR_TYPE, default=DEFAULT_NOTIFICATION_TYPE): vol.In(
            NOTIFICATION_TYPES
        ),
        vol.Optional(ATTR_TARGET_ALL, default=False): cv.boolean,
        vol.Optional(ATTR_TARGET): vol.Any(
            cv.string,
            vol.All(cv.ensure_list, [cv.string]),
        ),
        vol.Optional(ATTR_RECIPIENTS): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(ATTR_DATA): object,
        vol.Optional(ATTR_DRY_RUN, default=False): cv.boolean,
        vol.Optional(ATTR_CONTINUE_ON_ERROR, default=True): cv.boolean,
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Notification Dispatcher."""
    hass.data.setdefault(DOMAIN, {})

    async def async_handle_send(call: ServiceCall) -> dict[str, Any]:
        """Handle the send action."""
        dispatcher = _get_dispatcher(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
        result = await dispatcher.async_send(_normalize_call_data(call.data))
        if result["failed"]:
            _LOGGER.warning("Notification Dispatcher had failed targets: %s", result)
        return result

    if not hass.services.has_service(DOMAIN, SERVICE_SEND):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SEND,
            async_handle_send,
            schema=SERVICE_SEND_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Notification Dispatcher from a config entry."""
    if entry.title != NAME:
        hass.config_entries.async_update_entry(entry, title=NAME)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = NotificationDispatcher(
        hass, entry
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return True


def _get_dispatcher(
    hass: HomeAssistant, config_entry_id: str | None
) -> NotificationDispatcher:
    """Return the requested loaded dispatcher."""
    domain_data: dict[str, Any] = hass.data.setdefault(DOMAIN, {})

    if config_entry_id:
        entry = hass.config_entries.async_get_entry(config_entry_id)
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError("Notification Dispatcher entry not found")
        if entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError("Notification Dispatcher entry is not loaded")
        return domain_data[entry.entry_id]

    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED and entry.entry_id in domain_data:
            return domain_data[entry.entry_id]

    raise ServiceValidationError("No loaded Notification Dispatcher entry found")


def _normalize_call_data(call_data: dict[str, Any]) -> dict[str, Any]:
    """Normalize service call data before dispatching."""
    normalized = dict(call_data)
    raw_payload = normalized.get(ATTR_DATA)
    if raw_payload is None:
        normalized.pop(ATTR_DATA, None)
        return normalized

    if isinstance(raw_payload, str):
        if raw_payload.strip().casefold() in {"", "none", "null"}:
            normalized.pop(ATTR_DATA, None)
            return normalized

    if isinstance(raw_payload, dict):
        return normalized

    _LOGGER.debug(
        "Ignoring unsupported notification_dispatcher.send data payload type: %s",
        type(raw_payload).__name__,
    )
    normalized.pop(ATTR_DATA, None)
    return normalized
