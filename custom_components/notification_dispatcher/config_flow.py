"""Config flow for Notification Dispatcher."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig

from .config_flow_helpers import (
    InvalidTimeWindow,
    CONF_MEMBER_GROUPS,
    _apply_profile_group_memberships,
    _coerce_mapping_list,
    _fallback_group,
    _fallback_group_from_groups,
    _group_errors,
    _group_from_user_input,
    _group_ids_from_input,
    _group_schema,
    _group_select_options,
    _group_without_member,
    _is_fallback_group,
    _profile_errors,
    _profile_from_user_input,
    _profile_schedule_schema,
    _profile_schema,
    _profile_select_options,
)
from .const import (
    CONF_ALWAYS_NOTIFY,
    CONF_DND_END,
    CONF_DND_START,
    CONF_DND_WINDOW,
    CONF_GROUP_ID,
    CONF_GROUPS,
    CONF_NAME,
    CONF_PROFILE_ID,
    CONF_PROFILES,
    CONF_WEEKDAY_END,
    CONF_WEEKDAY_START,
    CONF_WEEKDAY_WINDOW,
    CONF_WEEKEND_END,
    CONF_WEEKEND_START,
    CONF_WEEKEND_WINDOW,
    DEFAULT_DND_WINDOW,
    DEFAULT_WEEKDAY_WINDOW,
    DEFAULT_WEEKEND_WINDOW,
    DOMAIN,
    NAME,
)

_LOGGER = logging.getLogger(__name__)


class NotificationDispatcherConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Notification Dispatcher."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Create the dispatcher without asking for a custom name."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=NAME,
            data={},
            options={CONF_PROFILES: [], CONF_GROUPS: [_fallback_group()]},
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
        self._pending_profile_input: dict[str, Any] | None = None

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Show the options menu."""
        menu_options = ["add_person", "manage_fallback"]
        if self._profiles:
            menu_options.extend(
                ["edit_person", "remove_person", "add_group", "edit_group"]
            )
        if self._custom_groups:
            menu_options.append("remove_group")

        return self.async_show_menu(step_id="init", menu_options=menu_options)

    async def async_step_manage_fallback(
        self, user_input: dict[str, Any] | None = None
    ):
        """Manage members of the built-in fallback group."""
        if not self._profiles:
            return await self.async_step_manage_fallback_empty(user_input)

        fallback_group = _fallback_group_from_groups(self._groups)
        if user_input is not None:
            updated_fallback = _group_from_user_input(
                user_input,
                existing=fallback_group,
            )
            groups = [
                updated_fallback if _is_fallback_group(group) else group
                for group in self._groups
            ]
            return self.async_create_entry(data=self._updated_options(groups=groups))

        return self.async_show_form(
            step_id="manage_fallback",
            data_schema=_group_schema(
                self._profiles,
                fallback_group,
                allow_name_edit=False,
            ),
        )

    async def async_step_manage_fallback_empty(
        self, user_input: dict[str, Any] | None = None
    ):
        """Show an informational fallback step when no people exist yet."""
        if user_input is not None:
            return await self.async_step_init()

        return self.async_show_form(
            step_id="manage_fallback_empty",
            data_schema=vol.Schema({}),
        )

    async def async_step_add_person(self, user_input: dict[str, Any] | None = None):
        """Add a person profile."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._pending_profile_input = dict(user_input)
            if bool(user_input.get(CONF_ALWAYS_NOTIFY, False)):
                return await self._async_save_profile_input(self._pending_profile_input)

            try:
                preview_profile = _profile_from_user_input(self.hass, user_input)
                errors = _profile_errors(self._profiles, preview_profile)
            except Exception:
                _LOGGER.exception("Unable to validate notification dispatcher person")
                errors["base"] = "save_failed"

            if errors:
                return self.async_show_form(
                    step_id="add_person",
                    data_schema=_profile_schema(
                        self.hass,
                        self._groups,
                        profile=user_input,
                        include_time_windows=False,
                    ),
                    errors=errors,
                )

            return await self.async_step_add_person_schedule()

        self._pending_profile_input = None
        return self.async_show_form(
            step_id="add_person",
            data_schema=_profile_schema(
                self.hass,
                self._groups,
                include_time_windows=False,
            ),
            errors=errors,
        )

    async def async_step_add_person_schedule(
        self, user_input: dict[str, Any] | None = None
    ):
        """Collect schedule windows for a new person profile."""
        base_input = self._pending_profile_input
        if base_input is None:
            return await self.async_step_add_person()

        errors: dict[str, str] = {}
        if user_input is not None:
            merged_input = {**base_input, **user_input}
            return await self._async_save_profile_input(merged_input)

        return self.async_show_form(
            step_id="add_person_schedule",
            data_schema=_profile_schedule_schema(base_input),
            errors=errors,
        )

    async def _async_save_profile_input(self, profile_input: dict[str, Any]):
        """Validate and save one profile from merged form input."""
        errors: dict[str, str] = {}
        try:
            profile = _profile_from_user_input(self.hass, profile_input)
        except InvalidTimeWindow as err:
            errors[err.field] = "invalid_time_window"
        except Exception:
            _LOGGER.exception("Unable to save notification dispatcher person")
            errors["base"] = "save_failed"
        else:
            try:
                errors = _profile_errors(self._profiles, profile)
                if not errors:
                    selected_group_ids = _group_ids_from_input(
                        profile_input.get(CONF_MEMBER_GROUPS, [])
                    )
                    profiles = [*self._profiles, profile]
                    groups = _apply_profile_group_memberships(
                        self._groups,
                        profile[CONF_PROFILE_ID],
                        selected_group_ids,
                    )
                    self._pending_profile_input = None
                    return self.async_create_entry(
                        data=self._updated_options(profiles=profiles, groups=groups)
                    )
            except Exception:
                _LOGGER.exception(
                    "Unable to finalize notification dispatcher person save"
                )
                errors["base"] = "save_failed"

        if profile_input.get(CONF_ALWAYS_NOTIFY, False):
            return self.async_show_form(
                step_id="add_person",
                data_schema=_profile_schema(
                    self.hass,
                    self._groups,
                    profile=profile_input,
                    include_time_windows=False,
                ),
                errors=errors,
            )

        self._pending_profile_input = dict(profile_input)
        return self.async_show_form(
            step_id="add_person_schedule",
            data_schema=_profile_schedule_schema(profile_input),
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
                        SelectSelectorConfig(
                            options=_profile_select_options(self._profiles)
                        )
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
            self._pending_profile_input = dict(user_input)
            try:
                preview_profile = _profile_from_user_input(
                    self.hass,
                    user_input,
                    existing=profile,
                )
                errors = _profile_errors(
                    self._profiles,
                    preview_profile,
                    profile.get(CONF_PROFILE_ID),
                )
            except Exception:
                _LOGGER.exception(
                    "Unable to validate notification dispatcher person update"
                )
                errors["base"] = "save_failed"

            if errors:
                return self.async_show_form(
                    step_id="edit_details",
                    data_schema=_profile_schema(
                        self.hass,
                        self._groups,
                        profile=user_input,
                        include_time_windows=False,
                    ),
                    errors=errors,
                )

            if bool(user_input.get(CONF_ALWAYS_NOTIFY, False)):
                return await self.async_step_edit_details_schedule(
                    {
                        CONF_WEEKDAY_WINDOW: _window_from_profile(
                            profile,
                            CONF_WEEKDAY_WINDOW,
                            DEFAULT_WEEKDAY_WINDOW,
                        ),
                        CONF_WEEKEND_WINDOW: _window_from_profile(
                            profile,
                            CONF_WEEKEND_WINDOW,
                            DEFAULT_WEEKEND_WINDOW,
                        ),
                        CONF_DND_WINDOW: _window_from_profile(
                            profile,
                            CONF_DND_WINDOW,
                            DEFAULT_DND_WINDOW,
                        ),
                    }
                )
            return await self.async_step_edit_details_schedule()

        self._pending_profile_input = None
        return self.async_show_form(
            step_id="edit_details",
            data_schema=_profile_schema(
                self.hass,
                self._groups,
                profile=profile,
                include_time_windows=False,
            ),
            errors=errors,
        )

    async def async_step_edit_details_schedule(
        self, user_input: dict[str, Any] | None = None
    ):
        """Collect schedule windows for an edited person profile."""
        profile = self._selected_profile
        if profile is None:
            return await self.async_step_init()

        base_input = self._pending_profile_input
        if base_input is None:
            return await self.async_step_edit_details()

        errors: dict[str, str] = {}
        if user_input is not None:
            merged_input = {**base_input, **user_input}
            try:
                updated_profile = _profile_from_user_input(
                    self.hass,
                    merged_input,
                    existing=profile,
                )
            except InvalidTimeWindow as err:
                errors[err.field] = "invalid_time_window"
            except Exception:
                _LOGGER.exception("Unable to update notification dispatcher person")
                errors["base"] = "save_failed"
            else:
                try:
                    errors = _profile_errors(
                        self._profiles,
                        updated_profile,
                        updated_profile[CONF_PROFILE_ID],
                    )
                    if not errors:
                        selected_group_ids = _group_ids_from_input(
                            merged_input.get(CONF_MEMBER_GROUPS, [])
                        )
                        profiles = [
                            updated_profile
                            if item.get(CONF_PROFILE_ID)
                            == updated_profile[CONF_PROFILE_ID]
                            else item
                            for item in self._profiles
                        ]
                        groups = _apply_profile_group_memberships(
                            self._groups,
                            updated_profile[CONF_PROFILE_ID],
                            selected_group_ids,
                        )
                        self._pending_profile_input = None
                        return self.async_create_entry(
                            data=self._updated_options(profiles=profiles, groups=groups)
                        )
                except Exception:
                    _LOGGER.exception(
                        "Unable to finalize notification dispatcher person update"
                    )
                    errors["base"] = "save_failed"

        return self.async_show_form(
            step_id="edit_details_schedule",
            data_schema=_profile_schedule_schema(
                user_input if user_input is not None else profile
            ),
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
            groups = [_group_without_member(group, profile_id) for group in self._groups]
            return self.async_create_entry(
                data=self._updated_options(profiles=profiles, groups=groups)
            )

        return self.async_show_form(
            step_id="remove_person",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PROFILE_ID): SelectSelector(
                        SelectSelectorConfig(
                            options=_profile_select_options(self._profiles)
                        )
                    )
                }
            ),
        )

    async def async_step_add_group(self, user_input: dict[str, Any] | None = None):
        """Add a notification group."""
        if not self._profiles:
            return await self.async_step_init()

        errors: dict[str, str] = {}
        if user_input is not None:
            group = _group_from_user_input(user_input)
            errors = _group_errors(self._groups, group)
            if not errors:
                groups = [*self._groups, group]
                return self.async_create_entry(data=self._updated_options(groups=groups))

        return self.async_show_form(
            step_id="add_group",
            data_schema=_group_schema(self._profiles),
            errors=errors,
        )

    async def async_step_edit_group(self, user_input: dict[str, Any] | None = None):
        """Select a notification group to edit."""
        if not self._profiles:
            return await self.async_step_init()

        if user_input is not None:
            self._selected_profile_id = user_input[CONF_GROUP_ID]
            return await self.async_step_edit_group_details()

        return self.async_show_form(
            step_id="edit_group",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_GROUP_ID): SelectSelector(
                        SelectSelectorConfig(options=_group_select_options(self._groups))
                    )
                }
            ),
        )

    async def async_step_edit_group_details(
        self, user_input: dict[str, Any] | None = None
    ):
        """Edit a selected notification group."""
        group = self._selected_group
        if group is None:
            return await self.async_step_init()

        errors: dict[str, str] = {}
        if user_input is not None:
            updated_group = _group_from_user_input(user_input, existing=group)
            errors = _group_errors(
                self._groups,
                updated_group,
                updated_group[CONF_GROUP_ID],
            )
            if not errors:
                groups = [
                    updated_group
                    if item.get(CONF_GROUP_ID) == updated_group[CONF_GROUP_ID]
                    else item
                    for item in self._groups
                ]
                return self.async_create_entry(data=self._updated_options(groups=groups))

        return self.async_show_form(
            step_id="edit_group_details",
            data_schema=_group_schema(
                self._profiles,
                group,
                allow_name_edit=not _is_fallback_group(group),
            ),
            errors=errors,
        )

    async def async_step_remove_group(self, user_input: dict[str, Any] | None = None):
        """Remove a notification group."""
        if not self._custom_groups:
            return await self.async_step_init()

        if user_input is not None:
            group_id = user_input[CONF_GROUP_ID]
            groups = [
                group for group in self._groups if group.get(CONF_GROUP_ID) != group_id
            ]
            return self.async_create_entry(data=self._updated_options(groups=groups))

        return self.async_show_form(
            step_id="remove_group",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_GROUP_ID): SelectSelector(
                        SelectSelectorConfig(
                            options=_group_select_options(self._custom_groups)
                        )
                    )
                }
            ),
        )

    @property
    def _profiles(self) -> list[dict[str, Any]]:
        """Return configured profiles."""
        return _coerce_mapping_list(self.config_entry.options.get(CONF_PROFILES, []))

    @property
    def _groups(self) -> list[dict[str, Any]]:
        """Return configured notification groups."""
        return _ensure_system_groups(
            _coerce_mapping_list(self.config_entry.options.get(CONF_GROUPS, []))
        )

    @property
    def _custom_groups(self) -> list[dict[str, Any]]:
        """Return user-defined groups without system groups."""
        return [group for group in self._groups if not _is_fallback_group(group)]

    @property
    def _selected_profile(self) -> dict[str, Any] | None:
        """Return the selected profile."""
        if self._selected_profile_id is None:
            return None
        for profile in self._profiles:
            if profile.get(CONF_PROFILE_ID) == self._selected_profile_id:
                return profile
        return None

    @property
    def _selected_group(self) -> dict[str, Any] | None:
        """Return the selected notification group."""
        if self._selected_profile_id is None:
            return None
        for group in self._groups:
            if group.get(CONF_GROUP_ID) == self._selected_profile_id:
                return group
        return None

    def _updated_options(
        self,
        *,
        profiles: list[dict[str, Any]] | None = None,
        groups: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Return options while preserving unrelated values."""
        options = dict(self.config_entry.options)
        options[CONF_PROFILES] = self._profiles if profiles is None else profiles
        raw_groups = self._groups if groups is None else groups
        options[CONF_GROUPS] = _ensure_system_groups(raw_groups)
        return options


