"""Battery discovery and detection manager."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from .diagnostics import DiagnosticsSnapshot, build_diagnostics
from .detector import CrossChargeDetector
from .models import AnalysisReport, BatteryState, DetectorResult, StopEvent
from .repair import build_repair_issue, repair_issue_payload
from .registry import BatteryRegistry

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


@dataclass(slots=True)
class BatteryManager:
    """Keep the registry and detector in sync."""

    registry: BatteryRegistry = field(default_factory=BatteryRegistry)
    detector: CrossChargeDetector = field(default_factory=CrossChargeDetector)
    stop_events: deque[StopEvent] = field(default_factory=lambda: deque(maxlen=10))
    hass: HomeAssistant | None = None

    def update_battery(self, battery: BatteryState) -> None:
        self.registry.upsert(battery)
        self.detector.registry = self.registry

    def detect(self) -> DetectorResult:
        self.detector.registry = self.registry
        return self.detector.detect()

    def analyze(self) -> AnalysisReport:
        result = self.detect()
        snapshot = build_diagnostics(result)
        issue = build_repair_issue(snapshot)
        if result.events:
            for event in result.events:
                self.record_stop_event(event.source, event.reason, event.severity.value)
        return AnalysisReport(
            result=result,
            diagnostics={
                "battery_count": snapshot.battery_count,
                "cross_charge_events": snapshot.cross_charge_events,
                "largest_transfer": snapshot.largest_transfer,
                "imbalance": snapshot.imbalance,
                "critical": snapshot.critical,
            },
            repair_issue=repair_issue_payload(issue),
        )

    def record_stop_event(self, battery: str, reason: str, status: str) -> None:
        self.stop_events.appendleft(
            StopEvent(
                timestamp=datetime.now(timezone.utc).isoformat(),
                battery=battery,
                reason=reason,
                status=status,
            )
        )
        if self.hass is not None:
            for sensor in self.hass.data.get("cross_battery_charge_guard", {}).get("stop_event_sensors", []):
                sensor.refresh()

    def stop_log(self) -> list[StopEvent]:
        return list(self.stop_events)
