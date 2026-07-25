"""Cross-charge detection service."""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import BatteryState, CrossChargeEvent, DetectorResult
from .registry import BatteryRegistry
from .rules import RuleEngine


@dataclass(slots=True)
class CrossChargeDetector:
    registry: BatteryRegistry = field(default_factory=BatteryRegistry)
    rules: RuleEngine = field(default_factory=RuleEngine)

    def upsert(self, battery: BatteryState) -> None:
        self.registry.upsert(battery)

    def detect(self) -> DetectorResult:
        batteries = self.registry.all()
        events = self.rules.evaluate(batteries)
        max_soc_difference = 0.0
        for index, battery in enumerate(batteries):
            for other in batteries[index + 1 :]:
                max_soc_difference = max(max_soc_difference, abs(battery.soc - other.soc))
        return DetectorResult(
            events=events,
            max_soc_difference=max_soc_difference,
            battery_count=len(batteries),
        )

