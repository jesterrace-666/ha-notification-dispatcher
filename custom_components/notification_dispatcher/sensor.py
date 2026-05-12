"""Recipient selector entities for Notification Dispatcher."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from .const import (
    ATTR_DISPATCHER_GROUP_ID,
    ATTR_DISPATCHER_PROFILE_ID,
    ATTR_DISPATCHER_TARGET_KEY,
    ATTR_DISPATCHER_TARGET_TYPE,
    CONF_GROUP_ID,
    CONF_GROUPS,
    CONF_NAME,
    CONF_PROFILE_ID,
    CONF_PROFILES,
    CONF_TARGET_KEY,
    TARGET_ALL,
    TARGET_TYPE_ALL,
    TARGET_TYPE_GROUP,
    TARGET_TYPE_PROFILE,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up recipient selector entities for one dispatcher entry."""
    entities: list[SensorEntity] = [
        DispatcherRecipientSensor(
            entry_id=entry.entry_id,
            name="Alle",
            object_id="all_recipients",
            target_key=TARGET_ALL,
            target_type=TARGET_TYPE_ALL,
        )
    ]

    for profile in _coerce_mapping_list(entry.options.get(CONF_PROFILES, [])):
        profile_id = str(profile.get(CONF_PROFILE_ID, "")).strip()
        if not profile_id:
            continue
        profile_name = str(profile.get(CONF_NAME) or "Person").strip() or "Person"
        target_key = _normalize_target_key(
            profile.get(CONF_TARGET_KEY) or profile_name
        )
        if not target_key:
            continue

        entities.append(
            DispatcherRecipientSensor(
                entry_id=entry.entry_id,
                name=profile_name,
                object_id=f"recipient_{slugify(profile_name)}_{profile_id[:8]}",
                target_key=target_key,
                target_type=TARGET_TYPE_PROFILE,
                profile_id=profile_id,
            )
        )

    for group in _coerce_mapping_list(entry.options.get(CONF_GROUPS, [])):
        group_id = str(group.get(CONF_GROUP_ID, "")).strip()
        if not group_id:
            continue
        group_name = str(group.get(CONF_NAME) or "Group").strip() or "Group"
        target_key = _normalize_target_key(
            group.get(CONF_TARGET_KEY) or group_name
        )
        if not target_key:
            continue

        entities.append(
            DispatcherRecipientSensor(
                entry_id=entry.entry_id,
                name=group_name,
                object_id=f"group_{slugify(group_name)}_{group_id[:8]}",
                target_key=target_key,
                target_type=TARGET_TYPE_GROUP,
                group_id=group_id,
            )
        )

    async_add_entities(entities)


class DispatcherRecipientSensor(SensorEntity):
    """Representation of one selectable dispatcher recipient."""

    _attr_should_poll = False
    _attr_icon = "mdi:account-arrow-right-outline"
    _attr_native_value = "configured"
    _attr_has_entity_name = True
    _attr_entity_registry_visible_default = False

    def __init__(
        self,
        *,
        entry_id: str,
        name: str,
        object_id: str,
        target_key: str,
        target_type: str,
        profile_id: str | None = None,
        group_id: str | None = None,
    ) -> None:
        """Initialize one dispatcher recipient sensor."""
        self._attr_unique_id = f"{entry_id}_{object_id}"
        self._attr_object_id = object_id
        self._attr_name = name

        attributes: dict[str, Any] = {
            ATTR_DISPATCHER_TARGET_KEY: target_key,
            ATTR_DISPATCHER_TARGET_TYPE: target_type,
        }
        if profile_id:
            attributes[ATTR_DISPATCHER_PROFILE_ID] = profile_id
        if group_id:
            attributes[ATTR_DISPATCHER_GROUP_ID] = group_id

        self._attr_extra_state_attributes = attributes


def _coerce_mapping_list(value: Any) -> list[dict[str, Any]]:
    """Return a list of dict entries from potentially old options formats."""
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


def _normalize_target_key(value: Any) -> str:
    """Normalize a target key."""
    return (
        str(value or "")
        .strip()
        .casefold()
        .replace(" ", "_")
        .replace("-", "_")
    )
