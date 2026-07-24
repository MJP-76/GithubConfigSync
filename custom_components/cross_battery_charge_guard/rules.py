"""Detection rules."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from .const import DEFAULT_DEADBAND, DEFAULT_MAX_BATTERY_TEMP, DEFAULT_MAX_CROSS_CHARGE_WATTS, DEFAULT_MAX_SOC_DIFFERENCE
from .models import BatteryState, CrossChargeEvent, Severity


@dataclass(slots=True, frozen=True)
class RuleContext:
    batteries: list[BatteryState]


class Rule:
    def evaluate(self, context: RuleContext) -> list[CrossChargeEvent]:
        raise NotImplementedError


class CrossChargeRule(Rule):
    def __init__(self, max_cross_charge_watts: float = DEFAULT_MAX_CROSS_CHARGE_WATTS) -> None:
        self.max_cross_charge_watts = max_cross_charge_watts

    def evaluate(self, context: RuleContext) -> list[CrossChargeEvent]:
        events: list[CrossChargeEvent] = []
        for source, destination in combinations(context.batteries, 2):
            if source.power > self.max_cross_charge_watts and destination.power < -self.max_cross_charge_watts:
                events.append(
                    CrossChargeEvent(
                        source=source.name,
                        destination=destination.name,
                        watts=min(source.power, abs(destination.power)),
                        severity=Severity.warning,
                        reason="charging another battery",
                        metadata={"source_id": source.id, "destination_id": destination.id},
                    )
                )
            if destination.power > self.max_cross_charge_watts and source.power < -self.max_cross_charge_watts:
                events.append(
                    CrossChargeEvent(
                        source=destination.name,
                        destination=source.name,
                        watts=min(destination.power, abs(source.power)),
                        severity=Severity.warning,
                        reason="charging another battery",
                        metadata={"source_id": destination.id, "destination_id": source.id},
                    )
                )
        return events


class SOCDifferenceRule(Rule):
    def __init__(self, max_soc_difference: float = DEFAULT_MAX_SOC_DIFFERENCE) -> None:
        self.max_soc_difference = max_soc_difference

    def evaluate(self, context: RuleContext) -> list[CrossChargeEvent]:
        events: list[CrossChargeEvent] = []
        for source, destination in combinations(context.batteries, 2):
            difference = abs(source.soc - destination.soc)
            if difference >= self.max_soc_difference:
                events.append(
                    CrossChargeEvent(
                        source=source.name,
                        destination=destination.name,
                        watts=difference,
                        severity=Severity.info if difference < 40 else Severity.warning,
                        reason="battery state of charge diverged",
                        metadata={"soc_difference": difference},
                    )
                )
        return events


class ThermalRule(Rule):
    def __init__(self, max_temperature: float = DEFAULT_MAX_BATTERY_TEMP) -> None:
        self.max_temperature = max_temperature

    def evaluate(self, context: RuleContext) -> list[CrossChargeEvent]:
        return [
            CrossChargeEvent(
                source=battery.name,
                destination=battery.name,
                watts=battery.temperature,
                severity=Severity.critical,
                reason="battery temperature too high",
                metadata={"battery_id": battery.id},
            )
            for battery in context.batteries
            if battery.temperature >= self.max_temperature
        ]


class RuleEngine:
    def __init__(self, rules: list[Rule] | None = None) -> None:
        self.rules = rules or [CrossChargeRule(), SOCDifferenceRule(), ThermalRule()]

    def evaluate(self, batteries: list[BatteryState]) -> list[CrossChargeEvent]:
        context = RuleContext(batteries=batteries)
        events: list[CrossChargeEvent] = []
        for rule in self.rules:
            events.extend(rule.evaluate(context))
        return events

