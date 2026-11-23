"""Notification Verlauf panel and its current-user-only WebSocket endpoint."""

from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .history import HISTORY_LIMIT
from .preferences import websocket_preferences, websocket_update_preferences

PANEL_PATH = "notification-verlauf"
PANEL_NAME = "notification-dispatcher-history"
ASSET_URL = "/notification_dispatcher_static/history.js"


async def async_setup_panel_api(hass: HomeAssistant) -> None:
    """Only the static UI code is served over HTTP, never any account data."""
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                ASSET_URL, str(Path(__file__).with_name("history-panel.js")), False
            ),
            StaticPathConfig(
                "/notification_dispatcher_static/availability.js",
                str(Path(__file__).with_name("availability.js")),
                False,
            ),
        ]
    )
    websocket_api.async_register_command(hass, websocket_history)
    websocket_api.async_register_command(hass, websocket_preferences)
    websocket_api.async_register_command(hass, websocket_update_preferences)


async def async_show_panel(hass: HomeAssistant) -> None:
    if not frontend.async_panel_exists(hass, PANEL_PATH):
        await panel_custom.async_register_panel(
            hass,
            PANEL_PATH,
            PANEL_NAME,
            sidebar_title="Notification Verlauf",
            sidebar_icon="mdi:message-text-clock-outline",
            module_url=ASSET_URL,
            require_admin=False,
        )


@callback
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/history"})
def websocket_history(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """The session determines the owner; there is no selector or admin override."""
    rows = [
        row
        for dispatcher in hass.data.get(DOMAIN, {}).values()
        if dispatcher.history is not None
        for row in dispatcher.history.for_user(connection.user.id)
    ]
    rows.sort(key=lambda row: row["timestamp"], reverse=True)
    connection.send_result(msg["id"], rows[:HISTORY_LIMIT])


def hide_panel(hass: HomeAssistant) -> None:
    frontend.async_remove_panel(hass, PANEL_PATH, warn_if_unknown=False)
