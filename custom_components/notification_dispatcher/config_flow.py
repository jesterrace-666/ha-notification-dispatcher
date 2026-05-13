"""Config flow for Notification Dispatcher."""

from __future__ import annotations

import logging
import re
from typing import Any
from uuid import uuid4

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
)

from .const import (
    CONF_ALLOW_WEEKDAYS,
    CONF_ALLOW_WEEKENDS,
    CONF_DND_ENABLED,
    CONF_DND_END,
    CONF_DND_START,
    CONF_DND_WINDOW,
    CONF_ENABLED_TYPES,
    CONF_GROUP_ID,
    CONF_GROUP_MEMBERS,
    CONF_GROUPS,
    CONF_NAME,
    CONF_NOTIFY_TARGETS,
    CONF_ONLY_WHEN_HOME,
    CONF_PERSON_ENTITY_ID,
    CONF_PROFILE_ID,
    CONF_PROFILES,
    CONF_TARGET_KEY,
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
    OPTIONAL_NOTIFICATION_TYPES,
    SYSTEM_GROUP_FALLBACK_ID,
    SYSTEM_GROUP_FALLBACK_NAME,
    SYSTEM_GROUP_FALLBACK_TARGET_KEY,
    TYPE_CRITICAL,
    TYPE_INFO,
)

_WINDOW_SPLITTER = re.compile(r"\s*(?:-|\bbis\b|\bto\b)\s*", re.IGNORECASE)
TARGET_ALL_ALIASES = {"all", "alle"}
CONF_MEMBER_GROUPS = "member_groups"
_LOGGER = logging.getLogger(__name__)


class InvalidTimeWindow(ValueError):
    """Raised when a compact time window cannot be parsed."""

    def __init__(self, field: str) -> None:
        """Initialize the error."""
        super().__init__(field)
        self.field = field


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
            try:
                profile = _profile_from_user_input(self.hass, user_input)
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
                            user_input.get(CONF_MEMBER_GROUPS, [])
                        )
                        profiles = [*self._profiles, profile]
                        groups = _apply_profile_group_memberships(
                            self._groups,
                            profile[CONF_PROFILE_ID],
                            selected_group_ids,
                        )
                        return self.async_create_entry(
                            data=self._updated_options(
                                profiles=profiles,
                                groups=groups,
                            )
                        )
                except Exception:
                    _LOGGER.exception(
                        "Unable to finalize notification dispatcher person save"
                    )
                    errors["base"] = "save_failed"

        return self.async_show_form(
            step_id="add_person",
            data_schema=_profile_schema(
                self.hass,
                self._groups,
            ),
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
            try:
                updated_profile = _profile_from_user_input(
                    self.hass,
                    user_input,
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
                            user_input.get(CONF_MEMBER_GROUPS, [])
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
                        return self.async_create_entry(
                            data=self._updated_options(
                                profiles=profiles,
                                groups=groups,
                            )
                        )
                except Exception:
                    _LOGGER.exception(
                        "Unable to finalize notification dispatcher person update"
                    )
                    errors["base"] = "save_failed"

        return self.async_show_form(
            step_id="edit_details",
            data_schema=_profile_schema(
                self.hass,
                self._groups,
                profile,
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
            groups = [
                _group_without_member(group, profile_id)
                for group in self._groups
            ]
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
                return self.async_create_entry(
                    data=self._updated_options(groups=groups)
                )

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
                return self.async_create_entry(
                    data=self._updated_options(groups=groups)
                )

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
                group
                for group in self._groups
                if group.get(CONF_GROUP_ID) != group_id
            ]
            return self.async_create_entry(
                data=self._updated_options(groups=groups)
            )

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


def _profile_schema(
    hass: HomeAssistant,
    groups: list[dict[str, Any]],
    profile: dict[str, Any] | None = None,
) -> vol.Schema:
    """Build the person profile schema."""
    profile = profile or {}
    notify_target_options = _notify_target_select_options(hass)
    if notify_target_options:
        notify_target_selector = SelectSelector(
            SelectSelectorConfig(
                options=notify_target_options,
                multiple=True,
                custom_value=True,
            )
        )
        notify_target_default = _targets_to_list(profile.get(CONF_NOTIFY_TARGETS, []))
    else:
        notify_target_selector = TextSelector()
        notify_target_default = _targets_to_text(profile.get(CONF_NOTIFY_TARGETS, []))

    profile_id = str(profile.get(CONF_PROFILE_ID, "")).strip()
    member_groups_default = _profile_group_ids(groups, profile_id)
    group_options = _group_select_options(groups)

    schema: dict[Any, Any] = {
        vol.Required(
            CONF_PERSON_ENTITY_ID,
            default=profile.get(CONF_PERSON_ENTITY_ID),
        ): EntitySelector(EntitySelectorConfig(domain="person")),
        vol.Required(
            CONF_NOTIFY_TARGETS,
            default=notify_target_default,
        ): notify_target_selector,
        vol.Optional(
            CONF_ENABLED_TYPES,
            default=_optional_enabled_types(
                profile.get(CONF_ENABLED_TYPES, [TYPE_INFO])
            ),
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
            CONF_WEEKDAY_WINDOW,
            default=_window_from_profile(
                profile,
                CONF_WEEKDAY_WINDOW,
                CONF_ALLOW_WEEKDAYS,
                CONF_WEEKDAY_START,
                CONF_WEEKDAY_END,
                DEFAULT_WEEKDAY_WINDOW,
            ),
        ): TextSelector(),
        vol.Optional(
            CONF_WEEKEND_WINDOW,
            default=_window_from_profile(
                profile,
                CONF_WEEKEND_WINDOW,
                CONF_ALLOW_WEEKENDS,
                CONF_WEEKEND_START,
                CONF_WEEKEND_END,
                DEFAULT_WEEKEND_WINDOW,
            ),
        ): TextSelector(),
        vol.Optional(
            CONF_DND_WINDOW,
            default=_window_from_profile(
                profile,
                CONF_DND_WINDOW,
                CONF_DND_ENABLED,
                CONF_DND_START,
                CONF_DND_END,
                DEFAULT_DND_WINDOW,
            ),
        ): TextSelector(),
    }

    if group_options:
        schema[
            vol.Optional(
                CONF_MEMBER_GROUPS,
                default=member_groups_default,
            )
        ] = SelectSelector(
            SelectSelectorConfig(
                options=group_options,
                multiple=True,
                mode="list",
            )
        )

    return vol.Schema(schema)


def _profile_from_user_input(
    hass: HomeAssistant,
    user_input: dict[str, Any],
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a stored profile from form input."""
    existing = existing or {}
    enabled_types = set(_optional_enabled_types(user_input.get(CONF_ENABLED_TYPES)))
    enabled_types.add(TYPE_CRITICAL)

    person_entity_id = _selector_value_to_string(
        user_input.get(CONF_PERSON_ENTITY_ID, "")
    ).strip()
    known_targets = _known_notify_targets(hass)

    target_key = (
        existing.get(CONF_TARGET_KEY)
        if existing.get(CONF_PERSON_ENTITY_ID) == person_entity_id
        else _target_key_from_person_entity(person_entity_id)
    )

    return {
        CONF_PROFILE_ID: existing.get(CONF_PROFILE_ID, uuid4().hex),
        CONF_NAME: _person_name(hass, person_entity_id),
        CONF_TARGET_KEY: target_key or _target_key_from_person_entity(person_entity_id),
        CONF_PERSON_ENTITY_ID: person_entity_id,
        CONF_NOTIFY_TARGETS: _targets_from_input(
            user_input.get(CONF_NOTIFY_TARGETS, ""),
            known_targets,
        ),
        CONF_ENABLED_TYPES: sorted(enabled_types),
        CONF_ONLY_WHEN_HOME: user_input.get(CONF_ONLY_WHEN_HOME, False),
        CONF_WEEKDAY_WINDOW: _normalize_time_window(
            user_input.get(CONF_WEEKDAY_WINDOW),
            DEFAULT_WEEKDAY_WINDOW,
            CONF_WEEKDAY_WINDOW,
        ),
        CONF_WEEKEND_WINDOW: _normalize_time_window(
            user_input.get(CONF_WEEKEND_WINDOW),
            DEFAULT_WEEKEND_WINDOW,
            CONF_WEEKEND_WINDOW,
        ),
        CONF_DND_WINDOW: _normalize_time_window(
            user_input.get(CONF_DND_WINDOW),
            DEFAULT_DND_WINDOW,
            CONF_DND_WINDOW,
        ),
    }


def _profile_errors(
    profiles: list[dict[str, Any]],
    profile: dict[str, Any],
    current_profile_id: str | None = None,
) -> dict[str, str]:
    """Validate a profile and return Home Assistant form errors."""
    errors: dict[str, str] = {}

    if not profile[CONF_NOTIFY_TARGETS]:
        errors[CONF_NOTIFY_TARGETS] = "missing_notify_target"
    if not profile[CONF_PERSON_ENTITY_ID]:
        errors[CONF_PERSON_ENTITY_ID] = "missing_person"

    if _person_exists(
        profiles,
        profile[CONF_PERSON_ENTITY_ID],
        current_profile_id,
    ):
        errors[CONF_PERSON_ENTITY_ID] = "duplicate_person"

    return errors


def _profile_select_options(
    profiles: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Build select options for profiles."""
    return [
        {
            "value": profile[CONF_PROFILE_ID],
            "label": _profile_label(profile),
        }
        for profile in profiles
    ]


def _profile_label(profile: dict[str, Any]) -> str:
    """Return a human readable profile label."""
    name = profile.get(CONF_NAME) or profile.get(CONF_PERSON_ENTITY_ID) or "Person"
    targets = profile.get(CONF_NOTIFY_TARGETS, [])
    target_count = len(targets) if isinstance(targets, list) else 1
    if target_count <= 1:
        return str(name)
    return f"{name} ({target_count} Ziele)"


def _group_schema(
    profiles: list[dict[str, Any]],
    group: dict[str, Any] | None = None,
    *,
    allow_name_edit: bool = True,
) -> vol.Schema:
    """Build the group schema."""
    group = group or {}
    schema: dict[Any, Any] = {
        vol.Required(
            CONF_GROUP_MEMBERS,
            default=list(group.get(CONF_GROUP_MEMBERS, [])),
        ): SelectSelector(
            SelectSelectorConfig(
                options=_profile_select_options(profiles),
                multiple=True,
            )
        )
    }
    if allow_name_edit:
        schema = {
            vol.Required(CONF_NAME, default=group.get(CONF_NAME, "")): TextSelector(),
            **schema,
        }
    return vol.Schema(schema)


def _group_from_user_input(
    user_input: dict[str, Any],
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a stored group from form input."""
    existing = existing or {}
    is_fallback_group = _is_fallback_group(existing)

    if is_fallback_group:
        name = SYSTEM_GROUP_FALLBACK_NAME
        target_key = SYSTEM_GROUP_FALLBACK_TARGET_KEY
        group_id = SYSTEM_GROUP_FALLBACK_ID
    else:
        if CONF_NAME in user_input:
            name = str(user_input.get(CONF_NAME, "")).strip()
        else:
            name = str(existing.get(CONF_NAME, "")).strip()

        target_key = (
            existing.get(CONF_TARGET_KEY)
            if existing.get(CONF_NAME) == name
            else _normalize_target_key(name)
        )
        group_id = str(existing.get(CONF_GROUP_ID, uuid4().hex))

    return {
        CONF_GROUP_ID: group_id,
        CONF_NAME: name,
        CONF_TARGET_KEY: target_key or _normalize_target_key(name),
        CONF_GROUP_MEMBERS: _ensure_list(user_input.get(CONF_GROUP_MEMBERS)),
    }


def _group_errors(
    groups: list[dict[str, Any]],
    group: dict[str, Any],
    current_group_id: str | None = None,
) -> dict[str, str]:
    """Validate a group and return Home Assistant form errors."""
    if _is_fallback_group(group):
        return {}

    errors: dict[str, str] = {}
    target_key = _normalize_target_key(group.get(CONF_TARGET_KEY))

    if not group.get(CONF_NAME):
        errors[CONF_NAME] = "missing_group_name"
    elif target_key in {SYSTEM_GROUP_FALLBACK_TARGET_KEY, *TARGET_ALL_ALIASES}:
        errors[CONF_NAME] = "reserved_group_name"
    elif _group_key_exists(groups, target_key, current_group_id):
        errors[CONF_NAME] = "duplicate_group"

    if not group.get(CONF_GROUP_MEMBERS):
        errors[CONF_GROUP_MEMBERS] = "missing_group_members"

    return errors


def _group_key_exists(
    groups: list[dict[str, Any]],
    target_key: str,
    current_group_id: str | None = None,
) -> bool:
    """Return whether a group key is already used by another group."""
    for group in groups:
        if group.get(CONF_GROUP_ID) == current_group_id:
            continue
        if _normalize_target_key(group.get(CONF_TARGET_KEY)) == target_key:
            return True
        if _normalize_target_key(group.get(CONF_NAME)) == target_key:
            return True
    return False


def _group_select_options(groups: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Build select options for groups."""
    return [
        {
            "value": group[CONF_GROUP_ID],
            "label": _group_label(group),
        }
        for group in groups
    ]


def _group_label(group: dict[str, Any]) -> str:
    """Return a human readable group label."""
    members = group.get(CONF_GROUP_MEMBERS, [])
    member_count = len(members) if isinstance(members, list) else 0
    if _is_fallback_group(group):
        return f"{SYSTEM_GROUP_FALLBACK_NAME} ({member_count} Personen)"
    return f"{group.get(CONF_NAME, 'Gruppe')} ({member_count} Personen)"


def _group_without_member(group: dict[str, Any], profile_id: str) -> dict[str, Any]:
    """Return a group with one profile removed."""
    updated_group = dict(group)
    updated_group[CONF_GROUP_MEMBERS] = [
        member_id
        for member_id in _ensure_list(group.get(CONF_GROUP_MEMBERS))
        if member_id != profile_id
    ]
    return updated_group


def _profile_group_ids(groups: list[dict[str, Any]], profile_id: str) -> list[str]:
    """Return group ids a profile currently belongs to."""
    if not profile_id:
        return []

    group_ids: list[str] = []
    for group in groups:
        group_id = str(group.get(CONF_GROUP_ID, "")).strip()
        if not group_id:
            continue
        members = [str(member) for member in _ensure_list(group.get(CONF_GROUP_MEMBERS))]
        if profile_id in members:
            group_ids.append(group_id)

    return group_ids


def _group_ids_from_input(value: Any) -> list[str]:
    """Parse group ids from selector input."""
    group_ids: list[str] = []
    for raw_group_id in _ensure_list(value):
        group_id = _selector_value_to_string(raw_group_id).strip()
        if group_id and group_id not in group_ids:
            group_ids.append(group_id)
    return group_ids


def _apply_profile_group_memberships(
    groups: list[dict[str, Any]],
    profile_id: str,
    selected_group_ids: list[str],
) -> list[dict[str, Any]]:
    """Apply selected group memberships for one profile."""
    selected_ids = set(selected_group_ids)
    updated_groups: list[dict[str, Any]] = []

    for group in groups:
        updated_group = dict(group)
        group_id = str(group.get(CONF_GROUP_ID, "")).strip()
        members = [
            str(member)
            for member in _ensure_list(group.get(CONF_GROUP_MEMBERS))
            if str(member).strip()
        ]
        members = [member for member in members if member != profile_id]
        if group_id in selected_ids:
            members.append(profile_id)
        updated_group[CONF_GROUP_MEMBERS] = list(dict.fromkeys(members))
        updated_groups.append(updated_group)

    return updated_groups


def _fallback_group_from_groups(groups: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the built-in fallback group from configured groups."""
    for group in groups:
        if _is_fallback_group(group):
            return _fallback_group(group)
    return _fallback_group()


def _fallback_group(existing: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the built-in fallback group."""
    existing = existing or {}
    return {
        CONF_GROUP_ID: SYSTEM_GROUP_FALLBACK_ID,
        CONF_NAME: SYSTEM_GROUP_FALLBACK_NAME,
        CONF_TARGET_KEY: SYSTEM_GROUP_FALLBACK_TARGET_KEY,
        CONF_GROUP_MEMBERS: _ensure_list(existing.get(CONF_GROUP_MEMBERS)),
    }


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


def _is_fallback_group(group: dict[str, Any]) -> bool:
    """Return whether a group is the built-in fallback group."""
    if str(group.get(CONF_GROUP_ID, "")).strip() == SYSTEM_GROUP_FALLBACK_ID:
        return True

    target_key = _normalize_target_key(group.get(CONF_TARGET_KEY))
    if target_key == SYSTEM_GROUP_FALLBACK_TARGET_KEY:
        return True

    group_name = _normalize_target_key(group.get(CONF_NAME))
    return group_name == SYSTEM_GROUP_FALLBACK_TARGET_KEY


def _person_name(hass: HomeAssistant, person_entity_id: str) -> str:
    """Return a friendly person name from Home Assistant."""
    state = hass.states.get(person_entity_id)
    if state is not None:
        friendly_name = state.attributes.get("friendly_name")
        if friendly_name:
            return str(friendly_name)

    return person_entity_id.removeprefix("person.").replace("_", " ").title()


def _target_key_from_person_entity(person_entity_id: str) -> str:
    """Create the invisible compatibility target key from a person entity."""
    return _normalize_target_key(person_entity_id.removeprefix("person."))


def _person_exists(
    profiles: list[dict[str, Any]],
    person_entity_id: str,
    current_profile_id: str | None = None,
) -> bool:
    """Return whether a person is already configured."""
    for profile in profiles:
        if profile.get(CONF_PROFILE_ID) == current_profile_id:
            continue
        if profile.get(CONF_PERSON_ENTITY_ID) == person_entity_id:
            return True
    return False


def _known_notify_targets(hass: HomeAssistant) -> set[str]:
    """Return notify services and notify entities that can be offered in the UI."""
    targets: set[str] = set()

    for service in _notify_services(hass):
        if service in {"persistent_notification", "send_message"}:
            continue
        targets.add(f"notify.{service}")

    try:
        targets.update(hass.states.async_entity_ids("notify"))
    except Exception:
        _LOGGER.exception("Unable to list notify entities for options flow")

    return targets


def _notify_services(hass: HomeAssistant) -> list[str]:
    """Return notify service names without failing the options flow."""
    try:
        return list(hass.services.async_services_for_domain("notify"))
    except AttributeError:
        try:
            return list(hass.services.async_services().get("notify", {}))
        except Exception:
            _LOGGER.exception("Unable to list notify services for options flow")
            return []
    except Exception:
        _LOGGER.exception("Unable to list notify services for options flow")
        return []


def _notify_target_select_options(hass: HomeAssistant) -> list[dict[str, str]]:
    """Build select options for available notify targets."""
    targets = sorted(
        _known_notify_targets(hass),
        key=lambda target: _notify_target_label(hass, target).casefold(),
    )
    return [
        {
            "value": target,
            "label": _notify_target_label(hass, target),
        }
        for target in targets
    ]


def _notify_target_label(hass: HomeAssistant, target: str) -> str:
    """Return a readable label for a notify target."""
    state = hass.states.get(target)
    if state is not None:
        friendly_name = state.attributes.get("friendly_name")
        if friendly_name:
            return f"{friendly_name} ({target})"

    name = target.removeprefix("notify.")
    if name.startswith("mobile_app_"):
        name = name.removeprefix("mobile_app_")
    label = name.replace("_", " ").title()
    return f"{label} ({target})"


def _targets_from_input(value: Any, known_targets: set[str]) -> list[str]:
    """Parse selector values into normalized notify targets."""
    if isinstance(value, str):
        raw_targets: list[Any] = value.replace("\n", ",").split(",")
    elif isinstance(value, list):
        raw_targets = value
    else:
        raw_targets = []

    targets: list[str] = []
    for raw_target in raw_targets:
        target = _normalize_notify_target(
            _selector_value_to_string(raw_target),
            known_targets,
        )
        if target and target not in targets:
            targets.append(target)
    return targets


def _normalize_notify_target(value: Any, known_targets: set[str]) -> str:
    """Normalize one notify target from the options form."""
    target = str(value or "").strip()
    if not target:
        return ""
    if target.startswith("notify."):
        return target

    notify_target = f"notify.{target}"
    mobile_app_target = f"notify.mobile_app_{target}"
    if notify_target in known_targets:
        return notify_target
    if mobile_app_target in known_targets:
        return mobile_app_target
    if target.startswith("mobile_app_"):
        return notify_target
    return notify_target


def _targets_to_text(value: Any) -> str:
    """Render notify targets for the options form."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if str(item).strip())
    return ""


def _targets_to_list(value: Any) -> list[str]:
    """Render notify targets for a multi-select field."""
    if isinstance(value, str):
        return [target.strip() for target in value.split(",") if target.strip()]
    if isinstance(value, list):
        return [
            _selector_value_to_string(item).strip()
            for item in value
            if _selector_value_to_string(item).strip()
        ]
    return []


def _optional_enabled_types(value: Any) -> list[str]:
    """Return non-critical enabled notification types."""
    optional_types: list[str] = []
    for raw_item in _ensure_list(value):
        item = _selector_value_to_string(raw_item).strip().lower()
        if item in OPTIONAL_NOTIFICATION_TYPES and item not in optional_types:
            optional_types.append(item)
    return optional_types


def _window_from_profile(
    profile: dict[str, Any],
    window_key: str,
    enabled_key: str,
    start_key: str,
    end_key: str,
    default_window: str,
    *,
    disabled_value: bool = True,
) -> str:
    """Return the compact time window for current and older profiles."""
    if window_key in profile:
        return str(profile.get(window_key) or "")

    if profile and profile.get(enabled_key, disabled_value) is False:
        return ""

    start = profile.get(start_key)
    end = profile.get(end_key)
    if start and end:
        return f"{_format_time(start)}-{_format_time(end)}"

    return default_window


def _normalize_time_window(value: Any, default: str, field: str) -> str:
    """Normalize a compact time window like 08:00-22:00."""
    raw = str(default if value is None else value).strip()
    if not raw:
        return ""

    parts = [part for part in _WINDOW_SPLITTER.split(raw, maxsplit=1) if part]
    if len(parts) != 2:
        raise InvalidTimeWindow(field)

    try:
        start = _normalize_time_part(parts[0])
        end = _normalize_time_part(parts[1])
    except ValueError as err:
        raise InvalidTimeWindow(field) from err

    return f"{start}-{end}"


def _normalize_time_part(value: Any) -> str:
    """Normalize one time part to HH:MM."""
    parts = str(value).strip().split(":")
    if not parts or len(parts) > 3:
        raise ValueError

    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 and parts[1] else 0
    second = int(float(parts[2])) if len(parts) > 2 and parts[2] else 0
    if not 0 <= hour <= 23 or not 0 <= minute <= 59 or not 0 <= second <= 59:
        raise ValueError

    return f"{hour:02d}:{minute:02d}"


def _format_time(value: Any) -> str:
    """Format old Home Assistant time selector values for the compact field."""
    try:
        return _normalize_time_part(value)
    except (TypeError, ValueError):
        return "00:00"


def _ensure_list(value: Any) -> list[Any]:
    """Return form data as a list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _selector_value_to_string(value: Any) -> str:
    """Convert selector values to a plain string."""
    if isinstance(value, dict):
        for key in ("value", "entity_id", "id"):
            raw = value.get(key)
            if raw:
                return str(raw)
    return str(value or "")


def _coerce_mapping_list(value: Any) -> list[dict[str, Any]]:
    """Return a list of dict entries from potentially old options formats."""
    if isinstance(value, dict):
        raw_items: list[Any] = list(value.values())
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = []

    items: list[dict[str, Any]] = []
    for item in raw_items:
        if isinstance(item, dict):
            items.append(item)
    return items


def _normalize_target_key(value: Any) -> str:
    """Normalize a profile target key."""
    return (
        str(value or "")
        .strip()
        .casefold()
        .replace(" ", "_")
        .replace("-", "_")
    )
