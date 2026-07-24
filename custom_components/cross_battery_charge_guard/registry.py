"""Battery registry."""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import BatteryState


@dataclass(slots=True)
class BatteryRegistry:
    """Deduplicate and retain the latest known battery state."""

    _batteries: dict[str, BatteryState] = field(default_factory=dict)

    def upsert(self, battery: BatteryState) -> None:
        self._batteries[battery.id] = battery

    def all(self) -> list[BatteryState]:
        return list(self._batteries.values())

    def get(self, battery_id: str) -> BatteryState | None:
        return self._batteries.get(battery_id)

    def clear(self) -> None:
        self._batteries.clear()

