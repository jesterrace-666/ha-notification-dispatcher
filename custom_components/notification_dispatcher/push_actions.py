"""Recipient-bound Companion notification buttons and durable personal reminders."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from secrets import token_hex
from typing import TYPE_CHECKING, Any

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.start import async_at_started
from homeassistant.util import dt as dt_util

from .const import CONF_PERSON_ENTITY_ID, CONF_PROFILE_ID
from .history import Delivery, NotificationHistory

if TYPE_CHECKING:
    from .dispatcher import NotificationDispatcher

_LOGGER = logging.getLogger(__name__)
EVENT_ACTION = "mobile_app_notification_action"
PREFIX = "ND1:"
DELAYS = ("5", "30", "60")


@dataclass(frozen=True, slots=True)
class Endpoint:
    service: str
    entry_id: str
    owner: str
    os: str


def endpoint(hass: HomeAssistant, target: str) -> Endpoint | None:
    """Resolve only a single, currently registered Companion device."""
    mobile = hass.data.get("mobile_app", {})
    services = getattr(mobile.get("notify"), "registered_targets", {})
    registrations = mobile.get("config_entries", {})
    if not services or not target.startswith("notify."):
        return None
    name = target.removeprefix("notify.")
    if hass.states.get(target) is not None:
        entity = er.async_get(hass).async_get(target)
        if entity is None or entity.platform != "mobile_app":
            return None
        name = next(
            (
                s
                for s, webhook in services.items()
                if (reg := registrations.get(webhook))
                and reg.entry_id == entity.config_entry_id
            ),
            "",
        )
    reg = registrations.get(services.get(name))
    if reg is None or not hass.services.has_service("notify", name):
        return None
    return Endpoint(
        name,
        reg.entry_id,
        reg.data.get("user_id", ""),
        str(reg.data.get("os_name", "")).lower(),
    )


def _buttons(
    device: Endpoint, language: str, data: dict, *, menu: bool = False
) -> tuple[dict, dict] | None:
    if device.os not in {"android", "ios", "ipados"}:
        return None
    existing = [] if menu else data.get("actions", [])
    if not isinstance(existing, list):
        return None
    if menu:
        verbs = DELAYS
    elif device.os == "android":
        verbs = ("read", "menu")
    else:
        verbs = ("read", *DELAYS)
    limit = 3 if device.os == "android" else 4
    verbs = verbs[: max(0, limit - len(existing))]
    if not verbs:
        return None
    de = language.lower().startswith("de")
    labels = {
        "read": "Gelesen" if de else "Mark read",
        "menu": "Erinnern ..." if de else "Remind me ...",
    }
    token = token_hex(16)
    actions = [
        {
            "action": f"{PREFIX}{token}:{v}",
            "title": labels.get(v, f"{v} Min." if de else f"{v} min"),
        }
        for v in verbs
    ]
    return data | {"actions": [*existing, *actions]}, {
        "token": token,
        "verbs": list(verbs),
        "registration": device.entry_id,
    }


def _is_notification(message: str) -> bool:
    return not message.startswith("command_") and message not in {
        "clear_notification",
        "remove_channel",
        "request_location_update",
        "TTS",
    }


class PushActions:
    def __init__(
        self, dispatcher: NotificationDispatcher, history: NotificationHistory
    ) -> None:
        self.dispatcher = dispatcher
        self.hass = dispatcher.hass
        self.history = history
        self._lock = asyncio.Lock()
        self._timer: Callable[[], None] | None = None
        self._unsub: list[Callable[[], None]] = []
        self._started = self._closed = False

    def start(self) -> None:
        self._unsub.append(self.hass.bus.async_listen(EVENT_ACTION, self._on_action))
        self._unsub.append(async_at_started(self.hass, self._on_start))

    @callback
    def _on_start(self, hass: HomeAssistant) -> None:
        self._started = True
        self._schedule()

    async def async_close(self) -> None:
        self._closed = True
        for unsubscribe in self._unsub:
            unsubscribe()
        self._cancel_timer()
        async with self._lock:
            pass  # Let an in-flight handoff finish before closing its private store.

    async def async_send_initial(
        self, route: Delivery, target: str, title: str, message: str, data: dict
    ) -> bool:
        """Return False to use the unchanged non-actionable notify path."""
        if self._closed or not route.owner or not _is_notification(message):
            return False
        device = endpoint(self.hass, target)
        if device is None or device.owner != route.owner:
            return False
        prepared = _buttons(device, self.hass.config.language, data)
        if prepared is None:
            return False
        payload, ticket = prepared
        await self._send(device, title, message, payload)
        if route.push is None:
            route.push = {
                "profile": route.profile[CONF_PROFILE_ID],
                "person": route.profile[CONF_PERSON_ENTITY_ID],
                "title": title,
                "data": data,
                "devices": {},
            }
        route.push["devices"][target] = ticket
        return True

    async def _send(
        self, device: Endpoint, title: str, message: str, data: dict
    ) -> None:
        await self.hass.services.async_call(
            "notify",
            device.service,
            {"title": title, "message": message, "data": data},
            blocking=True,
        )

    async def _on_action(self, event: Event) -> None:
        value = event.data.get("action")
        owner = event.context.user_id
        if not owner or not isinstance(value, str) or not value.startswith(PREFIX):
            return
        token, _, verb = value[len(PREFIX) :].partition(":")
        async with self._lock:
            if self._closed:
                return
            for _, row, push in self.history.receipts(owner):
                for target, ticket in push["devices"].items():
                    if (
                        ticket["token"] != token
                        or verb not in ticket["verbs"]
                        or push.get("read")
                    ):
                        continue
                    if verb == "read":
                        push["read"] = True
                        push.pop("pending", None)
                    elif ticket.get("used"):
                        return
                    elif verb == "menu":
                        ticket["used"] = True
                        await self._reissue(owner, row, push, target, menu=True)
                    elif verb in DELAYS:
                        at = dt_util.utcnow() + timedelta(minutes=int(verb))
                        # One choice per delivery, even with duplicate events or multiple phones.
                        for previous in push["devices"].values():
                            previous["used"] = True
                        push["pending"] = {"at": at.isoformat(), "target": target}
                        push.pop("repeat", None)
                        push.pop("repeat_reason", None)
                    else:
                        return
                    self.history.changed()
                    await self.history.async_flush()
                    self._schedule()
                    return

    def _cancel_timer(self) -> None:
        if self._timer:
            self._timer()
            self._timer = None

    def _schedule(self) -> None:
        self._cancel_timer()
        if self._closed or not self._started:
            return
        due = min(
            (
                p["pending"]["at"]
                for _, _, p in self.history.receipts()
                if p.get("pending")
            ),
            default=None,
        )
        if due:
            self._timer = async_track_point_in_utc_time(
                self.hass, self.async_due, datetime.fromisoformat(due)
            )

    async def async_due(self, now: datetime) -> None:
        async with self._lock:
            if self._closed:
                return
            try:
                for owner, row, push in list(self.history.receipts()):
                    pending = push.get("pending")
                    if not pending or datetime.fromisoformat(pending["at"]) > now:
                        continue
                    # Claim durably before the external call: a restart must not send it twice.
                    del push["pending"]
                    push["repeat"] = "interrupted"
                    await self.history.async_flush()
                    if self._closed:
                        break
                    await self._reissue(owner, row, push, pending["target"], menu=False)
                    self.history.changed()
                    await self.history.async_flush()
            finally:
                self._schedule()

    async def _reissue(
        self, owner: str, row: dict, push: dict, target: str, *, menu: bool
    ) -> None:
        reason = self.dispatcher.personal_push_denial(push, owner, row["type"], target)
        device = endpoint(self.hass, target)
        if not reason and (
            device is None
            or device.owner != owner
            or device.entry_id != push["devices"][target]["registration"]
        ):
            reason = "recipient_changed"
        if reason or device is None:
            push.update(repeat="blocked", repeat_reason=reason or "recipient_changed")
            return
        prepared = _buttons(device, self.hass.config.language, push["data"], menu=menu)
        if prepared is None:
            push.update(repeat="blocked", repeat_reason="recipient_changed")
            return
        payload, ticket = prepared
        try:
            await self._send(device, push["title"], row["message"], payload)
        except Exception:  # Notify integrations may raise transport-specific errors.
            _LOGGER.warning("Personal reminder notify call failed for %s", target)
            push.update(repeat="failed", repeat_reason="notify_failed")
        else:
            push["devices"][target] = ticket
            if not menu:
                push["repeat"] = "sent"
            push.pop("repeat_reason", None)
