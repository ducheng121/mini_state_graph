"""Reducer functions for merging state updates."""

from __future__ import annotations

from typing import Any


def override(_: Any, new_value: Any) -> Any:
    """Replace the previous value with the new value."""

    return new_value


def append_list(old_value: Any, new_value: Any) -> list[Any]:
    """Append items into a list field."""

    old_items = list(old_value or [])
    if isinstance(new_value, list):
        return old_items + new_value
    return old_items + [new_value]


def add_messages_like(old_value: Any, new_value: Any) -> list[Any]:
    """Merge list items by message id when possible, otherwise append."""

    existing = list(old_value or [])
    incoming = new_value if isinstance(new_value, list) else [new_value]

    index_by_id = {
        item["id"]: idx
        for idx, item in enumerate(existing)
        if isinstance(item, dict) and "id" in item
    }

    merged = list(existing)
    for item in incoming:
        if isinstance(item, dict) and "id" in item and item["id"] in index_by_id:
            merged[index_by_id[item["id"]]] = item
        else:
            merged.append(item)

    return merged
