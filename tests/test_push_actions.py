"""Exercise actual HA service calls, event contexts, timers and private storage."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import Mock, patch

from homeassistant.components import persistent_notification
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import Context, EventOrigin, callback
from test_notification_history import DispatcherFixture

from custom_components.notification_dispatcher import async_setup_entry
from custom_components.notification_dispatcher.const import DOMAIN
from custom_components.notification_dispatcher.push_actions import EVENT_ACTION

MONDAY = datetime(2026, 11, 23, 12, tzinfo=UTC)


class ActionTests(DispatcherFixture, IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.hass.config.language = "de"
        self.mobile = {
            "notify": SimpleNamespace(registered_targets={}),
            "config_entries": {},
        }
        self.hass.data["mobile_app"] = self.mobile
        self.phones = {}
        self.bell = []

        @callback
        def bell(update_type, notifications):
            self.bell.append(update_type)

        self.addCleanup(
            persistent_notification.async_register_callback(self.hass, bell)
        )
        for profile in self.profiles:
            profile["notify_targets"] = [self.phone(profile["id"], profile["id"])]

    @property
    def dispatcher(self):
        return self.hass.data[DOMAIN]["test"]

    def phone(self, name, owner, os="iOS"):
        service = "mobile_app_" + name
        self.mobile["notify"].registered_targets[service] = "webhook_" + name
        self.mobile["config_entries"]["webhook_" + name] = SimpleNamespace(
            entry_id="registration_" + name, data={"user_id": owner, "os_name": os}
        )
        self.phones[name] = []

        @callback
        def notify(call):
            self.phones[name].append(dict(call.data))

        self.hass.services.async_register("notify", service, notify)
        return "notify." + service

    def buttons(self, device, index=-1):
        return {
            a["title"]: a["action"]
            for a in self.phones[device][index]["data"]["actions"]
        }

    async def press(self, value, owner="linda", **data):
        self.hass.bus.async_fire(
            EVENT_ACTION,
            {"action": value, **data},
            origin=EventOrigin.remote,
            context=Context(user_id=owner),
        )
        await self.hass.async_block_till_done()

    def route(self, owner="linda"):
        return self.rows(owner)[0]["routes"][0]

    async def test_ios_actions_are_optional_private_and_unique_per_delivery_and_device(
        self,
    ):
        self.profiles[0]["notify_targets"].append(
            self.phone("tablet", "linda", "iPadOS")
        )
        await self.send(["linda", "johannes"], data={"url": "/lovelace/office"})
        buttons = self.buttons("linda")
        self.assertEqual(list(buttons), ["Gelesen", "5 Min.", "30 Min.", "60 Min."])
        self.assertEqual(self.phones["linda"][0]["data"]["url"], "/lovelace/office")
        self.assertNotEqual(buttons, self.buttons("tablet"))
        self.assertNotEqual(buttons, self.buttons("johannes"))
        self.assertNotIn("read", self.route())
        for invalid_owner in (None, "johannes"):
            await self.press(buttons["Gelesen"], invalid_owner, user_id="linda")
        self.assertNotIn("read", self.route())
        await self.press("UNRELATED", "linda")
        await self.press(buttons["Gelesen"])
        self.assertTrue(self.route()["read"])
        self.assertNotIn("read", self.route("johannes"))
        await self.press(buttons["5 Min."])
        self.assertNotIn("due", self.route())
        self.assertNotIn("ND1:", str(self.rows("linda")))
        self.assertNotIn("registration_", str(self.rows("linda")))
        await self.send()
        self.assertNotEqual(buttons["5 Min."], self.buttons("linda")["5 Min."])
        self.assertNotIn("read", self.route())

    async def test_all_durations_start_on_tap_and_expire_only_once_on_requesting_device(
        self,
    ):
        self.profiles[0]["notify_targets"].append(self.phone("tablet", "linda"))
        for i, minutes in enumerate((5, 30, 60)):
            with self.subTest(minutes=minutes):
                await self.send("alle", type="warning")
                buttons = self.buttons("linda")
                with patch(
                    "custom_components.notification_dispatcher.push_actions.dt_util.utcnow",
                    return_value=MONDAY,
                ):
                    await self.press(buttons[f"{minutes} Min."])
                due = MONDAY + timedelta(minutes=minutes)
                await self.press(buttons["60 Min."])
                await self.press(self.buttons("tablet")["5 Min."])
                self.assertEqual(self.route()["due"], due.isoformat())
                await self.dispatcher.actions.async_due(due - timedelta(seconds=1))
                self.assertEqual(len(self.phones["linda"]), 2 * i + 1)
                await self.dispatcher.actions.async_due(due)
                await self.dispatcher.actions.async_due(due)
                await self.press(buttons["30 Min."])
                self.assertEqual(len(self.phones["linda"]), 2 * i + 2)
                self.assertEqual(len(self.bell), i + 1)
                for other in ("johannes", "mara", "tablet"):
                    self.assertEqual(len(self.phones[other]), i + 1)
                self.assertEqual(self.route()["repeat"], "sent")
                self.assertNotIn("due", self.route())
                self.assertNotEqual(buttons, self.buttons("linda"))

    async def test_filters_before_original_fallback_and_repeat(self):
        scenarios = (
            ({"only_when_home": True}, "person_not_home"),
            (
                {
                    "always_notify": False,
                    "weekday_window": "00:00-23:59",
                    "dnd_window": "11:00-13:00",
                },
                "dnd_active",
            ),
            (
                {"always_notify": False, "weekday_window": "14:00-20:00"},
                "outside_weekday_window",
            ),
            ({"enabled_types": []}, "type_not_enabled"),
        )
        for settings, reason in scenarios:
            with (
                self.subTest(reason=reason),
                patch(
                    "custom_components.notification_dispatcher.dispatcher.dt_util.now",
                    return_value=MONDAY,
                ),
            ):
                profile = self.profiles[0]
                before = dict(profile)
                await self.send()
                await self.press(self.buttons("linda")["5 Min."])
                due = datetime.fromisoformat(self.route()["due"])
                profile.update(settings)
                counts = {k: len(v) for k, v in self.phones.items()}
                await self.dispatcher.actions.async_due(due)
                self.assertEqual(self.route()["repeat_reason"], reason)
                self.assertEqual({k: len(v) for k, v in self.phones.items()}, counts)
                self.profiles[1]["only_when_home"] = True
                await self.send()
                self.assertEqual(self.route()["reason"], reason)
                self.assertEqual(
                    self.route()["fallback"],
                    None if reason == "type_not_enabled" else "blocked",
                )
                self.assertEqual({k: len(v) for k, v in self.phones.items()}, counts)
                profile.clear()
                profile.update(before)
        self.assertFalse(self.bell)

    async def test_critical_broadcast_and_bell_but_personal_repeat_honors_rules(self):
        self.profiles[0]["only_when_home"] = True
        await self.send("johannes", type="critical")
        self.assertEqual([len(v) for v in self.phones.values()], [1, 1, 1])
        self.assertEqual(
            self.phones["linda"][0]["data"]["push"]["interruption-level"], "critical"
        )
        await self.press(self.buttons("linda")["5 Min."])
        await self.dispatcher.actions.async_due(
            datetime.fromisoformat(self.route()["due"])
        )
        self.assertEqual(self.route()["repeat_reason"], "person_not_home")
        self.assertEqual([len(v) for v in self.phones.values()], [1, 1, 1])
        await self.press(self.buttons("johannes")["30 Min."], "johannes")
        await self.dispatcher.actions.async_due(
            datetime.fromisoformat(self.route("johannes")["due"])
        )
        self.assertEqual([len(v) for v in self.phones.values()], [1, 2, 1])
        self.assertEqual(len(self.bell), 1)

    async def test_home_to_away_dnd_start_and_weekend_transition_while_snoozed(self):
        profile = self.profiles[0]
        profile.update(
            only_when_home=True,
            always_notify=False,
            weekday_window="00:00-23:59",
            weekend_window="",
            dnd_window="",
        )
        friday = MONDAY + timedelta(days=4)
        for start, reason in (
            (MONDAY, "person_not_home"),
            (MONDAY.replace(hour=21, minute=58), "dnd_active"),
            (friday.replace(hour=23, minute=58), "weekend_disabled"),
        ):
            with self.subTest(reason=reason):
                self.hass.states.async_set("person.linda", "home")
                profile["dnd_window"] = "22:00-07:00" if reason == "dnd_active" else ""
                profile["always_notify"] = (
                    reason == "dnd_active"
                )  # An explicit legacy DND still applies.
                with (
                    patch(
                        "custom_components.notification_dispatcher.dispatcher.dt_util.now",
                        return_value=start,
                    ),
                    patch(
                        "custom_components.notification_dispatcher.push_actions.dt_util.utcnow",
                        return_value=start,
                    ),
                ):
                    await self.send()
                    self.assertEqual(self.route()["status"], "sent")
                    await self.press(self.buttons("linda")["5 Min."])
                count = len(self.phones["linda"])
                if reason == "person_not_home":
                    self.hass.states.async_set("person.linda", "not_home")
                due = start + timedelta(minutes=5)
                with patch(
                    "custom_components.notification_dispatcher.dispatcher.dt_util.now",
                    return_value=due,
                ):
                    await self.dispatcher.actions.async_due(due)
                self.assertEqual(self.route()["repeat_reason"], reason)
                self.assertEqual(len(self.phones["linda"]), count)
                self.assertEqual(self.phones["johannes"], [])

    async def test_android_menu_is_filtered_and_has_three_native_durations(self):
        self.mobile["config_entries"]["webhook_linda"].data["os_name"] = "Android"
        await self.send()
        buttons = self.buttons("linda")
        self.assertEqual(list(buttons), ["Gelesen", "Erinnern ..."])
        await self.press(buttons["Erinnern ..."])
        await self.press(buttons["Erinnern ..."])
        self.assertEqual(len(self.phones["linda"]), 2)
        self.assertEqual(list(self.buttons("linda")), ["5 Min.", "30 Min.", "60 Min."])
        await self.press(self.buttons("linda")["30 Min."])
        await self.dispatcher.actions.async_due(
            datetime.fromisoformat(self.route()["due"])
        )
        self.profiles[0]["only_when_home"] = True
        await self.press(self.buttons("linda")["Erinnern ..."])
        self.assertEqual(len(self.phones["linda"]), 3)
        self.assertEqual(self.route()["repeat_reason"], "person_not_home")

    async def test_restart_restores_timer_read_cancels_and_busy_history_does_not_evict_pending(
        self,
    ):
        await self.send()
        buttons = self.buttons("linda")
        await self.press(buttons["5 Min."])
        await self.press(buttons["Gelesen"])
        self.assertTrue(self.route()["read"])
        self.assertNotIn("due", self.route())
        await self.send(title="Please remind me")
        await self.press(self.buttons("linda")["30 Min."])
        due = datetime.fromisoformat(self.route()["due"])
        for n in range(51):
            await self.send(title=str(n))
        self.assertEqual(len(self.rows("linda")), 50)
        await self.close()
        with patch(
            "custom_components.notification_dispatcher.push_actions.async_track_point_in_utc_time"
        ) as track:
            await async_setup_entry(self.hass, self.entry)
            self.hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
            await self.hass.async_block_till_done()
            self.assertEqual(track.call_args.args[2], due)
            await track.call_args.args[1](due)
        self.assertEqual(len(self.phones["linda"]), 54)
        self.assertIn("Please remind me", self.phones["linda"][-1]["title"])
        self.assertEqual(self.phones["johannes"], [])

    async def test_current_profile_target_registration_and_account_are_rechecked(self):
        profile = self.profiles[0]
        reg = self.mobile["config_entries"]["webhook_linda"]
        for change in (
            "person_account",
            "device_account",
            "registration",
            "target",
            "profile",
        ):
            with self.subTest(change=change):
                await self.send()
                await self.press(self.buttons("linda")["60 Min."])
                due = datetime.fromisoformat(self.route()["due"])
                count = len(self.phones["linda"])
                if change == "person_account":
                    self.entities["person.linda"].extra_state_attributes["user_id"] = (
                        "mara"
                    )
                elif change == "device_account":
                    reg.data["user_id"] = "mara"
                elif change == "registration":
                    reg.entry_id = "replacement"
                elif change == "target":
                    profile["notify_targets"] = ["notify.mobile_app_johannes"]
                else:
                    self.profiles.remove(profile)
                await self.dispatcher.actions.async_due(due)
                self.assertEqual(len(self.phones["linda"]), count)
                self.assertEqual(self.route()["repeat_reason"], "recipient_changed")
                self.entities["person.linda"].extra_state_attributes[
                    "user_id"
                ] = reg.data["user_id"] = "linda"
                reg.entry_id = "registration_linda"
                profile["notify_targets"] = ["notify.mobile_app_linda"]
                if change == "profile":
                    self.profiles.insert(0, profile)
        self.assertFalse(self.phones["johannes"])

    async def test_fallback_buttons_belong_to_backup_and_never_forward_twice(self):
        self.profiles[0]["only_when_home"] = True
        await self.send()
        buttons = self.buttons("johannes")
        await self.press(buttons["5 Min."], "linda")
        self.assertNotIn("due", self.route("johannes"))
        await self.press(buttons["5 Min."], "johannes")
        self.profiles[1]["only_when_home"] = True
        self.fallback["group_members"] = ["mara"]
        await self.dispatcher.actions.async_due(
            datetime.fromisoformat(self.route("johannes")["due"])
        )
        self.assertEqual(self.route("johannes")["repeat_reason"], "person_not_home")
        self.assertEqual(self.route()["fallback"], "sent")
        self.assertFalse(self.phones["mara"])

    async def test_non_companion_dry_run_system_commands_custom_buttons_and_failed_push(
        self,
    ):
        await self.send("system")
        await self.send(dry_run=True)
        self.assertFalse(self.rows("linda"))
        self.assertFalse(self.phones["linda"])
        await self.send(message="clear_notification", data={"tag": "door"})
        self.assertEqual(self.phones["linda"][-1]["data"], {"tag": "door"})
        own = [{"action": "MY_ACTION", "title": "Garage"}]
        await self.send(data={"actions": own})
        self.assertEqual(self.phones["linda"][-1]["data"]["actions"][0], own[0])
        self.profiles[0]["notify_targets"] = ["notify.linda", "notify.mobile_app_mara"]
        await self.send()
        self.assertNotIn("data", self.pushes["linda"][-1])
        self.assertNotIn("data", self.phones["mara"][-1])
        self.profiles[0]["notify_targets"] = ["notify.mobile_app_linda"]

        @callback
        def fail(call):
            raise ConnectionError("offline")

        self.hass.services.async_register("notify", "mobile_app_linda", fail)
        receipts = len(list(self.dispatcher.history.receipts()))
        await self.send()
        self.assertEqual(self.route()["status"], "failed")
        self.assertEqual(len(list(self.dispatcher.history.receipts())), receipts)

    async def test_notify_entity_maps_to_its_actual_mobile_app_registration(self):
        self.profiles[0]["notify_targets"] = ["notify.renamed_2"]
        self.hass.states.async_set("notify.renamed_2", "unknown")
        registry = Mock()
        registry.async_get.return_value = SimpleNamespace(
            platform="mobile_app", config_entry_id="registration_linda"
        )
        with patch(
            "custom_components.notification_dispatcher.push_actions.er.async_get",
            return_value=registry,
        ):
            await self.send()
            await self.press(self.buttons("linda")["5 Min."])
            await self.dispatcher.actions.async_due(
                datetime.fromisoformat(self.route()["due"])
            )
        self.assertEqual(len(self.phones["linda"]), 2)
        self.assertFalse(self.phones["johannes"])
