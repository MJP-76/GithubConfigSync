"""Diagnostics helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .models import DetectorResult
from .models import Severity


@dataclass(slots=True, frozen=True)
class DiagnosticsSnapshot:
    battery_count: int
    cross_charge_events: int
    largest_transfer: float
    imbalance: float
    critical: bool


def build_diagnostics(result: DetectorResult) -> DiagnosticsSnapshot:
    largest_transfer = max((abs(event.watts) for event in result.events), default=0.0)
    critical = any(event.severity == Severity.critical for event in result.events)
    return DiagnosticsSnapshot(
        battery_count=result.battery_count,
        cross_charge_events=len(result.events),
        largest_transfer=largest_transfer,
        imbalance=result.max_soc_difference,
        critical=critical,
    )


def diagnostics_payload(snapshot: DiagnosticsSnapshot) -> dict[str, object]:
    return asdict(snapshot)
