"""Config flow for Notification Dispatcher."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TimeSelector,
)

from .const import (
    CONF_ALLOW_WEEKDAYS,
    CONF_ALLOW_WEEKENDS,
    CONF_DND_ENABLED,
    CONF_DND_END,
    CONF_DND_START,
    CONF_ENABLED_TYPES,
    CONF_FALLBACK_TARGET_KEY,
    CONF_INSTANCE_NAME,
    CONF_NAME,
    CONF_NOTIFY_TARGETS,
    CONF_ONLY_WHEN_HOME,
    CONF_PERSON_ENTITY_ID,
    CONF_PROFILE_ID,
    CONF_PROFILES,
    CONF_TARGET_KEY,
    CONF_WEEKDAY_END,
    CONF_WEEKDAY_START,
    CONF_WEEKEND_END,
    CONF_WEEKEND_START,
    DEFAULT_DND_END,
    DEFAULT_DND_START,
    DEFAULT_WEEKDAY_END,
    DEFAULT_WEEKDAY_START,
    DEFAULT_WEEKEND_END,
    DEFAULT_WEEKEND_START,
    DOMAIN,
    NAME,
    OPTIONAL_NOTIFICATION_TYPES,
    TARGET_ALL,
    TYPE_CRITICAL,
)


class NotificationDispatcherConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Notification Dispatcher."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(
                title=user_input[CONF_INSTANCE_NAME],
                data={},
                options={CONF_PROFILES: []},
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_INSTANCE_NAME, default=NAME): TextSelector()}
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Create the options flow."""
        return NotificationDispatcherOptionsFlow()


