"""Notification routing logic."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import time
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_CONTINUE_ON_ERROR,
    ATTR_DATA,
    ATTR_DRY_RUN,
    ATTR_MESSAGE,
    ATTR_RECIPIENTS,
    ATTR_TARGET,
    ATTR_TARGET_ALL,
    ATTR_TITLE,
    ATTR_TYPE,
    CONF_ALLOW_WEEKDAYS,
    CONF_ALLOW_WEEKENDS,
    CONF_DND_ENABLED,
    CONF_DND_END,
    CONF_DND_START,
    CONF_DND_WINDOW,
    CONF_ENABLED_TYPES,
    CONF_GROUP_ID,
    CONF_GROUP_MEMBERS,
    CONF_GROUPS,
    CONF_NAME,
    CONF_NOTIFY_TARGETS,
    CONF_ONLY_WHEN_HOME,
    CONF_PERSON_ENTITY_ID,
    CONF_PROFILE_ID,
    CONF_PROFILES,
    CONF_TARGET_KEY,
    CONF_WEEKDAY_END,
    CONF_WEEKDAY_START,
    CONF_WEEKDAY_WINDOW,
    CONF_WEEKEND_END,
    CONF_WEEKEND_START,
    CONF_WEEKEND_WINDOW,
    DEFAULT_DND_END,
    DEFAULT_DND_START,
    DEFAULT_DND_WINDOW,
    DEFAULT_NOTIFICATION_TYPE,
    DEFAULT_WEEKDAY_END,
    DEFAULT_WEEKDAY_START,
    DEFAULT_WEEKDAY_WINDOW,
    DEFAULT_WEEKEND_WINDOW,
    NOTIFICATION_TYPES,
    TARGET_ALL,
    TYPE_CRITICAL,
    TYPE_INFO,
    TYPE_REMINDER,
    TYPE_WARNING,
)

_LOGGER = logging.getLogger(__name__)
TARGET_ALL_ALIASES = {TARGET_ALL, "alle"}

TYPE_ICONS = {
    TYPE_INFO: "ℹ️",
    TYPE_WARNING: "⚠️",
    TYPE_CRITICAL: "🔥",
    TYPE_REMINDER: "⏰",
}


@dataclass(frozen=True)
class DeliveryDecision:
    """A delivery decision for one profile."""

    should_deliver: bool
    reason: str


class NotificationDispatcher:
    """Dispatch notifications according to person profile rules."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the dispatcher."""
        self.hass = hass
        self.entry = entry

    async def async_send(self, call_data: dict[str, Any]) -> dict[str, Any]:
        """Send a notification according to configured profiles."""
        message = str(call_data[ATTR_MESSAGE]).strip()
        if not message:
            raise ServiceValidationError("Message must not be empty")

        notification_type = str(
            call_data.get(ATTR_TYPE, DEFAULT_NOTIFICATION_TYPE)
        ).lower()
        if notification_type not in NOTIFICATION_TYPES:
            raise ServiceValidationError(
                f"Unsupported notification type: {notification_type}"
            )

        target_keys = _target_keys_from_call(call_data, notification_type)
        profiles = self._select_profiles(target_keys, notification_type)
        if not profiles:
            raise ServiceValidationError("No matching notification profiles configured")

        title = _format_title(notification_type, call_data.get(ATTR_TITLE))
        extra_data = _coerce_payload_data(call_data.get(ATTR_DATA))
        dry_run = bool(call_data.get(ATTR_DRY_RUN, False))
        continue_on_error = bool(call_data.get(ATTR_CONTINUE_ON_ERROR, True))

        result: dict[str, list[dict[str, Any]]] = {
            "sent": [],
            "skipped": [],
            "failed": [],
            "persistent": [],
        }

        if (
            notification_type in {TYPE_WARNING, TYPE_CRITICAL}
            and not dry_run
        ):
            try:
                await self._async_send_persistent_notification(
                    title=title,
                    message=message,
                )
            except HomeAssistantError as err:
                result["failed"].append(
                    {"target": "notify.persistent_notification", "error": str(err)}
                )
                if not continue_on_error:
                    raise
            else:
                result["persistent"].append(
                    {"target": "notify.persistent_notification"}
                )

        for profile in profiles:
            decision = self._delivery_decision(profile, notification_type)
            if not decision.should_deliver:
                result["skipped"].append(
                    {"profile": _profile_name(profile), "reason": decision.reason}
                )
                continue

            payload_data = _deep_merge(
                _default_payload_data(notification_type),
                extra_data,
            )
            await self._async_send_profile(
                result=result,
                profile=profile,
                title=title,
                message=message,
                payload_data=payload_data,
                dry_run=dry_run,
                continue_on_error=continue_on_error,
            )

        _LOGGER.debug("Notification dispatcher result: %s", result)
        return result

    def _select_profiles(
        self, target_keys: list[str], notification_type: str
    ) -> list[dict[str, Any]]:
        """Return profiles matching the requested recipients."""
        profiles = list(self.entry.options.get(CONF_PROFILES, []))

        if notification_type == TYPE_CRITICAL or set(target_keys) & TARGET_ALL_ALIASES:
            return profiles

        matched: list[dict[str, Any]] = []
        matched_keys: set[str] = set()
        requested_keys = set(target_keys)
        group_member_ids, matched_group_keys = self._group_member_ids(requested_keys)

        for profile in profiles:
            keys = {
                str(profile.get(CONF_PROFILE_ID, "")).casefold(),
                str(profile.get(CONF_NAME, "")).casefold(),
                str(profile.get(CONF_PERSON_ENTITY_ID, "")).casefold(),
                _profile_target_key(profile),
            }
            profile_matches = requested_keys & keys
            if profile_matches or profile.get(CONF_PROFILE_ID) in group_member_ids:
                matched.append(profile)
                matched_keys.update(profile_matches)

        if not matched:
            if matched_group_keys:
                raise ServiceValidationError(
                    f"Notification group has no configured people: "
                    f"{', '.join(sorted(matched_group_keys))}"
                )
            raise ServiceValidationError(
                f"Unknown notification target: {', '.join(target_keys)}"
            )

        unknown = requested_keys - matched_keys - matched_group_keys
        if unknown:
            _LOGGER.warning(
                "Skipping unknown notification targets: %s",
                ", ".join(sorted(unknown)),
            )

        return matched

    def _group_member_ids(self, requested_keys: set[str]) -> tuple[set[str], set[str]]:
        """Return profile ids selected by matching groups."""
        member_ids: set[str] = set()
        matched_group_keys: set[str] = set()

        for group in self.entry.options.get(CONF_GROUPS, []):
            group_keys = _group_target_keys(group)
            matches = requested_keys & group_keys
            if not matches:
                continue
            matched_group_keys.update(matches)
            member_ids.update(
                str(member_id)
                for member_id in _ensure_list(group.get(CONF_GROUP_MEMBERS))
                if str(member_id)
            )

        return member_ids, matched_group_keys

    def _delivery_decision(
        self, profile: dict[str, Any], notification_type: str
    ) -> DeliveryDecision:
        """Decide whether a profile should receive the notification."""
        if notification_type == TYPE_CRITICAL:
            return DeliveryDecision(True, "critical")

        enabled_types = set(_ensure_list(profile.get(CONF_ENABLED_TYPES)))
        if notification_type not in enabled_types:
            return DeliveryDecision(False, "type_not_enabled")

        if profile.get(CONF_ONLY_WHEN_HOME, False) and not self._is_home(profile):
            return DeliveryDecision(False, "person_not_home")

        now = dt_util.now()
        now_time = now.time().replace(tzinfo=None)
        is_weekday = now.weekday() < 5

        if is_weekday:
            weekday_window = _profile_time_window(
                profile,
                CONF_WEEKDAY_WINDOW,
                CONF_ALLOW_WEEKDAYS,
                CONF_WEEKDAY_START,
                CONF_WEEKDAY_END,
                DEFAULT_WEEKDAY_WINDOW,
            )
            if weekday_window is None:
                return DeliveryDecision(False, "weekday_disabled")
            if not _time_in_allowed_window(now_time, *weekday_window):
                return DeliveryDecision(False, "outside_weekday_window")
        else:
            weekend_window = _profile_time_window(
                profile,
                CONF_WEEKEND_WINDOW,
                CONF_ALLOW_WEEKENDS,
                CONF_WEEKEND_START,
                CONF_WEEKEND_END,
                DEFAULT_WEEKEND_WINDOW,
            )
            if weekend_window is None:
                return DeliveryDecision(False, "weekend_disabled")
            if not _time_in_allowed_window(now_time, *weekend_window):
                return DeliveryDecision(False, "outside_weekend_window")

        dnd_window = _profile_time_window(
            profile,
            CONF_DND_WINDOW,
            CONF_DND_ENABLED,
            CONF_DND_START,
            CONF_DND_END,
            DEFAULT_DND_WINDOW,
        )
        if dnd_window is not None and _time_in_blocked_window(now_time, *dnd_window):
            return DeliveryDecision(False, "dnd_active")

        return DeliveryDecision(True, "matched")

    def _is_home(self, profile: dict[str, Any]) -> bool:
        """Return whether the configured person is home."""
        person_entity_id = profile.get(CONF_PERSON_ENTITY_ID)
        if not person_entity_id:
            return False

        state = self.hass.states.get(person_entity_id)
        return state is not None and state.state == "home"

    def _profile_targets(self, profile: dict[str, Any]) -> list[str]:
        """Return normalized notify targets for a profile."""
        targets = profile.get(CONF_NOTIFY_TARGETS, [])
        if isinstance(targets, str):
            targets = [targets]

        return [
            _normalize_notify_target(target)
            for target in targets
            if str(target).strip()
        ]

    async def _async_send_profile(
        self,
        *,
        result: dict[str, list[dict[str, Any]]],
        profile: dict[str, Any],
        title: str,
        message: str,
        payload_data: dict[str, Any],
        dry_run: bool,
        continue_on_error: bool,
    ) -> None:
        """Send a notification to all targets of a profile."""
        targets = self._profile_targets(profile)
        if not targets:
            result["skipped"].append(
                {
                    "profile": _profile_name(profile),
                    "reason": "no_notify_targets",
                }
            )
            return

        for target in targets:
            if dry_run:
                sent = {
                    "profile": _profile_name(profile),
                    "target": target,
                    "dry_run": True,
                }
                result["sent"].append(sent)
                continue

            try:
                await self._async_send_to_target(
                    target=target,
                    title=title,
                    message=message,
                    payload_data=payload_data,
                )
            except HomeAssistantError as err:
                failed = {
                    "profile": _profile_name(profile),
                    "target": target,
                    "error": str(err),
                }
                result["failed"].append(failed)
                if not continue_on_error:
                    raise
                _LOGGER.warning(
                    "Failed to send notification to %s for %s: %s",
                    target,
                    _profile_name(profile),
                    err,
                )
            else:
                sent = {"profile": _profile_name(profile), "target": target}
                result["sent"].append(sent)

    async def _async_send_to_target(
        self,
        *,
        target: str,
        title: str,
        message: str,
        payload_data: dict[str, Any],
    ) -> None:
        """Send one notification to a notify service or notify entity."""
        service_data: dict[str, Any] = {"message": message}
        if title:
            service_data["title"] = title

        if self.hass.states.get(target) is not None:
            if payload_data:
                legacy_service = _legacy_notify_service_for_entity(self.hass, target)
                if legacy_service is not None:
                    legacy_data = dict(service_data)
                    legacy_data["data"] = payload_data
                    await self.hass.services.async_call(
                        "notify",
                        legacy_service,
                        legacy_data,
                        blocking=True,
                    )
                    return
                _LOGGER.debug(
                    "Notify entity %s has no compatible legacy service for payload data;"
                    " sending without extra payload",
                    target,
                )

            service_data["entity_id"] = target
            await self.hass.services.async_call(
                "notify",
                "send_message",
                service_data,
                blocking=True,
            )
            return

        if payload_data:
            service_data["data"] = payload_data

        domain, service = target.split(".", 1)
        await self.hass.services.async_call(
            domain,
            service,
            service_data,
            blocking=True,
        )

    async def _async_send_persistent_notification(
        self, *, title: str, message: str
    ) -> None:
        """Send a persistent Home Assistant notification."""
        await self.hass.services.async_call(
            "notify",
            "persistent_notification",
            {"title": title, "message": message},
            blocking=True,
        )


