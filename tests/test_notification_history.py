"""Privacy, routing outcomes and lifecycle of the Notification Verlauf."""

from datetime import datetime, timezone
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.components import frontend, persistent_notification
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_component import DATA_INSTANCES

from custom_components.notification_dispatcher import (
    async_remove_entry,
    async_setup,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.notification_dispatcher.const import DOMAIN
from custom_components.notification_dispatcher.history import NotificationHistory
from custom_components.notification_dispatcher.panel import (
    PANEL_PATH,
    websocket_history,
)


class HistoryTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.hass = HomeAssistant(tmp.name)
        self.hass.http = AsyncMock()
        self.hass.config_entries = Mock()
        self.hass.config_entries.async_forward_entry_setups = AsyncMock()
        self.hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
        self.entities = {}
        self.pushes = {}
        self.profiles = []
        for name in ("Linda", "Johannes", "Mara"):
            key = name.lower()
            entity = "person." + key
            self.entities[entity] = SimpleNamespace(
                extra_state_attributes={"user_id": key}
            )
            self.profiles.append(
                {
                    "id": key,
                    "name": name,
                    "person_entity_id": entity,
                    "notify_targets": ["notify." + key],
                    "always_notify": True,
                    "enabled_types": ["info", "warning", "reminder"],
                }
            )
            self.pushes[key] = []

            @callback
            def receive(call, messages=self.pushes[key]):
                messages.append(dict(call.data))

            self.hass.services.async_register("notify", key, receive)
        self.hass.data[DATA_INSTANCES] = {
            "person": SimpleNamespace(get_entity=self.entities.get)
        }
        self.fallback = {
            "group_id": "system_fallback",
            "name": "Fallback",
            "target_key": "fallback",
            "group_members": ["johannes"],
        }
        self.entry = SimpleNamespace(
            entry_id="test",
            domain=DOMAIN,
            title="Notification Dispatcher",
            state=ConfigEntryState.LOADED,
            options={"profiles": self.profiles, "groups": [self.fallback]},
        )
        self.hass.config_entries.async_entries.return_value = [self.entry]
        await persistent_notification.async_setup(self.hass, {})
        await async_setup(self.hass, {})
        await async_setup_entry(self.hass, self.entry)
        self.addAsyncCleanup(self.close)

    async def close(self):
        if self.entry.entry_id in self.hass.data[DOMAIN]:
            await async_unload_entry(self.hass, self.entry)

    async def send(self, target="linda", **fields):
        return await self.hass.services.async_call(
            DOMAIN,
            "send",
            {
                "target": target,
                "title": "Büro",
                "message": "Hohe Luftfeuchtigkeit",
                **fields,
            },
            blocking=True,
            return_response=True,
        )

    def rows(self, user, admin=False, **extra):
        connection = SimpleNamespace(
            user=SimpleNamespace(id=user, is_admin=admin), send_result=Mock()
        )
        websocket_history(
            self.hass, connection, {"id": 9, "type": DOMAIN + "/history", **extra}
        )
        return connection.send_result.call_args.args[1]

    async def test_home_rule_fallback_and_account_bound_reads(self):
        self.profiles[0]["only_when_home"] = True
        await self.send()
        own = self.rows("linda")[0]["routes"]
        self.assertEqual(
            own,
            [
                {
                    "status": "blocked",
                    "reason": "person_not_home",
                    "fallback": "sent",
                    "for": [],
                }
            ],
        )
        self.assertEqual(self.pushes["linda"], [])
        self.assertTrue(self.pushes["johannes"][0]["title"].startswith("FB: @Linda "))
        self.assertNotIn("Persoenlich", self.pushes["johannes"][0]["title"])
        self.assertEqual(
            self.rows("johannes")[0]["routes"],
            [{"status": "sent", "reason": None, "fallback": None, "for": ["Linda"]}],
        )
        self.assertEqual(self.rows("mara", admin=True, user_id="linda"), [])
        self.assertEqual(self.rows("unlinked"), [])

    async def test_dnd_time_and_type_record_actual_reason(self):
        monday = datetime(2026, 11, 23, 12, tzinfo=timezone.utc)
        self.profiles[0].update(
            always_notify=False, weekday_window="08:00-22:00", dnd_window="11:00-13:00"
        )
        self.fallback["group_members"] = []
        with patch(
            "custom_components.notification_dispatcher.dispatcher.dt_util.now",
            return_value=monday,
        ):
            await self.send()
            self.assertEqual(self.rows("linda")[0]["routes"][0]["reason"], "dnd_active")
            self.profiles[0]["weekday_window"] = "08:00-10:00"
            await self.send()
            self.assertEqual(
                self.rows("linda")[0]["routes"][0]["reason"], "outside_weekday_window"
            )
        self.assertEqual(self.rows("linda")[0]["routes"][0]["fallback"], "empty")
        self.profiles[0]["enabled_types"] = []
        await self.send()
        self.assertIsNone(self.rows("linda")[0]["routes"][0]["fallback"])
        self.assertEqual(
            self.rows("linda")[0]["routes"][0]["reason"], "type_not_enabled"
        )

    async def test_group_and_all_do_not_expose_other_routes_or_repeat_push(self):
        self.entry.options["groups"].append(
            {"name": "Team", "group_members": ["linda", "mara"]}
        )
        self.profiles[0]["only_when_home"] = self.profiles[2]["only_when_home"] = True
        await self.send("team")
        self.assertEqual(
            self.rows("johannes")[0]["routes"][0]["for"], ["Linda", "Mara"]
        )
        self.assertTrue(
            self.pushes["johannes"][0]["title"].startswith("FB: @Linda +1 ")
        )
        self.assertEqual(len(self.rows("linda")[0]["routes"]), 1)
        await self.send("alle")
        self.assertEqual(len(self.pushes["johannes"]), 2)
        self.assertNotIn("FB:", self.pushes["johannes"][-1]["title"])
        self.assertEqual(self.rows("mara")[0]["routes"][0]["fallback"], "already_sent")
        self.assertEqual(self.rows("johannes")[0]["routes"][0]["for"], [])

    async def test_partial_failed_and_interrupted_send(self):
        self.profiles[0]["only_when_home"] = True
        self.profiles[1]["notify_targets"].append("notify.missing")
        await self.send()
        self.assertEqual(self.rows("linda")[0]["routes"][0]["fallback"], "partial")
        self.assertEqual(self.rows("johannes")[0]["routes"][0]["status"], "partial")
        self.profiles[1]["notify_targets"] = ["notify.missing"]
        with self.assertRaises(HomeAssistantError):
            await self.send(continue_on_error=False)
        self.assertEqual(self.rows("johannes")[0]["routes"][0]["status"], "failed")
        self.assertEqual(self.rows("linda")[0]["routes"][0]["fallback"], "failed")
        self.profiles[1]["notify_targets"] = []
        await self.send()
        self.assertEqual(
            self.rows("johannes")[0]["routes"][0]["reason"], "no_notify_targets"
        )
        self.assertEqual(self.rows("linda")[0]["routes"][0]["fallback"], "failed")

    async def test_no_dry_run_or_system_only_and_no_inherited_history(self):
        await self.send("system")
        await self.send(dry_run=True)
        self.assertEqual(self.rows("linda"), [])
        self.hass.states.async_set("person.linda", "home", {"user_id": "mara"})
        await self.send()
        self.assertEqual(self.rows("mara"), [])
        self.entities["person.linda"].extra_state_attributes["user_id"] = "new-account"
        self.assertEqual(self.rows("new-account"), [])
        await self.send(title="New")
        self.assertEqual([r["title"] for r in self.rows("new-account")], ["New"])
        self.entities["person.linda"].extra_state_attributes.clear()
        await self.send(title="Unlinked")
        self.assertEqual(len(self.rows("linda")), 1)
        self.assertEqual(len(self.rows("new-account")), 1)
        self.assertEqual(self.rows("mara"), [])

    async def test_device_error_is_private_and_unattempted_recipient_is_distinct(self):
        @callback
        def disconnected(call):
            raise ConnectionError("Transport unavailable")

        self.hass.services.async_register("notify", "offline", disconnected)
        self.profiles[0]["notify_targets"] = ["notify.offline"]
        with self.assertRaises(ConnectionError):
            await self.send(["linda", "mara"], continue_on_error=False)
        self.assertEqual(self.rows("linda")[0]["routes"][0]["reason"], "notify_failed")
        self.assertEqual(self.rows("mara")[0]["routes"][0]["status"], "not_attempted")
        self.assertFalse(self.rows("johannes"))
        await self.send(["linda", "mara"])
        self.assertEqual(self.rows("mara")[0]["routes"][0]["status"], "sent")

    async def test_last_fifty_persist_across_reload_and_removed_on_delete(self):
        for n in range(52):
            await self.send(title=str(n))
        await self.send("mara", title="Private")
        self.assertEqual(self.rows("linda")[0]["title"], "51")
        self.assertEqual(self.rows("linda")[-1]["title"], "2")
        self.assertEqual(len(self.rows("linda")), 50)
        self.assertTrue(frontend.async_panel_exists(self.hass, PANEL_PATH))
        await self.close()
        self.assertFalse(frontend.async_panel_exists(self.hass, PANEL_PATH))
        self.assertFalse(self.rows("linda"))
        await async_setup_entry(self.hass, self.entry)
        self.assertEqual(len(self.rows("linda")), 50)
        self.assertEqual([r["title"] for r in self.rows("mara")], ["Private"])
        await self.close()
        await async_remove_entry(self.hass, self.entry)
        check = NotificationHistory(self.hass, self.entry.entry_id)
        await check.async_load()
        self.assertEqual(check.for_user("linda"), [])
