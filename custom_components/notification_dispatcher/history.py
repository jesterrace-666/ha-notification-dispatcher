"""Private delivery history for authenticated Home Assistant users."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

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
    push: dict[str, Any] | None = None

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
            **({"_push": self.push} if self.push is not None else {}),
        }


@dataclass(frozen=True, slots=True)
class DispatchNote:
    timestamp: str
    kind: str
    title: str
    message: str
    id: str = field(default_factory=lambda: uuid4().hex)


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
        result = []
        for row in self._rows.get(user_id, [])[:HISTORY_LIMIT]:
            routes = []
            for route in row["routes"]:
                public = {k: route[k] for k in ("status", "reason", "fallback", "for")}
                if push := route.get("_push"):
                    public.update(
                        {
                            k: push[k]
                            for k in ("read", "repeat", "repeat_reason")
                            if k in push
                        }
                    )
                    if pending := push.get("pending"):
                        public["due"] = pending["at"]
                routes.append(public)
            result.append(
                {k: row[k] for k in ("timestamp", "type", "title", "message")}
                | {"routes": routes}
            )
        return result

    def receipts(self, owner: str | None = None) -> Iterator[tuple[str, dict, dict]]:
        for account in self._rows if owner is None else (owner,):
            for row in self._rows.get(account, ()):
                for route in row["routes"]:
                    if push := route.get("_push"):
                        yield account, row, push

    def record(
        self, rows: list[Delivery], note: DispatchNote, *, stage: bool = False
    ) -> None:
        if self._closed:
            return
        by_owner: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for route in rows:
            if route.owner:
                by_owner[route.owner].append(route.private_result())
        for owner, routes in by_owner.items():
            items = self._rows.setdefault(owner, [])
            entry = next((item for item in items if item.get("_id") == note.id), None)
            if entry is None:
                entry = {
                    "_id": note.id,
                    "timestamp": note.timestamp,
                    "type": note.kind,
                    "title": note.title,
                    "message": note.message,
                    "routes": [],
                }
                items.append(entry)
            if stage:
                # A phone can answer before another recipient's notify call returns.
                for route in routes:
                    entry["routes"] = [
                        r
                        for r in entry["routes"]
                        if r.get("_push") is not route["_push"]
                    ]
                    entry["routes"].append(route)
            else:
                entry["routes"] = routes
            # Concurrent sends can finish in a different order than they started.
            items.sort(key=lambda item: item["timestamp"], reverse=True)
        if by_owner:
            self.changed()

    def changed(self) -> None:
        if self._closed:
            return
        for items in self._rows.values():
            items[HISTORY_LIMIT:] = [
                row
                for row in items[HISTORY_LIMIT:]
                if any(r.get("_push", {}).get("pending") for r in row["routes"])
            ]
        self._changed = True
        self.store.async_delay_save(lambda: self._rows, 1)

    async def async_flush(self) -> None:
        if not self._closed:
            self._changed = True
            await self.store.async_save(self._rows)

    async def async_close(self) -> None:
        self._closed = True
        if self._changed:
            await self.store.async_save(self._rows)