class NotificationDispatcherOptionsFlow(config_entries.OptionsFlowWithReload):
    """Manage Notification Dispatcher options."""

    def __init__(self) -> None:
        """Initialize the options flow."""
        self._selected_profile_id: str | None = None

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Show the options menu."""
        menu_options = ["add_person"]
        if self._profiles:
            menu_options.extend(["edit_person", "remove_person"])

        return self.async_show_menu(step_id="init", menu_options=menu_options)

    async def async_step_add_person(self, user_input: dict[str, Any] | None = None):
        """Add a person profile."""
        errors: dict[str, str] = {}
        if user_input is not None:
            profile = _profile_from_user_input(user_input)
            if not profile[CONF_NOTIFY_TARGETS]:
                errors[CONF_NOTIFY_TARGETS] = "missing_notify_target"
            elif profile[CONF_TARGET_KEY] == TARGET_ALL:
                errors[CONF_TARGET_KEY] = "reserved_target_key"
            elif _target_key_exists(self._profiles, profile[CONF_TARGET_KEY]):
                errors[CONF_TARGET_KEY] = "duplicate_target_key"
            else:
                profiles = [*self._profiles, profile]
                return self.async_create_entry(data={CONF_PROFILES: profiles})

        return self.async_show_form(
            step_id="add_person",
            data_schema=_profile_schema(),
            errors=errors,
        )

    async def async_step_edit_person(self, user_input: dict[str, Any] | None = None):
        """Select a person profile to edit."""
        if user_input is not None:
            self._selected_profile_id = user_input[CONF_PROFILE_ID]
            return await self.async_step_edit_details()

        return self.async_show_form(
            step_id="edit_person",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PROFILE_ID): SelectSelector(
                        SelectSelectorConfig(options=_profile_select_options(self._profiles))
                    )
                }
            ),
        )

    async def async_step_edit_details(self, user_input: dict[str, Any] | None = None):
        """Edit a selected person profile."""
        profile = self._selected_profile
        if profile is None:
            return await self.async_step_init()

        errors: dict[str, str] = {}
        if user_input is not None:
            updated_profile = _profile_from_user_input(user_input, existing=profile)
            if not updated_profile[CONF_NOTIFY_TARGETS]:
                errors[CONF_NOTIFY_TARGETS] = "missing_notify_target"
            elif updated_profile[CONF_TARGET_KEY] == TARGET_ALL:
                errors[CONF_TARGET_KEY] = "reserved_target_key"
            elif _target_key_exists(
                self._profiles,
                updated_profile[CONF_TARGET_KEY],
                updated_profile[CONF_PROFILE_ID],
            ):
                errors[CONF_TARGET_KEY] = "duplicate_target_key"
            else:
                profiles = [
                    updated_profile
                    if item.get(CONF_PROFILE_ID) == updated_profile[CONF_PROFILE_ID]
                    else item
                    for item in self._profiles
                ]
                return self.async_create_entry(data={CONF_PROFILES: profiles})

        return self.async_show_form(
            step_id="edit_details",
            data_schema=_profile_schema(profile),
            errors=errors,
        )

    async def async_step_remove_person(self, user_input: dict[str, Any] | None = None):
        """Remove a person profile."""
        if user_input is not None:
            profile_id = user_input[CONF_PROFILE_ID]
            profiles = [
                profile
                for profile in self._profiles
                if profile.get(CONF_PROFILE_ID) != profile_id
            ]
            return self.async_create_entry(data={CONF_PROFILES: profiles})

        return self.async_show_form(
            step_id="remove_person",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PROFILE_ID): SelectSelector(
                        SelectSelectorConfig(options=_profile_select_options(self._profiles))
                    )
                }
            ),
        )

    @property
    def _profiles(self) -> list[dict[str, Any]]:
        """Return configured profiles."""
        return list(self.config_entry.options.get(CONF_PROFILES, []))

    @property
    def _selected_profile(self) -> dict[str, Any] | None:
        """Return the selected profile."""
        if self._selected_profile_id is None:
            return None
        for profile in self._profiles:
            if profile.get(CONF_PROFILE_ID) == self._selected_profile_id:
                return profile
        return None


def _profile_schema(profile: dict[str, Any] | None = None) -> vol.Schema:
    """Build the person profile schema."""
    profile = profile or {}

    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=profile.get(CONF_NAME, "")): TextSelector(),
            vol.Required(
                CONF_TARGET_KEY,
                default=profile.get(CONF_TARGET_KEY, ""),
            ): TextSelector(),
            vol.Required(
                CONF_PERSON_ENTITY_ID,
                default=profile.get(CONF_PERSON_ENTITY_ID),
            ): EntitySelector(EntitySelectorConfig(domain="person")),
            vol.Required(
                CONF_NOTIFY_TARGETS,
                default=_targets_to_text(profile.get(CONF_NOTIFY_TARGETS, [])),
            ): TextSelector(),
            vol.Optional(
                CONF_FALLBACK_TARGET_KEY,
                default=profile.get(CONF_FALLBACK_TARGET_KEY, ""),
            ): TextSelector(),
            vol.Optional(
                CONF_ENABLED_TYPES,
                default=_optional_enabled_types(profile.get(CONF_ENABLED_TYPES, [])),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=OPTIONAL_NOTIFICATION_TYPES,
                    multiple=True,
                )
            ),
            vol.Optional(
                CONF_ONLY_WHEN_HOME,
                default=profile.get(CONF_ONLY_WHEN_HOME, False),
            ): BooleanSelector(),
            vol.Optional(
                CONF_ALLOW_WEEKDAYS,
                default=profile.get(CONF_ALLOW_WEEKDAYS, True),
            ): BooleanSelector(),
            vol.Optional(
                CONF_WEEKDAY_START,
                default=profile.get(CONF_WEEKDAY_START, DEFAULT_WEEKDAY_START),
            ): TimeSelector(),
            vol.Optional(
                CONF_WEEKDAY_END,
                default=profile.get(CONF_WEEKDAY_END, DEFAULT_WEEKDAY_END),
            ): TimeSelector(),
            vol.Optional(
                CONF_ALLOW_WEEKENDS,
                default=profile.get(CONF_ALLOW_WEEKENDS, True),
            ): BooleanSelector(),
            vol.Optional(
                CONF_WEEKEND_START,
                default=profile.get(CONF_WEEKEND_START, DEFAULT_WEEKEND_START),
            ): TimeSelector(),
            vol.Optional(
                CONF_WEEKEND_END,
                default=profile.get(CONF_WEEKEND_END, DEFAULT_WEEKEND_END),
            ): TimeSelector(),
            vol.Optional(
                CONF_DND_ENABLED,
                default=profile.get(CONF_DND_ENABLED, True),
            ): BooleanSelector(),
            vol.Optional(
                CONF_DND_START,
                default=profile.get(CONF_DND_START, DEFAULT_DND_START),
            ): TimeSelector(),
            vol.Optional(
                CONF_DND_END,
                default=profile.get(CONF_DND_END, DEFAULT_DND_END),
            ): TimeSelector(),
        }
    )


def _profile_from_user_input(
    user_input: dict[str, Any], existing: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Create a stored profile from form input."""
    existing = existing or {}
    enabled_types = set(user_input.get(CONF_ENABLED_TYPES, []))
    enabled_types.add(TYPE_CRITICAL)

    return {
        CONF_PROFILE_ID: existing.get(CONF_PROFILE_ID, uuid4().hex),
        CONF_NAME: user_input[CONF_NAME],
        CONF_TARGET_KEY: _normalize_target_key(
            user_input.get(CONF_TARGET_KEY) or user_input[CONF_NAME]
        ),
        CONF_PERSON_ENTITY_ID: user_input[CONF_PERSON_ENTITY_ID],
        CONF_NOTIFY_TARGETS: _targets_from_text(user_input[CONF_NOTIFY_TARGETS]),
        CONF_FALLBACK_TARGET_KEY: _normalize_target_key(
            user_input.get(CONF_FALLBACK_TARGET_KEY, "")
        ),
        CONF_ENABLED_TYPES: sorted(enabled_types),
        CONF_ONLY_WHEN_HOME: user_input.get(CONF_ONLY_WHEN_HOME, False),
        CONF_ALLOW_WEEKDAYS: user_input.get(CONF_ALLOW_WEEKDAYS, True),
        CONF_WEEKDAY_START: user_input.get(CONF_WEEKDAY_START, DEFAULT_WEEKDAY_START),
        CONF_WEEKDAY_END: user_input.get(CONF_WEEKDAY_END, DEFAULT_WEEKDAY_END),
        CONF_ALLOW_WEEKENDS: user_input.get(CONF_ALLOW_WEEKENDS, True),
        CONF_WEEKEND_START: user_input.get(CONF_WEEKEND_START, DEFAULT_WEEKEND_START),
        CONF_WEEKEND_END: user_input.get(CONF_WEEKEND_END, DEFAULT_WEEKEND_END),
        CONF_DND_ENABLED: user_input.get(CONF_DND_ENABLED, True),
        CONF_DND_START: user_input.get(CONF_DND_START, DEFAULT_DND_START),
        CONF_DND_END: user_input.get(CONF_DND_END, DEFAULT_DND_END),
    }


