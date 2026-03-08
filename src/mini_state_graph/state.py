"""State spec and merge logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, get_type_hints

from .errors import ReducerExecutionError, UnknownStateKeyError
from .reducers import override

Reducer = Callable[[Any, Any], Any]
State = dict[str, Any]
Update = dict[str, Any]


@dataclass(frozen=True, slots=True)
class StateField:
    """Declares one allowed state key and its reducer."""

    name: str
    reducer: Reducer = override


@dataclass(slots=True)
class StateSpec:
    """Defines how individual state keys should be merged."""

    reducers: dict[str, Reducer] = field(default_factory=dict)
    allowed_keys: set[str] | None = None

    def merge(self, state: State, update: Update) -> State:
        merged = dict(state)

        for key, new_value in update.items():
            if self.allowed_keys is not None and key not in self.allowed_keys:
                raise UnknownStateKeyError(f"Unknown state key: {key}")

            if key not in merged:
                merged[key] = new_value
                continue

            reducer = self.reducers.get(key, override)
            try:
                merged[key] = reducer(merged[key], new_value)
            except Exception as exc:
                raise ReducerExecutionError(f"Reducer failed for state key '{key}'") from exc

        return merged

    @classmethod
    def from_fields(cls, fields: list[str] | tuple[str, ...], *, reducers: dict[str, Reducer] | None = None) -> "StateSpec":
        reducer_map = dict(reducers or {})
        return cls(reducers=reducer_map, allowed_keys=set(fields))

    @classmethod
    def from_field_defs(cls, fields: list[StateField] | tuple[StateField, ...]) -> "StateSpec":
        reducers = {field.name: field.reducer for field in fields}
        return cls(reducers=reducers, allowed_keys={field.name for field in fields})

    @classmethod
    def from_typed_dict(
        cls,
        schema: type[Any],
        *,
        reducers: dict[str, Reducer] | None = None,
    ) -> "StateSpec":
        allowed_keys = set(get_type_hints(schema).keys())
        return cls(reducers=dict(reducers or {}), allowed_keys=allowed_keys)
