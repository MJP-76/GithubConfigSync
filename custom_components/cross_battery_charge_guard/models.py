"""Internal models for cross-charge detection."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Severity(StrEnum):
    info = "info"
    warning = "warning"
    critical = "critical"


@dataclass(slots=True, frozen=True)
class BatteryState:
    id: str
    name: str
    soc: float
    voltage: float
    current: float
    power: float
    charging: bool
    discharging: bool
    temperature: float
    online: bool


@dataclass(slots=True, frozen=True)
class CrossChargeEvent:
    source: str
    destination: str
    watts: float
    severity: Severity
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class StopEvent:
    timestamp: str
    battery: str
    reason: str
    status: str


@dataclass(slots=True, frozen=True)
class DetectorResult:
    events: list[CrossChargeEvent]
    max_soc_difference: float
    battery_count: int


@dataclass(slots=True, frozen=True)
class AnalysisReport:
    result: DetectorResult
    diagnostics: dict[str, object]
    repair_issue: dict[str, object] | None
