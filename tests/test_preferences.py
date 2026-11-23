"""Self-service availability through the registered HA WebSocket commands."""

from copy import deepcopy
from datetime import UTC, datetime
from types import MappingProxyType, SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import Mock, patch

from homeassistant.components import frontend
from homeassistant.config_entries import ConfigEntries, ConfigEntry, ConfigEntryState
from test_notification_history import DispatcherFixture

from custom_components.notification_dispatcher.config_flow import (
    NotificationDispatcherOptionsFlow,
)
from custom_components.notification_dispatcher.config_flow_helpers import (
    _profile_from_user_input,
)
from custom_components.notification_dispatcher.const import DOMAIN

COMMAND = f"{DOMAIN}/preferences"
MONDAY = datetime(2026, 11, 23, 12, tzinfo=UTC)


class PreferenceTests(DispatcherFixture, IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.hass.config_entries.async_update_entry.side_effect = (
            lambda entry, *, options: setattr(entry, "options", options)
        )
        self.hass.config_entries.async_get_known_entry.return_value = self.entry
        self.dispatcher = self.hass.data[DOMAIN][self.entry.entry_id]

    def ws(self, user, kind=COMMAND, *, admin=False, **payload):
        handler, schema = self.hass.data["websocket_api"][kind]
        connection = SimpleNamespace(
            user=SimpleNamespace(id=user, is_admin=admin),
            send_result=Mock(),
            send_error=Mock(),
        )
        message = {"id": 4, "type": kind, **payload}
        handler(self.hass, connection, schema(message) if schema else message)
        if connection.send_error.called:
            return {"error": connection.send_error.call_args.args[1]}
        return connection.send_result.call_args.args[1]

    def save(self, user, snapshot=None, **changes):
        snapshot = self.ws(user) if snapshot is None else snapshot
        return self.ws(
            user,
            COMMAND + "/update",
            revision=snapshot["revision"],
            settings={**snapshot["settings"], **changes},
        )

    async def test_exposes_only_own_settings_and_no_routing_configuration(self):
        self.profiles[0].update(weekday_window="07:30-16:00", dnd_window="22:00-06:00")
        mine = self.ws("linda")
        self.assertEqual(
            set(mine), {"state", "revision", "settings", "quiet_window", "quiet_in_24h"}
        )
        self.assertEqual(
            set(mine["settings"]),
            {
                "weekday_window",
                "weekend_window",
                "only_when_home",
                "always_notify",
                "enabled_types",
            },
        )
        self.assertEqual(mine["settings"]["weekday_window"], "07:30-16:00")
        self.assertEqual(mine["quiet_window"], "22:00-06:00")
        self.assertNotIn("critical", mine["settings"]["enabled_types"])
        self.assertNotIn("notify.", str(mine))
        self.assertNotIn("person.", str(mine))
        self.assertNotEqual(self.ws("johannes")["revision"], mine["revision"])
        self.assertEqual(self.ws("other", admin=True), {"state": "unlinked"})
        for actor in ("johannes", "unlinked"):
            response = self.ws(
                actor,
                COMMAND + "/update",
                admin=True,
                revision=mine["revision"],
                settings=mine["settings"],
            )
            self.assertIn(
                response["error"], {"preferences_changed", "profile_unavailable"}
            )
        self.assertEqual(self.ws("linda"), mine)

    async def test_ownership_is_rechecked_and_ambiguous_or_writable_state_not_trusted(
        self,
    ):
        mine = self.ws("linda")
        self.hass.states.async_set("person.linda", "home", {"user_id": "intruder"})
        self.assertEqual(self.ws("intruder", admin=True)["state"], "unlinked")
        self.entities["person.linda"].extra_state_attributes["user_id"] = "mara"
        self.assertEqual(self.ws("mara"), {"state": "ambiguous"})
        self.assertEqual(
            self.save("linda", mine, only_when_home=True)["error"],
            "profile_unavailable",
        )
        self.assertEqual(self.save("mara", mine)["error"], "profile_unavailable")
        self.assertFalse(self.profiles[0].get("only_when_home"))

    async def test_only_allowlisted_values_can_be_written_and_critical_is_fixed(self):
        before = deepcopy(self.entry.options)
        mine = self.ws("linda")
        cases = (
            {"notify_targets": []},
            {"groups": []},
            {"person_entity_id": "person.mara"},
            {"id": "mara"},
            {"dnd_window": ""},
            {"only_when_home": "true"},
            {"always_notify": 1},
            {"weekday_window": "25:00-08:00"},
            {"weekend_window": "08:00-24:00"},
            {"day_windows": {"thursday": "08:00-09:00"}},
            {"day_windows": {"thu": "25:00-09:00"}},
            {"day_windows": {"tue": ""}},
            {"day_windows": ["mon"]},
            {"day_windows": {"mon": {"notify_targets": ["notify.other"]}}},
            {"weekday_window": "08:00-22:00\n"},
            {"enabled_types": ["critical"]},
            {"enabled_types": "warning"},
            {"enabled_types": ["other"]},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                self.assertEqual(
                    self.save("linda", mine, **changes)["error"], "invalid_preferences"
                )
        self.assertEqual(self.entry.options, before)
        self.save("linda", enabled_types=[])
        self.assertEqual(
            self.entry.options["profiles"][0]["enabled_types"], ["critical"]
        )
        await self.send(type="info")
        self.assertFalse(self.pushes["linda"])
        await self.send(type="critical")
        self.assertEqual(len(self.pushes["linda"]), 1)

    async def test_save_preserves_other_people_devices_groups_and_unrelated_concurrent_edits(
        self,
    ):
        profile = self.profiles[0]
        profile.update(dnd_window="20:30-06:00", extension={"opaque": True})
        mine = self.ws("linda")
        profile["notify_targets"].append("notify.additional")
        self.fallback["group_members"] = ["johannes", "mara"]
        self.entry.options["extension"] = "unrelated"
        self.save("johannes", only_when_home=True)
        other = deepcopy(self.entry.options["profiles"][1:])
        saved = self.save(
            "linda",
            mine,
            always_notify=False,
            weekday_window="21:30-06:45",
            weekend_window="",
        )
        self.assertEqual(saved, self.ws("linda"))
        self.assertNotEqual(saved["revision"], mine["revision"])
        updated = self.entry.options["profiles"][0]
        for k in (
            "id",
            "person_entity_id",
            "notify_targets",
            "extension",
            "dnd_window",
        ):
            self.assertEqual(updated[k], profile[k])
        self.assertEqual(self.entry.options["profiles"][1:], other)
        self.assertEqual(self.entry.options["groups"][0], self.fallback)
        self.assertEqual(self.entry.options["extension"], "unrelated")
        self.assertEqual(
            self.save("linda", mine, weekday_window="")["error"], "preferences_changed"
        )
        self.assertEqual(self.ws("linda"), saved)

    async def test_changes_apply_to_dispatch_fallback_and_already_requested_reminders(
        self,
    ):
        self.profiles[0]["dnd_window"] = ""
        self.save("linda", only_when_home=True)
        self.save("johannes", only_when_home=True)
        await self.send()
        self.assertEqual(self.rows("linda")[0]["routes"][0]["fallback"], "blocked")
        self.assertFalse(self.pushes["johannes"])
        push = {"profile": "linda", "person": "person.linda"}
        denial = lambda: self.dispatcher.personal_push_denial(
            push, "linda", "info", "notify.linda"
        )
        self.assertEqual(denial(), "person_not_home")
        self.hass.states.async_set("person.linda", "home")
        self.assertIsNone(denial())
        with patch(
            "custom_components.notification_dispatcher.dispatcher.dt_util.now",
            return_value=MONDAY,
        ):
            self.save(
                "linda",
                always_notify=False,
                weekday_window="08:00-09:00",
                weekend_window="",
            )
            self.assertEqual(denial(), "outside_weekday_window")
            self.save("linda", weekday_window="09:00-18:00")
            await self.send()
            self.assertIsNone(denial())
            self.assertEqual(len(self.pushes["linda"]), 1)
        saturday = MONDAY.replace(day=28)
        with patch(
            "custom_components.notification_dispatcher.dispatcher.dt_util.now",
            return_value=saturday,
        ):
            self.assertEqual(denial(), "weekend_disabled")
            saved = self.save("linda", always_notify=True)
            self.assertIsNone(denial())
            self.assertEqual(saved["settings"]["weekday_window"], "09:00-18:00")
        self.assertIs(self.hass.data[DOMAIN]["test"], self.dispatcher)

    async def test_legacy_windows_and_explicit_quiet_hours_are_preserved_until_removed(
        self,
    ):
        self.profiles[0].update(
            always_notify=False,
            allow_weekdays=False,
            weekend_start="10:30:00",
            weekend_end="19:45:00",
            dnd_enabled=True,
            dnd_start="11:00:00",
            dnd_end="13:00:00",
        )
        mine = self.ws("linda")
        self.assertEqual(mine["settings"]["weekday_window"], "")
        self.assertEqual(mine["settings"]["weekend_window"], "10:30-19:45")
        mine = self.save("linda", mine, always_notify=True)
        self.assertEqual(mine["quiet_window"], "11:00-13:00")
        with patch(
            "custom_components.notification_dispatcher.dispatcher.dt_util.now",
            return_value=MONDAY,
        ):
            await self.send()
            self.assertFalse(self.pushes["linda"])
            saved = self.ws(
                "linda",
                COMMAND + "/update",
                revision=mine["revision"],
                settings=mine["settings"],
                clear_quiet_hours=True,
            )
            self.assertEqual(saved["quiet_window"], "")
            await self.send()
            self.assertEqual(len(self.pushes["linda"]), 1)

    async def test_admin_forms_cannot_undo_an_intervening_personal_save(self):
        self.profiles[0].update(
            always_notify=False, weekday_window="09:00-17:00", dnd_window="12:00-13:00"
        )
        flow = NotificationDispatcherOptionsFlow()
        flow.hass = self.hass
        flow.handler = self.entry.entry_id
        flow.flow_id = "editing"
        initial = await flow.async_step_edit_person({"id": "linda"})
        self.assertEqual(initial["step_id"], "edit_details")
        old = dict(self.profiles[0])
        next_step = await flow.async_step_edit_details(old)
        self.assertEqual(next_step["step_id"], "edit_details_schedule")
        self.save("linda", only_when_home=True)
        rejected = await flow.async_step_edit_details_schedule(
            {"weekday_window": "00:00-23:59"}
        )
        self.assertEqual(rejected["step_id"], "edit_details")
        self.assertEqual(rejected["errors"]["base"], "profile_changed")
        current = self.entry.options["profiles"][0]
        via_admin = _profile_from_user_input(
            self.hass, {**current, "always_notify": True}, existing=current
        )
        self.assertTrue(via_admin["only_when_home"])
        self.assertEqual(via_admin["dnd_window"], "12:00-13:00")
        self.assertEqual(via_admin["weekday_window"], "09:00-17:00")

    async def test_real_config_entry_roundtrip_through_ha_storage(self):
        manager = ConfigEntries(self.hass, {})
        entry = ConfigEntry(
            domain=DOMAIN,
            entry_id="test",
            title=self.entry.title,
            options=self.entry.options,
            data={},
            version=1,
            minor_version=1,
            unique_id=DOMAIN,
            source="user",
            state=ConfigEntryState.LOADED,
            discovery_keys=MappingProxyType({}),
            subentries_data=[],
        )
        manager._entries[entry.entry_id] = entry
        with (
            patch.object(self.hass, "config_entries", manager),
            patch.object(self.dispatcher, "entry", entry),
        ):
            result = self.save(
                "linda",
                only_when_home=True,
                weekend_window="11:00-15:00",
                day_windows={"mon": "11:15-15:45"},
            )
            self.assertEqual(result, self.ws("linda"))
            await manager._store.async_save(manager._data_to_save())
        restored = ConfigEntries(self.hass, {})
        await restored.async_initialize()
        profile = restored.async_get_known_entry("test").options["profiles"][0]
        self.assertTrue(profile["only_when_home"])
        self.assertEqual(profile["weekend_window"], "11:00-15:00")
        self.assertEqual(profile["day_windows"], {"mon": "11:15-15:45"})

    async def test_sidebar_is_renamed_without_breaking_bookmarks_or_admin_scope(self):
        panel = self.hass.data[frontend.DATA_PANELS]["notification-verlauf"]
        self.assertEqual(panel.sidebar_title, "Benachrichtigen")
        self.assertFalse(panel.require_admin)

    async def test_daily_plan_drives_direct_fallback_and_personal_repeats(self):
        self.profiles[0]["dnd_window"] = self.profiles[1]["dnd_window"] = ""
        saved = self.save(
            "linda",
            always_notify=False,
            day_windows={"mon": "08:30-18:00", "thu": "10:00-16:00"},
        )
        self.assertEqual(saved, self.ws("linda"))
        self.save("johannes", always_notify=False, day_windows={"wed": "00:00-00:00"})
        push = {"profile": "linda", "person": "person.linda"}
        for day, reason, fallback in [
            (23, None, None),
            (24, "day_disabled", "blocked"),
            (25, "day_disabled", "sent"),
            (26, None, None),
        ]:
            with (
                self.subTest(day=day),
                patch(
                    "custom_components.notification_dispatcher.dispatcher.dt_util.now",
                    return_value=MONDAY.replace(day=day),
                ),
            ):
                count = len(self.pushes["linda"])
                await self.send()
                route = self.rows("linda")[0]["routes"][0]
                self.assertEqual(route["reason"], reason)
                self.assertEqual(route["fallback"], fallback)
                self.assertEqual(len(self.pushes["linda"]), count + (reason is None))
                self.assertEqual(
                    self.dispatcher.personal_push_denial(
                        push, "linda", "info", "notify.linda"
                    ),
                    reason,
                )
        self.save("linda", day_windows={}, only_when_home=True)
        await self.send()
        self.assertEqual(
            self.rows("linda")[0]["routes"][0]["reason"], "person_not_home"
        )
        await self.send(type="critical")
        self.assertEqual(self.rows("linda")[0]["routes"][0]["status"], "sent")
        self.hass.states.async_set("person.linda", "home")
        self.save("linda", always_notify=True)
        self.assertIsNone(
            self.dispatcher.personal_push_denial(push, "linda", "info", "notify.linda")
        )
        self.assertEqual(self.ws("linda")["settings"]["day_windows"], {})

    async def test_overnight_belongs_to_start_day_and_wraps_week(self):
        self.profiles[0]["dnd_window"] = ""
        self.save(
            "linda",
            always_notify=False,
            day_windows={"mon": "21:00-06:37", "sun": "23:15-01:20"},
        )
        p = self.entry.options["profiles"][0]
        for date, hour, minute, expected in [
            (23, 1, 20, True),
            (23, 1, 21, False),
            (23, 3, 0, False),
            (23, 20, 59, False),
            (23, 21, 0, True),
            (24, 6, 37, True),
            (24, 6, 38, False),
            (29, 23, 15, True),
        ]:
            with (
                self.subTest(day=date, hour=hour, minute=minute),
                patch(
                    "custom_components.notification_dispatcher.dispatcher.dt_util.now",
                    return_value=MONDAY.replace(
                        day=date, hour=hour, minute=minute, second=59
                    ),
                ),
            ):
                self.assertEqual(
                    self.dispatcher._delivery_decision(p, "info").should_deliver,
                    expected,
                )
        p["dnd_window"] = "00:45-01:30"
        with patch(
            "custom_components.notification_dispatcher.dispatcher.dt_util.now",
            return_value=MONDAY.replace(hour=1),
        ):
            self.assertEqual(
                self.dispatcher._delivery_decision(p, "info").reason, "dnd_active"
            )

    async def test_week_survives_old_clients_and_admin_device_edits_unless_explicitly_reset(
        self,
    ):
        mine = self.ws("linda")
        plan = {"tue": "09:13-17:39"}
        saved = self.save("linda", mine, always_notify=False, day_windows=plan)
        self.assertNotEqual(mine["revision"], saved["revision"])
        legacy = dict(saved["settings"])
        del legacy["day_windows"]
        result = self.ws(
            "linda",
            COMMAND + "/update",
            revision=saved["revision"],
            settings={**legacy, "only_when_home": True},
        )
        self.assertEqual(result["settings"]["day_windows"], plan)
        rejected = self.ws(
            "linda",
            COMMAND + "/update",
            revision=result["revision"],
            settings={**legacy, "weekday_window": ""},
        )
        self.assertEqual(rejected["error"], "preferences_changed")
        current = self.entry.options["profiles"][0]
        for reset in (False, True):
            flow = NotificationDispatcherOptionsFlow()
            flow.hass, flow.handler, flow.flow_id = (
                self.hass,
                self.entry.entry_id,
                "edit",
            )
            form = await flow.async_step_edit_person({"id": "linda"})
            self.assertIn("reset_personal_week", form["data_schema"].schema)
            answer = await flow.async_step_edit_details(
                {**current, "reset_personal_week": reset}
            )
            if reset:
                self.assertEqual(answer["step_id"], "edit_details_schedule")
                answer = await flow.async_step_edit_details_schedule(
                    {"weekday_window": "08:00-19:00", "weekend_window": ""}
                )
                self.assertNotIn("day_windows", answer["data"]["profiles"][0])
            else:
                self.assertEqual(answer["data"]["profiles"][0]["day_windows"], plan)
