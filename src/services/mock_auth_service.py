from copy import deepcopy
import re
from typing import Any

from config.roles import APPROVED_ROLES, ROLE_LABELS
from services.unit_display_service import (
    DISPLAY_MODE_DEFAULT,
    UNIT_SYSTEM_IMPERIAL,
    normalize_display_mode,
    normalize_unit_system,
)


DEFAULT_MOCK_USERS = [
    {
        "user_id": "dev_user_001",
        "display_name": "Plato Choi",
        "role": "standard_user",
        "preferences": {
            "display_mode": DISPLAY_MODE_DEFAULT,
            "unit_system": UNIT_SYSTEM_IMPERIAL,
        },
    },
    {
        "user_id": "dietitian_001",
        "display_name": "Dana Reed",
        "role": "dietitian",
        "preferences": {
            "display_mode": DISPLAY_MODE_DEFAULT,
            "unit_system": UNIT_SYSTEM_IMPERIAL,
        },
    },
    {
        "user_id": "reviewer_001",
        "display_name": "Chris Vale",
        "role": "reviewer",
        "preferences": {
            "display_mode": DISPLAY_MODE_DEFAULT,
            "unit_system": UNIT_SYSTEM_IMPERIAL,
        },
    },
    {
        "user_id": "admin_001",
        "display_name": "Morgan Hale",
        "role": "admin",
        "preferences": {
            "display_mode": DISPLAY_MODE_DEFAULT,
            "unit_system": UNIT_SYSTEM_IMPERIAL,
        },
    },
]

MOCK_USERS_SESSION_KEY = "mock_auth_users"
CURRENT_USER_SESSION_KEY = "mock_auth_current_user"


def _normalize_preferences(preferences: dict[str, Any] | None) -> dict[str, str]:
    preferences = preferences or {}
    return {
        "display_mode": normalize_display_mode(preferences.get("display_mode")),
        "unit_system": normalize_unit_system(preferences.get("unit_system")),
    }


def _hydrate_user(user: dict[str, Any]) -> dict[str, Any]:
    hydrated_user = deepcopy(user)
    hydrated_user["preferences"] = _normalize_preferences(hydrated_user.get("preferences"))
    return hydrated_user


def _normalize_display_name(display_name: str) -> str:
    return " ".join(display_name.split())


def _normalize_role(role: str) -> str:
    return role if role in APPROVED_ROLES else "standard_user"


def _build_user_lookup(users: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {user["user_id"]: user for user in users}


def _next_custom_user_id(existing_users: list[dict[str, str]]) -> str:
    pattern = re.compile(r"^mock_user_(\d+)$")
    highest = 0

    for user in existing_users:
        match = pattern.match(user["user_id"])
        if match:
            highest = max(highest, int(match.group(1)))

    return f"mock_user_{highest + 1:03d}"


def ensure_mock_auth_state(flask_session: Any) -> None:
    if MOCK_USERS_SESSION_KEY not in flask_session:
        flask_session[MOCK_USERS_SESSION_KEY] = [_hydrate_user(user) for user in DEFAULT_MOCK_USERS]

    users = [_hydrate_user(user) for user in flask_session[MOCK_USERS_SESSION_KEY]]
    flask_session[MOCK_USERS_SESSION_KEY] = users
    user_lookup = _build_user_lookup(users)

    current_user = flask_session.get(CURRENT_USER_SESSION_KEY)
    if not current_user or current_user.get("user_id") not in user_lookup:
        flask_session[CURRENT_USER_SESSION_KEY] = deepcopy(users[0])
    else:
        flask_session[CURRENT_USER_SESSION_KEY] = _hydrate_user(current_user)


def get_mock_users(flask_session: Any) -> list[dict[str, str]]:
    ensure_mock_auth_state(flask_session)
    return deepcopy(flask_session[MOCK_USERS_SESSION_KEY])


def get_current_mock_user(flask_session: Any) -> dict[str, str]:
    ensure_mock_auth_state(flask_session)
    return deepcopy(flask_session[CURRENT_USER_SESSION_KEY])


def select_mock_user(flask_session: Any, user_id: str) -> dict[str, str]:
    ensure_mock_auth_state(flask_session)
    users = flask_session[MOCK_USERS_SESSION_KEY]
    user_lookup = _build_user_lookup(users)

    if user_id not in user_lookup:
        raise ValueError("Selected mock user was not found.")

    selected_user = deepcopy(user_lookup[user_id])
    flask_session[CURRENT_USER_SESSION_KEY] = selected_user
    return selected_user


def create_mock_user(flask_session: Any, display_name: str, role: str) -> dict[str, str]:
    ensure_mock_auth_state(flask_session)

    normalized_display_name = _normalize_display_name(display_name)
    if not normalized_display_name:
        raise ValueError("Display name is required.")

    normalized_role = _normalize_role(role)
    users = deepcopy(flask_session[MOCK_USERS_SESSION_KEY])

    new_user = {
        "user_id": _next_custom_user_id(users),
        "display_name": normalized_display_name,
        "role": normalized_role,
        "preferences": _normalize_preferences(None),
    }
    users.append(new_user)

    flask_session[MOCK_USERS_SESSION_KEY] = users
    flask_session[CURRENT_USER_SESSION_KEY] = deepcopy(new_user)
    return deepcopy(new_user)


def apply_debug_override(
    flask_session: Any,
    base_user_id: str,
    role: str,
    display_name: str,
) -> dict[str, str]:
    ensure_mock_auth_state(flask_session)
    users = flask_session[MOCK_USERS_SESSION_KEY]
    user_lookup = _build_user_lookup(users)

    if base_user_id not in user_lookup:
        raise ValueError("Selected override account was not found.")

    base_user = deepcopy(user_lookup[base_user_id])
    normalized_display_name = _normalize_display_name(display_name) or base_user["display_name"]
    normalized_role = _normalize_role(role or base_user["role"])

    overridden_user = {
        "user_id": base_user["user_id"],
        "display_name": normalized_display_name,
        "role": normalized_role,
        "preferences": _normalize_preferences(base_user.get("preferences")),
    }
    flask_session[CURRENT_USER_SESSION_KEY] = overridden_user
    return deepcopy(overridden_user)


def update_current_user_preferences(flask_session: Any, *, display_mode: str, unit_system: str) -> dict[str, Any]:
    ensure_mock_auth_state(flask_session)
    normalized_preferences = _normalize_preferences(
        {
            "display_mode": display_mode,
            "unit_system": unit_system,
        }
    )

    users = [_hydrate_user(user) for user in flask_session[MOCK_USERS_SESSION_KEY]]
    current_user = _hydrate_user(flask_session[CURRENT_USER_SESSION_KEY])

    for user in users:
        if user["user_id"] == current_user["user_id"]:
            user["preferences"] = deepcopy(normalized_preferences)
            break

    current_user["preferences"] = deepcopy(normalized_preferences)
    flask_session[MOCK_USERS_SESSION_KEY] = users
    flask_session[CURRENT_USER_SESSION_KEY] = current_user
    return deepcopy(current_user)


def build_auth_shell_context(flask_session: Any) -> dict[str, Any]:
    current_user = get_current_mock_user(flask_session)
    mock_users = get_mock_users(flask_session)

    return {
        "current_user": current_user,
        "mock_users": mock_users,
        "available_roles": [
            {"value": role, "label": ROLE_LABELS[role]}
            for role in APPROVED_ROLES
        ],
    }
