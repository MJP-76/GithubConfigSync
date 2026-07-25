"""Repairs helper."""

from __future__ import annotations

from dataclasses import dataclass

from .diagnostics import DiagnosticsSnapshot


@dataclass(slots=True, frozen=True)
class RepairIssue:
    title: str
    body: str
    severity: str


def build_repair_issue(snapshot: DiagnosticsSnapshot) -> RepairIssue | None:
    if not snapshot.critical and snapshot.cross_charge_events == 0:
        return None

    body = "Cross-charge behavior was detected. Check inverter priorities, wiring, and battery settings."
    if snapshot.critical:
        body = "A critical battery condition was detected. Check battery temperature and inverter behavior immediately."
    return RepairIssue(
        title="Cross Charge Guard detected a battery issue",
        body=body,
        severity="critical" if snapshot.critical else "warning",
    )


def repair_issue_payload(issue: RepairIssue | None) -> dict[str, object] | None:
    if issue is None:
        return None
    return {
        "title": issue.title,
        "body": issue.body,
        "severity": issue.severity,
    }
