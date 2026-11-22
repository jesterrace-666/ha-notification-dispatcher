"""Private delivery history for authenticated Home Assistant users."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_component import DATA_INSTANCES
from homeassistant.helpers.storage import Store

from .const import DOMAIN

HISTORY_LIMIT = 50


def linked_user_id(hass: HomeAssistant, entity_id: str) -> str | None:
    """Read the configured person object, never a name or writable state value."""
    if not entity_id.startswith("person."):
        return None
    component = hass.data.get(DATA_INSTANCES, {}).get("person")
    entity = component.get_entity(entity_id) if component is not None else None
    attributes = entity.extra_state_attributes if entity is not None else None
    user_id = (attributes or {}).get("user_id")
    return user_id if isinstance(user_id, str) and user_id else None


@dataclass(eq=False, slots=True)
class Delivery:
    """Outcome for one addressed profile, independent of its other recipients."""

    profile: dict[str, Any]
    owner: str | None
    origins: tuple[str, ...] = ()
    accepted: int = 0
    failed: int = 0
    reason: str = "not_attempted"
    fallback: str | None = None

    def private_result(self) -> dict[str, Any]:
        if self.accepted:
            status = "partial" if self.failed else "sent"
        elif self.failed or self.reason == "no_notify_targets":
            status = "failed"
        elif self.reason == "not_attempted":
            status = "not_attempted"
        else:
            status = "blocked"
        return {
            "status": status,
            "reason": self.reason if status != "sent" else None,
            "fallback": self.fallback,
            "for": list(self.origins),
        }


class NotificationHistory:
    """Keep bounded, account-owned rows outside entity states and the event bus."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.store = Store[dict](
            hass, 1, f"{DOMAIN}.history.{entry_id}", private=True, atomic_writes=True
        )
        self._rows: dict[str, list[dict[str, Any]]] = {}
        self._changed = False
        self._closed = False

    async def async_load(self) -> None:
        self._rows = await self.store.async_load() or {}

    def for_user(self, user_id: str) -> list[dict[str, Any]]:
        return self._rows.get(user_id, [])[:HISTORY_LIMIT]

    def record(
        self, rows: list[Delivery], timestamp: str, kind: str, title: str, message: str
    ) -> None:
        if self._closed:
            return
        by_owner: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for route in rows:
            if route.owner:
                by_owner[route.owner].append(route.private_result())
        for owner, routes in by_owner.items():
            entry = {
                "timestamp": timestamp,
                "type": kind,
                "title": title,
                "message": message,
                "routes": routes,
            }
            items = self._rows.setdefault(owner, [])
            items.append(entry)
            # Concurrent sends can finish in a different order than they started.
            items.sort(key=lambda item: item["timestamp"], reverse=True)
            del items[HISTORY_LIMIT:]
        if by_owner:
            self._changed = True
            self.store.async_delay_save(lambda: self._rows, 1)

    async def async_close(self) -> None:
        self._closed = True
        if self._changed:
            await self.store.async_save(self._rows)
