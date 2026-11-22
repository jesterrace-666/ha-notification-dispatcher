"""Routing regressions for the Home Assistant notification panel."""

from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import Mock

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback

from custom_components.notification_dispatcher import async_setup
from custom_components.notification_dispatcher.const import DOMAIN
from custom_components.notification_dispatcher.dispatcher import NotificationDispatcher
from custom_components.notification_dispatcher.sensor import (
    async_setup_entry as setup_targets,
)


class SystemNotificationTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.hass = HomeAssistant(tmp.name)
        self.pushes = []
        self.bell_events = []
        self.person = {
            "id": "j",
            "name": "Johannes",
            "person_entity_id": "person.johannes",
            "notify_targets": ["notify.mobile_app_phone"],
            "always_notify": True,
            "enabled_types": ["info", "warning", "reminder"],
        }
        self.entry = SimpleNamespace(
            domain=DOMAIN,
            entry_id="dispatcher",
            state=ConfigEntryState.LOADED,
            options={"profiles": [self.person], "groups": []},
        )
        self.hass.config_entries = Mock()
        self.hass.config_entries.async_entries.return_value = [self.entry]

        @callback
        def record_bell(update_type, notifications):
            self.bell_events.extend(notifications.values())

        @callback
        def record_push(call):
            self.pushes.append(dict(call.data))

        await persistent_notification.async_setup(self.hass, {})
        self.addCleanup(
            persistent_notification.async_register_callback(self.hass, record_bell)
        )
        self.hass.services.async_register("notify", "mobile_app_phone", record_push)
        entities = []
        await setup_targets(self.hass, self.entry, entities.extend)
        for entity in entities:
            key = entity.extra_state_attributes["dispatcher_target_key"]
            self.hass.states.async_set(
                f"sensor.{key}_target",
                entity.native_value,
                entity.extra_state_attributes,
            )
        await async_setup(self.hass, {})
        self.hass.data[DOMAIN][self.entry.entry_id] = NotificationDispatcher(
            self.hass, self.entry
        )

    async def send(self, *, entities=None, **fields):
        return await self.hass.services.async_call(
            DOMAIN,
            "send",
            {"title": "Update", "message": "Version 1", **fields},
            target={"entity_id": entities} if entities is not None else None,
            blocking=True,
            return_response=True,
        )

    async def test_bell_only_and_additional_push_update_same_entry(self):
        result = await self.send(target="system")
        self.assertEqual(self.pushes, [])
        self.assertEqual(len(self.bell_events), 1)
        first = self.bell_events[0]
        self.assertEqual(
            first["notification_id"], result["persistent"][0]["notification_id"]
        )
        self.assertTrue(first["title"].startswith("System "))
        self.assertTrue(first["title"].endswith(" Update"))

        await self.send(
            entities=[
                "sensor.johannes_target",
                "sensor.home_assistant_persistent_target",
            ],
            message="Version 2",
        )
        self.assertEqual(len(self.pushes), 1)
        self.assertIn("Persoenlich", self.pushes[0]["title"])
        self.assertEqual(len(self.bell_events), 2)
        second = self.bell_events[-1]
        self.assertEqual(second["title"], first["title"])
        self.assertEqual(second["notification_id"], first["notification_id"])
        self.assertEqual(second["message"], "Version 2")

    async def test_automatic_system_copy_with_or_without_explicit_target(self):
        self.entry.options["groups"].append({"name": "Admins", "group_members": ["j"]})
        for kind in ("warning", "critical"):
            for targets in (["admins"], ["admins", "system"]):
                with self.subTest(kind=kind, targets=targets):
                    self.bell_events.clear()
                    self.pushes.clear()
                    await self.send(target=targets, type=kind)
                    self.assertEqual(len(self.bell_events), 1)
                    self.assertTrue(self.bell_events[0]["title"].startswith("System "))
                    self.assertEqual(len(self.pushes), 1)
                    self.assertIn(
                        "@Admins" if kind == "warning" else "Alle",
                        self.pushes[0]["title"],
                    )

    async def test_people_only_all_and_explicit_system(self):
        await self.send(target="alle", type="reminder")
        self.assertEqual(self.bell_events, [])
        await self.send(target_all=True, target="system", type="reminder")
        self.assertEqual(len(self.bell_events), 1)
        self.assertEqual(len(self.pushes), 2)
        self.entry.options["profiles"].clear()
        result = await self.send(
            entities="sensor.home_assistant_persistent_target", dry_run=True
        )
        self.assertTrue(result["persistent"][0]["dry_run"])
        self.assertFalse(result["sent"])
        self.assertEqual(len(self.bell_events), 1)
        await self.send(entities="sensor.home_assistant_persistent_target")
        self.assertEqual(len(self.bell_events), 2)
        self.assertEqual(len(self.pushes), 2)

    async def test_saved_notifier_in_fallback_shares_one_system_copy(self):
        self.person["only_when_home"] = True
        self.entry.options["profiles"].append(
            {
                "id": "backup",
                "name": "Backup",
                "notify_targets": [
                    "notify.persistent_notification",
                    "notify.mobile_app_phone",
                ],
            }
        )
        self.entry.options["groups"].append(
            {"target_key": "fallback", "group_members": ["backup"]}
        )
        for kind in ("info", "warning"):
            with self.subTest(kind=kind):
                self.bell_events.clear()
                self.pushes.clear()
                result = await self.send(target="person.johannes", type=kind)
                self.assertEqual(len(self.bell_events), 1)
                self.assertTrue(self.bell_events[0]["title"].startswith("System "))
                self.assertIn("Fallback", self.pushes[0]["title"])
                self.assertEqual(len(result["persistent"]), 1)
