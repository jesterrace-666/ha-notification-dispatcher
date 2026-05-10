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
    CONF_ENABLED_TYPES,
    CONF_NAME,
    CONF_NOTIFY_TARGETS,
    CONF_ONLY_WHEN_HOME,
    CONF_PERSON_ENTITY_ID,
    CONF_PROFILE_ID,
    CONF_PROFILES,
    CONF_WEEKDAY_END,
    CONF_WEEKDAY_START,
    CONF_WEEKEND_END,
    CONF_WEEKEND_START,
    DEFAULT_DND_END,
    DEFAULT_DND_START,
    DEFAULT_NOTIFICATION_TYPE,
    DEFAULT_WEEKDAY_END,
    DEFAULT_WEEKDAY_START,
    DEFAULT_WEEKEND_END,
    DEFAULT_WEEKEND_START,
    NOTIFICATION_TYPES,
    TYPE_CRITICAL,
    TYPE_INFO,
    TYPE_REMINDER,
    TYPE_WARNING,
)

_LOGGER = logging.getLogger(__name__)


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

        profiles = self._select_profiles(call_data)
        if not profiles:
            raise ServiceValidationError("No matching notification profiles configured")

        title = str(call_data.get(ATTR_TITLE) or "")
        extra_data = call_data.get(ATTR_DATA) or {}
        dry_run = bool(call_data.get(ATTR_DRY_RUN, False))
        continue_on_error = bool(call_data.get(ATTR_CONTINUE_ON_ERROR, True))

        result: dict[str, list[dict[str, Any]]] = {
            "sent": [],
            "skipped": [],
            "failed": [],
        }

        for profile in profiles:
            decision = self._delivery_decision(profile, notification_type)
            if not decision.should_deliver:
                result["skipped"].append(
                    {"profile": profile.get(CONF_NAME), "reason": decision.reason}
                )
                continue

            targets = self._profile_targets(profile)
            if not targets:
                result["skipped"].append(
                    {
                        "profile": profile.get(CONF_NAME),
                        "reason": "no_notify_targets",
                    }
                )
                continue

            payload_data = _deep_merge(
                _default_payload_data(notification_type),
                extra_data,
            )

            for target in targets:
                if dry_run:
                    result["sent"].append(
                        {
                            "profile": profile.get(CONF_NAME),
                            "target": target,
                            "dry_run": True,
                        }
                    )
                    continue

                try:
                    await self._async_send_to_target(
                        target=target,
                        title=title,
                        message=message,
                        payload_data=payload_data,
                    )
                except HomeAssistantError as err:
                    result["failed"].append(
                        {
                            "profile": profile.get(CONF_NAME),
                            "target": target,
                            "error": str(err),
                        }
                    )
                    if not continue_on_error:
                        raise
                    _LOGGER.warning(
                        "Failed to send notification to %s for %s: %s",
                        target,
                        profile.get(CONF_NAME),
                        err,
                    )
                else:
                    result["sent"].append(
                        {"profile": profile.get(CONF_NAME), "target": target}
                    )

        _LOGGER.debug("Notification dispatcher result: %s", result)
        return result

    def _select_profiles(self, call_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Return profiles matching the requested recipients."""
        profiles = list(self.entry.options.get(CONF_PROFILES, []))

        if call_data.get(ATTR_TARGET_ALL) is True:
            return profiles

        target = call_data.get(ATTR_TARGET)
        recipients = call_data.get(ATTR_RECIPIENTS)
        if target:
            recipients = target
        elif call_data.get(ATTR_TARGET_ALL) is False and not recipients:
            raise ServiceValidationError(
                "Select at least one target person or enable target_all"
            )

        if not recipients:
            return profiles

        requested = {str(recipient).casefold() for recipient in recipients}
        matched: list[dict[str, Any]] = []
        found: set[str] = set()

        for profile in profiles:
            keys = {
                str(profile.get(CONF_PROFILE_ID, "")).casefold(),
                str(profile.get(CONF_NAME, "")).casefold(),
                str(profile.get(CONF_PERSON_ENTITY_ID, "")).casefold(),
            }
            if keys & requested:
                matched.append(profile)
                found.update(keys & requested)

        missing = requested - found
        if missing:
            raise ServiceValidationError(
                f"Unknown notification recipient(s): {', '.join(sorted(missing))}"
            )

        return matched

    def _delivery_decision(
        self, profile: dict[str, Any], notification_type: str
    ) -> DeliveryDecision:
        """Decide whether a profile should receive the notification."""
        if notification_type == TYPE_CRITICAL:
            return DeliveryDecision(True, "critical")

        enabled_types = set(profile.get(CONF_ENABLED_TYPES, []))
        if notification_type not in enabled_types:
            return DeliveryDecision(False, "type_not_enabled")

        if profile.get(CONF_ONLY_WHEN_HOME, False) and not self._is_home(profile):
            return DeliveryDecision(False, "person_not_home")

        now = dt_util.now()
        now_time = now.time().replace(tzinfo=None)
        is_weekday = now.weekday() < 5

        if is_weekday:
            if not profile.get(CONF_ALLOW_WEEKDAYS, True):
                return DeliveryDecision(False, "weekday_disabled")
            if not _time_in_allowed_window(
                now_time,
                profile.get(CONF_WEEKDAY_START, DEFAULT_WEEKDAY_START),
                profile.get(CONF_WEEKDAY_END, DEFAULT_WEEKDAY_END),
            ):
                return DeliveryDecision(False, "outside_weekday_window")
        else:
            if not profile.get(CONF_ALLOW_WEEKENDS, True):
                return DeliveryDecision(False, "weekend_disabled")
            if not _time_in_allowed_window(
                now_time,
                profile.get(CONF_WEEKEND_START, DEFAULT_WEEKEND_START),
                profile.get(CONF_WEEKEND_END, DEFAULT_WEEKEND_END),
            ):
                return DeliveryDecision(False, "outside_weekend_window")

        if profile.get(CONF_DND_ENABLED, True) and _time_in_blocked_window(
            now_time,
            profile.get(CONF_DND_START, DEFAULT_DND_START),
            profile.get(CONF_DND_END, DEFAULT_DND_END),
        ):
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
        if payload_data:
            service_data["data"] = payload_data

        if self.hass.states.get(target) is not None:
            service_data["entity_id"] = target
            await self.hass.services.async_call(
                "notify",
                "send_message",
                service_data,
                blocking=True,
            )
            return

        domain, service = target.split(".", 1)
        await self.hass.services.async_call(
            domain,
            service,
            service_data,
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
                }
            },
            "ttl": 0,
            "priority": "high",
            "importance": "high",
            "interruption-level": "critical",
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
