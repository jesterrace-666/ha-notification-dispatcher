"""Personal availability stored on the existing dispatcher profile."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, callback

from .config_flow_helpers import (
    InvalidTimeWindow,
    _normalize_time_window,
    _window_from_profile,
)
from .const import (
    CONF_ALLOW_WEEKDAYS,
    CONF_ALLOW_WEEKENDS,
    CONF_ALWAYS_NOTIFY,
    CONF_DND_ENABLED,
    CONF_DND_END,
    CONF_DND_START,
    CONF_DND_WINDOW,
    CONF_ENABLED_TYPES,
    CONF_ONLY_WHEN_HOME,
    CONF_PERSON_ENTITY_ID,
    CONF_PROFILE_ID,
    CONF_PROFILES,
    CONF_WEEKDAY_END,
    CONF_WEEKDAY_START,
    CONF_WEEKDAY_WINDOW,
    CONF_WEEKEND_END,
    CONF_WEEKEND_START,
    CONF_WEEKEND_WINDOW,
    DEFAULT_DND_WINDOW,
    DEFAULT_WEEKDAY_WINDOW,
    DEFAULT_WEEKEND_WINDOW,
    DOMAIN,
    OPTIONAL_NOTIFICATION_TYPES,
    TYPE_CRITICAL,
)
from .history import linked_user_id

_CLOCK = r"(?:[01][0-9]|2[0-3]):[0-5][0-9]"
_WINDOW = vol.Any("", vol.All(str, vol.Match(rf"\A{_CLOCK}-{_CLOCK}\Z")))
_SETTINGS = vol.Schema(
    {
        vol.Required(CONF_ALWAYS_NOTIFY): bool,
        vol.Required(CONF_ONLY_WHEN_HOME): bool,
        vol.Required(CONF_WEEKDAY_WINDOW): _WINDOW,
        vol.Required(CONF_WEEKEND_WINDOW): _WINDOW,
        vol.Required(CONF_ENABLED_TYPES): vol.All(
            [vol.In(OPTIONAL_NOTIFICATION_TYPES)],
            vol.Length(max=len(OPTIONAL_NOTIFICATION_TYPES)),
        ),
    },
    extra=vol.PREVENT_EXTRA,
)


def _owned_profiles(hass: HomeAssistant, owner: str) -> list[tuple[ConfigEntry, dict]]:
    matches = []
    if not owner:
        return matches
    for dispatcher in hass.data.get(DOMAIN, {}).values():
        entry = dispatcher.entry
        if entry.state is not ConfigEntryState.LOADED:
            continue
        profiles = entry.options.get(CONF_PROFILES, [])
        for profile in profiles.values() if isinstance(profiles, dict) else profiles:
            if not isinstance(profile, dict) or not profile.get(CONF_PROFILE_ID):
                continue
            person = profile.get(CONF_PERSON_ENTITY_ID)
            if isinstance(person, str) and linked_user_id(hass, person) == owner:
                matches.append((entry, profile))
    return matches


def _snapshot(entry: ConfigEntry, profile: dict) -> dict:
    def window(key, enabled, start, end, default):
        raw = _window_from_profile(profile, key, enabled, start, end, default)
        return _normalize_time_window(raw, default, key)

    values = {
        CONF_ALWAYS_NOTIFY: bool(profile.get(CONF_ALWAYS_NOTIFY)),
        CONF_ONLY_WHEN_HOME: bool(profile.get(CONF_ONLY_WHEN_HOME)),
        CONF_WEEKDAY_WINDOW: window(
            CONF_WEEKDAY_WINDOW,
            CONF_ALLOW_WEEKDAYS,
            CONF_WEEKDAY_START,
            CONF_WEEKDAY_END,
            DEFAULT_WEEKDAY_WINDOW,
        ),
        CONF_WEEKEND_WINDOW: window(
            CONF_WEEKEND_WINDOW,
            CONF_ALLOW_WEEKENDS,
            CONF_WEEKEND_START,
            CONF_WEEKEND_END,
            DEFAULT_WEEKEND_WINDOW,
        ),
        CONF_ENABLED_TYPES: sorted(
            t
            for t in OPTIONAL_NOTIFICATION_TYPES
            if t in profile.get(CONF_ENABLED_TYPES, [])
        ),
    }
    quiet = window(
        CONF_DND_WINDOW,
        CONF_DND_ENABLED,
        CONF_DND_START,
        CONF_DND_END,
        DEFAULT_DND_WINDOW,
    )
    quiet_in_24h = bool(profile.get(CONF_DND_WINDOW) or profile.get(CONF_DND_ENABLED))
    # Bind the edit to the profile that was shown, not to unrelated changes to groups or devices.
    identity = [
        entry.entry_id,
        profile[CONF_PROFILE_ID],
        profile[CONF_PERSON_ENTITY_ID],
        values,
        quiet,
        quiet_in_24h,
    ]
    revision = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    return {
        "state": "ready",
        "revision": revision,
        "settings": values,
        "quiet_window": quiet,
        "quiet_in_24h": quiet_in_24h,
    }


@callback
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/preferences"})
def websocket_preferences(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    matches = _owned_profiles(hass, connection.user.id)
    if len(matches) != 1:
        connection.send_result(
            msg["id"], {"state": "ambiguous" if matches else "unlinked"}
        )
        return
    try:
        result = _snapshot(*matches[0])
    except InvalidTimeWindow:
        connection.send_error(msg["id"], "invalid_profile", "Invalid saved time window")
        return
    connection.send_result(msg["id"], result)


@callback
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/preferences/update",
        vol.Required("revision"): str,
        vol.Required("settings"): dict,
        vol.Optional("clear_quiet_hours"): bool,
    }
)
def websocket_update_preferences(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    matches = _owned_profiles(hass, connection.user.id)
    if len(matches) != 1:
        connection.send_error(
            msg["id"], "profile_unavailable", "No unique personal dispatcher profile"
        )
        return
    entry, profile = matches[0]
    try:
        current = _snapshot(entry, profile)
        settings = _SETTINGS(msg["settings"])
    except (InvalidTimeWindow, vol.Invalid):
        connection.send_error(
            msg["id"],
            "invalid_preferences",
            "Invalid personal notification preferences",
        )
        return
    if msg["revision"] != current["revision"]:
        connection.send_error(
            msg["id"], "preferences_changed", "Personal preferences have changed"
        )
        return
    settings[CONF_ENABLED_TYPES] = sorted(
        {*settings[CONF_ENABLED_TYPES], TYPE_CRITICAL}
    )
    updated = {**profile, **settings}
    if msg.get("clear_quiet_hours") is True and current["quiet_window"]:
        updated[CONF_DND_WINDOW] = ""
        for key in (CONF_DND_ENABLED, CONF_DND_START, CONF_DND_END):
            updated.pop(key, None)
    # No await between authorizing and persisting. Always merge into the latest options.
    original = entry.options[CONF_PROFILES]
    if isinstance(original, dict):
        profiles = {k: updated if p is profile else p for k, p in original.items()}
    else:
        profiles = [updated if p is profile else p for p in original]
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_PROFILES: profiles}
    )
    connection.send_result(msg["id"], _snapshot(entry, updated))