def _profile_select_options(profiles: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Build select options for profiles."""
    return [
        {
            "value": profile[CONF_PROFILE_ID],
            "label": (
                f"{profile.get(CONF_NAME)} ({profile.get(CONF_TARGET_KEY)})"
                if profile.get(CONF_TARGET_KEY)
                else profile.get(CONF_NAME) or profile.get(CONF_PERSON_ENTITY_ID)
            ),
        }
        for profile in profiles
    ]


def _targets_from_text(value: Any) -> list[str]:
    """Parse comma or newline separated notify targets."""
    text = str(value or "")
    raw_targets = text.replace("\n", ",").split(",")
    targets: list[str] = []
    for raw_target in raw_targets:
        target = raw_target.strip()
        if not target:
            continue
        if "." not in target:
            target = f"notify.{target}"
        if target.startswith("notify.") and target != "notify.":
            targets.append(target)
    return targets


def _targets_to_text(value: Any) -> str:
    """Render notify targets for the options form."""
    if isinstance(value, str):
        return value
    return ", ".join(str(item) for item in value)


def _optional_enabled_types(value: Any) -> list[str]:
    """Return non-critical enabled notification types."""
    if isinstance(value, str):
        value = [value]
    return [
        item
        for item in value
        if item in OPTIONAL_NOTIFICATION_TYPES
    ]


def _normalize_target_key(value: Any) -> str:
    """Normalize a profile target key."""
    return (
        str(value or "")
        .strip()
        .casefold()
        .replace(" ", "_")
        .replace("-", "_")
    )


def _target_key_exists(
    profiles: list[dict[str, Any]],
    target_key: str,
    current_profile_id: str | None = None,
) -> bool:
    """Return whether a target key is already used by another profile."""
    if not target_key:
        return False
    for profile in profiles:
        if profile.get(CONF_PROFILE_ID) == current_profile_id:
            continue
        if profile.get(CONF_TARGET_KEY) == target_key:
            return True
    return False