def _normalize_notify_target(target: Any) -> str:
    """Normalize user-provided notify target names."""
    normalized = str(target).strip()
    if "." not in normalized:
        normalized = f"notify.{normalized}"
    if not normalized.startswith("notify."):
        raise ServiceValidationError(
            f"Notify target must start with notify.: {normalized}"
        )
    if normalized == "notify.":
        raise ServiceValidationError(
            "Notify target must include a service or entity name"
        )
    return normalized


def _legacy_notify_service_for_entity(
    hass: HomeAssistant, entity_id: str
) -> str | None:
    """Return a compatible legacy notify service for a notify entity."""
    if not entity_id.startswith("notify."):
        return None

    state = hass.states.get(entity_id)
    if state is None:
        return None

    entity_key = entity_id.split(".", 1)[1]
    candidates: list[str] = []
    for value in (
        state.attributes.get("service"),
        entity_key,
        f"mobile_app_{entity_key}" if not entity_key.startswith("mobile_app_") else "",
    ):
        candidate = str(value or "").strip()
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    for service in candidates:
        if hass.services.has_service("notify", service):
            return service

    return None


def _target_keys_from_call(
    call_data: dict[str, Any],
    notification_type: str,
) -> list[str]:
    """Return the requested target keys from service data."""
    if notification_type == TYPE_CRITICAL:
        return [TARGET_ALL]

    if call_data.get(ATTR_TARGET_ALL) is True:
        return [TARGET_ALL]

    raw_values = _ensure_list(call_data.get(ATTR_TARGET))
    if not raw_values:
        raw_values = _ensure_list(call_data.get(ATTR_RECIPIENTS))
    if not raw_values:
        raise ServiceValidationError(
            "Select at least one recipient or enable all recipients"
        )

    target_keys: list[str] = []
    for raw_value in raw_values:
        target_key = _normalize_target_key(_extract_target_value(raw_value))
        if target_key in {"", *TARGET_ALL_ALIASES}:
            return [TARGET_ALL]
        if target_key not in target_keys:
            target_keys.append(target_key)

    if not target_keys:
        raise ServiceValidationError(
            "Select at least one recipient or enable all recipients"
        )

    return target_keys


