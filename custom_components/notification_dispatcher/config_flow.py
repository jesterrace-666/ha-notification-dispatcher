"""Config flow for Notification Dispatcher."""

from __future__ import annotations

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
    TYPE_CRITICAL,
)

_WINDOW_SPLITTER = re.compile(r"\s*(?:-|\bbis\b|\bto\b)\s*", re.IGNORECASE)
_IGNORED_NOTIFY_SERVICES = {"persistent_notification", "send_message"}


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
            options={CONF_PROFILES: []},
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
            try:
                profile = _profile_from_user_input(self.hass, user_input)
            except InvalidTimeWindow as err:
                errors[err.field] = "invalid_time_window"
            else:
                errors = _profile_errors(self._profiles, profile)
                if not errors:
                    profiles = [*self._profiles, profile]
                    return self.async_create_entry(data={CONF_PROFILES: profiles})

        return self.async_show_form(
            step_id="add_person",
            data_schema=_profile_schema(self.hass),
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
            try:
                updated_profile = _profile_from_user_input(
                    self.hass,
                    user_input,
                    existing=profile,
                )
            except InvalidTimeWindow as err:
                errors[err.field] = "invalid_time_window"
            else:
                errors = _profile_errors(
                    self._profiles,
                    updated_profile,
                    updated_profile[CONF_PROFILE_ID],
                )
                if not errors:
                    profiles = [
                        updated_profile
                        if item.get(CONF_PROFILE_ID) == updated_profile[CONF_PROFILE_ID]
                        else item
                        for item in self._profiles
                    ]
                    return self.async_create_entry(data={CONF_PROFILES: profiles})

        return self.async_show_form(
            step_id="edit_details",
            data_schema=_profile_schema(self.hass, profile),
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


def _profile_schema(
    hass: HomeAssistant,
    profile: dict[str, Any] | None = None,
) -> vol.Schema:
    """Build the person profile schema."""
    profile = profile or {}

    return vol.Schema(
        {
            vol.Required(
                CONF_PERSON_ENTITY_ID,
                default=profile.get(CONF_PERSON_ENTITY_ID),
            ): EntitySelector(EntitySelectorConfig(domain="person")),
            vol.Required(
                CONF_NOTIFY_TARGETS,
                default=_targets_to_form(profile.get(CONF_NOTIFY_TARGETS, [])),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=_notify_target_options(hass),
                    multiple=True,
                    custom_value=True,
                )
            ),
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
    )


def _profile_from_user_input(
    hass: HomeAssistant,
    user_input: dict[str, Any],
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a stored profile from form input."""
    existing = existing or {}
    enabled_types = set(user_input.get(CONF_ENABLED_TYPES, []))
    enabled_types.add(TYPE_CRITICAL)

    person_entity_id = user_input[CONF_PERSON_ENTITY_ID]
    known_targets = _known_notify_targets(hass)

    return {
        CONF_PROFILE_ID: existing.get(CONF_PROFILE_ID, uuid4().hex),
        CONF_NAME: _person_name(hass, person_entity_id),
        CONF_TARGET_KEY: existing.get(CONF_TARGET_KEY)
        or _target_key_from_person_entity(person_entity_id),
        CONF_PERSON_ENTITY_ID: person_entity_id,
        CONF_NOTIFY_TARGETS: _targets_from_input(
            user_input[CONF_NOTIFY_TARGETS],
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

    if _person_exists(
        profiles,
        profile[CONF_PERSON_ENTITY_ID],
        current_profile_id,
    ):
        errors[CONF_PERSON_ENTITY_ID] = "duplicate_person"

    return errors


def _profile_select_options(profiles: list[dict[str, Any]]) -> list[dict[str, str]]:
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

    notify_services = hass.services.async_services().get("notify", {})
    for service in notify_services:
        if service in _IGNORED_NOTIFY_SERVICES:
            continue
        targets.add(f"notify.{service}")

    for entity_id in hass.states.async_entity_ids("notify"):
        targets.add(entity_id)

    return targets


def _notify_target_options(hass: HomeAssistant) -> list[dict[str, str]]:
    """Build selector options for available notify targets."""
    return [
        {
            "value": target,
            "label": _notify_target_label(hass, target),
        }
        for target in sorted(_known_notify_targets(hass))
    ]


def _notify_target_label(hass: HomeAssistant, target: str) -> str:
    """Return a readable label for a notify target."""
    state = hass.states.get(target)
    if state is not None:
        friendly_name = state.attributes.get("friendly_name")
        if friendly_name:
            return f"{friendly_name} ({target})"

    return target.removeprefix("notify.").replace("_", " ")


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
        target = _normalize_notify_target(raw_target, known_targets)
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


def _targets_to_form(value: Any) -> list[str]:
    """Render notify targets for the options form."""
    if isinstance(value, str):
        return _targets_from_input(value, set())
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def _optional_enabled_types(value: Any) -> list[str]:
    """Return non-critical enabled notification types."""
    if isinstance(value, str):
        value = [value]
    return [item for item in value if item in OPTIONAL_NOTIFICATION_TYPES]


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


def _normalize_target_key(value: Any) -> str:
    """Normalize a profile target key."""
    return (
        str(value or "")
        .strip()
        .casefold()
        .replace(" ", "_")
        .replace("-", "_")
    )
