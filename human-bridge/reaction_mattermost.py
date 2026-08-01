"""Pure helpers for detecting Principal-authored Mattermost reactions.

Kept separate from ``main.py`` so channel classification, targeting and
first-run backfill semantics can be tested without a live appliance or DB.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional


DIRECT_CHANNEL = "D"
GROUP_CHANNEL = "G"
TEAM_CHANNELS = frozenset({"O", "P"})


def configured_human_email(explicit_email: str, admin_email: str) -> str:
    """Use the appliance login identity; never infer it from another appliance."""
    return (explicit_email or admin_email).strip().lower()


def merge_channels(*channel_sets: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Merge Mattermost channel listings by id without duplicate polling."""
    merged: dict[str, dict[str, Any]] = {}
    for channels in channel_sets:
        for channel in channels:
            channel_id = str(channel.get("id") or "")
            if channel_id:
                merged[channel_id] = dict(channel)
    return list(merged.values())


def first_poll_params(
    cursor: Optional[str], *, now_ms: int, backfill_hours: int = 168, limit: int = 50
) -> dict[str, int]:
    """Return a bounded query: durable cursor, or a recent first-run window."""
    params = {"page": 0, "per_page": limit}
    if cursor:
        params["since"] = int(cursor)
    else:
        params["since"] = max(0, now_ms - max(1, backfill_hours) * 3_600_000)
    return params


def target_employee_id(
    *,
    channel_type: str,
    message: str,
    principal_id: str,
    member_ids: Iterable[str],
    employees_by_mattermost_id: Mapping[str, int],
    employees_by_username: Mapping[str, int],
) -> Optional[int]:
    """Resolve a DM peer automatically; require explicit mentions elsewhere."""
    if channel_type == DIRECT_CHANNEL:
        candidates = {
            employees_by_mattermost_id[user_id]
            for user_id in member_ids
            if user_id != principal_id and user_id in employees_by_mattermost_id
        }
        return next(iter(candidates)) if len(candidates) == 1 else None

    # Group DMs and team channels can involve multiple employees. An explicit
    # mention is therefore the only unambiguous routing signal.
    lowered = message.lower()
    for username, employee_id in employees_by_username.items():
        if f"@{username.lower()}" in lowered:
            return employee_id
    return None


def is_principal_post(post: Mapping[str, Any], principal_id: str) -> bool:
    """Exclude employee bots, system posts and every non-Principal author."""
    return bool(principal_id) and post.get("user_id") == principal_id