def _ensure_list(value: Any) -> list[Any]:
    """Return Home Assistant service data as a list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _extract_target_value(value: Any) -> Any:
    """Extract the underlying value from selector-like dictionaries."""
    if not isinstance(value, dict):
        return value
    if "entity_id" in value:
        entity_value = value["entity_id"]
        if isinstance(entity_value, list):
            return entity_value[0] if entity_value else ""
        return entity_value
    for key in ("value", "id"):
        if key in value:
            return value[key]
    return value


def _profile_target_key(profile: dict[str, Any]) -> str:
    """Return a profile target key, with compatibility for older options."""
    return _normalize_target_key(
        profile.get(CONF_TARGET_KEY) or profile.get(CONF_NAME)
    )


def _group_target_keys(group: dict[str, Any]) -> set[str]:
    """Return all keys that can select a configured group."""
    return {
        key
        for key in {
            str(group.get(CONF_GROUP_ID, "")).casefold(),
            _normalize_target_key(group.get(CONF_NAME)),
            _normalize_target_key(group.get(CONF_TARGET_KEY)),
        }
        if key
    }


def _normalize_target_key(value: Any) -> str:
    """Normalize a target key."""
    return (
        str(value or "")
        .strip()
        .casefold()
        .replace(" ", "_")
        .replace("-", "_")
    )


def _profile_name(profile: dict[str, Any]) -> str:
    """Return the configured person name."""
    return str(
        profile.get(CONF_NAME)
        or profile.get(CONF_PERSON_ENTITY_ID)
        or "Person"
    )


def _format_title(notification_type: str, title: Any) -> str:
    """Prefix the title with the script-compatible type icon."""
    icon = TYPE_ICONS.get(notification_type, "🔔")
    raw_title = str(title or "").strip()
    if not raw_title:
        return icon
    return f"{icon} {raw_title}"


def _profile_time_window(
    profile: dict[str, Any],
    window_key: str,
    enabled_key: str,
    start_key: str,
    end_key: str,
    default_window: str,
    *,
    disabled_value: bool = True,
) -> tuple[Any, Any] | None:
    """Return a compact or legacy profile time window."""
    if window_key in profile:
        return _split_time_window(profile.get(window_key), default_window)

    if profile.get(enabled_key, disabled_value) is False:
        return None

    start = profile.get(start_key)
    end = profile.get(end_key)
    if start and end:
        return start, end

    return _split_time_window(default_window, default_window)


def _split_time_window(value: Any, fallback: str) -> tuple[str, str] | None:
    """Split a compact time window into start and end."""
    raw = str(value or "").strip()
    if not raw:
        return None

    if "-" not in raw:
        raw = fallback

    start, end = raw.split("-", 1)
    return start.strip(), end.strip()


def _parse_time(value: Any, fallback: str) -> time:
    """Parse a Home Assistant time selector value."""
    if isinstance(value, time):
        return value.replace(tzinfo=None)

    raw = str(value or fallback)
    parts = raw.split(":")
    try:
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        second = int(float(parts[2])) if len(parts) > 2 else 0
    except (TypeError, ValueError, IndexError) as err:
        raise ServiceValidationError(f"Invalid time value: {raw}") from err

    return time(hour=hour, minute=minute, second=second)


def _time_in_allowed_window(now_time: time, start: Any, end: Any) -> bool:
    """Return whether now is in an allowed delivery window."""
    start_time = _parse_time(start, DEFAULT_WEEKDAY_START)
    end_time = _parse_time(end, DEFAULT_WEEKDAY_END)

    if start_time == end_time:
        return True
    if start_time < end_time:
        return start_time <= now_time <= end_time
    return now_time >= start_time or now_time <= end_time


def _time_in_blocked_window(now_time: time, start: Any, end: Any) -> bool:
    """Return whether now is in a blocked DND window."""
    start_time = _parse_time(start, DEFAULT_DND_START)
    end_time = _parse_time(end, DEFAULT_DND_END)

    if start_time == end_time:
        return False
    if start_time < end_time:
        return start_time <= now_time <= end_time
    return now_time >= start_time or now_time <= end_time


def _default_payload_data(notification_type: str) -> dict[str, Any]:
    """Return mobile-app friendly defaults for a notification type."""
    if notification_type == TYPE_CRITICAL:
        return {
            "push": {
                "sound": {
                    "name": "default",
                    "critical": 1,
                    "volume": 1.0,
                },
                "interruption-level": "critical",
            },
            "ttl": 0,
            "priority": "high",
            "importance": "high",
        }

    if notification_type == TYPE_WARNING:
        return {
            "priority": "high",
            "importance": "high",
        }

    if notification_type == TYPE_REMINDER:
        return {"tag": "reminder"}

    if notification_type == TYPE_INFO:
        return {}

    return {}


def _coerce_payload_data(value: Any) -> dict[str, Any]:
    """Coerce optional payload data to a dictionary."""
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    if isinstance(value, str) and value.strip().casefold() in {"", "none", "null"}:
        return {}
    return {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge notification data so caller-provided values win."""
    merged = deepcopy(base)
    for key, value in override.items():
        if (
            isinstance(value, dict)
            and isinstance(merged.get(key), dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged
