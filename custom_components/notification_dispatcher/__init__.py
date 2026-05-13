"""The Notification Dispatcher integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
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
    ATTR_TARGET,
    ATTR_TITLE,
    ATTR_TYPE,
    BUILD_CODENAME,
    BUILD_SERIES,
    CONF_GROUP_ID,
    CONF_GROUP_MEMBERS,
    CONF_GROUPS,
    CONF_NAME,
    CONF_TARGET_KEY,
    DEFAULT_NOTIFICATION_TYPE,
    DOMAIN,
    NAME,
    NOTIFICATION_TYPES,
    SERVICE_SEND,
    SYSTEM_GROUP_FALLBACK_ID,
    SYSTEM_GROUP_FALLBACK_NAME,
    SYSTEM_GROUP_FALLBACK_TARGET_KEY,
)
from .dispatcher import NotificationDispatcher

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_SEND_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_TITLE, default=""): cv.string,
        vol.Required(ATTR_MESSAGE): cv.string,
        vol.Optional(ATTR_TYPE, default=DEFAULT_NOTIFICATION_TYPE): vol.In(
            NOTIFICATION_TYPES
        ),
        vol.Optional(ATTR_TARGET): vol.Any(
            cv.string,
            vol.All(cv.ensure_list, [cv.string]),
            dict,
        ),
        vol.Optional(ATTR_DATA): object,
        vol.Optional(ATTR_DRY_RUN, default=False): cv.boolean,
        vol.Optional(ATTR_CONTINUE_ON_ERROR, default=True): cv.boolean,
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Notification Dispatcher."""
    hass.data.setdefault(DOMAIN, {})
    _LOGGER.info(
        "Starting %s (%s - %s)",
        NAME,
        BUILD_SERIES,
        BUILD_CODENAME,
    )

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
    normalized_options = _normalized_options(entry.options)
    if entry.title != NAME or normalized_options != entry.options:
        hass.config_entries.async_update_entry(
            entry,
            title=NAME,
            options=normalized_options,
        )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = NotificationDispatcher(
        hass, entry
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False
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


def _normalized_options(options: dict[str, Any]) -> dict[str, Any]:
    """Normalize entry options and ensure built-in groups exist."""
    normalized = dict(options)
    groups = _coerce_mapping_list(normalized.get(CONF_GROUPS, []))
    normalized[CONF_GROUPS] = _ensure_system_groups(groups)
    return normalized


def _coerce_mapping_list(value: Any) -> list[dict[str, Any]]:
    """Return options as a list of dict items."""
    if isinstance(value, dict):
        raw_items: list[Any] = list(value.values())
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = []

    items: list[dict[str, Any]] = []
    for item in raw_items:
        if isinstance(item, dict):
            items.append(item)
    return items


def _ensure_system_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure the non-removable fallback group exists."""
    normalized_groups: list[dict[str, Any]] = []
    fallback_members: list[str] = []

    for group in groups:
        if _is_fallback_group(group):
            fallback_members = [
                str(member)
                for member in group.get(CONF_GROUP_MEMBERS, [])
                if str(member).strip()
            ]
            continue
        normalized_groups.append(group)

    normalized_groups.append(
        {
            CONF_GROUP_ID: SYSTEM_GROUP_FALLBACK_ID,
            CONF_NAME: SYSTEM_GROUP_FALLBACK_NAME,
            CONF_TARGET_KEY: SYSTEM_GROUP_FALLBACK_TARGET_KEY,
            CONF_GROUP_MEMBERS: fallback_members,
        }
    )
    return normalized_groups


def _is_fallback_group(group: dict[str, Any]) -> bool:
    """Return whether a group is the built-in fallback group."""
    if str(group.get(CONF_GROUP_ID, "")).strip() == SYSTEM_GROUP_FALLBACK_ID:
        return True

    target_key = (
        str(group.get(CONF_TARGET_KEY, ""))
        .strip()
        .casefold()
        .replace(" ", "_")
        .replace("-", "_")
    )
    if target_key == SYSTEM_GROUP_FALLBACK_TARGET_KEY:
        return True

    group_name = (
        str(group.get(CONF_NAME, ""))
        .strip()
        .casefold()
        .replace(" ", "_")
        .replace("-", "_")
    )
    return group_name == SYSTEM_GROUP_FALLBACK_TARGET_KEY