def _window_from_profile(profile: dict[str, Any], key: str, default: str) -> str:
    """Return a profile window from compact or legacy fields."""
    if key in profile:
        return str(profile.get(key) or "")

    if key == CONF_WEEKDAY_WINDOW:
        start = profile.get(CONF_WEEKDAY_START)
        end = profile.get(CONF_WEEKDAY_END)
    elif key == CONF_WEEKEND_WINDOW:
        start = profile.get(CONF_WEEKEND_START)
        end = profile.get(CONF_WEEKEND_END)
    else:
        start = profile.get(CONF_DND_START)
        end = profile.get(CONF_DND_END)

    if start and end:
        return f"{_window_time_str(start)}-{_window_time_str(end)}"
    return default


def _window_time_str(value: Any) -> str:
    """Format one time value to HH:MM."""
    text = str(value or "")
    if len(text) >= 5 and text[2] == ":":
        return text[:5]
    parts = text.split(":")
    try:
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
    except (TypeError, ValueError, IndexError):
        return "00:00"
    return f"{hour:02d}:{minute:02d}"


def _ensure_system_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure built-in groups are present and normalized."""
    normalized_groups: list[dict[str, Any]] = []
    fallback: dict[str, Any] | None = None

    for group in groups:
        if _is_fallback_group(group):
            if fallback is None:
                fallback = _fallback_group(group)
            continue
        normalized_groups.append(group)

    normalized_groups.append(_fallback_group(fallback))
    return normalized_groups
