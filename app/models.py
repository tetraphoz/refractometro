from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import StrEnum

from experiments.voltage_sweep import MeasurementPoint


def _new_run_uid() -> str:
    """Create a stable identifier from the run start timestamp."""
    started_at_ns = time.time_ns()
    return hashlib.sha256(str(started_at_ns).encode()).hexdigest()


class RunStatus(StrEnum):
    """Persistent lifecycle state of a run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


@dataclass
class RunRecord:
    """Typed record for a run shown in the history panel."""

    id: int
    kind: str
    label: str
    curve_tag: str
    measurements: list[MeasurementPoint] = field(default_factory=list)
    peaks: list[MeasurementPoint] = field(default_factory=list)
    filename: str | None = None
    row_tag: str | None = None
    text_tag: str | None = None
    expected_points: int | None = None
    stabilization_time_s: str | None = ""
    laser_on_time_s: float | None = None
    created_at: float = field(default_factory=time.time)
    uid: str = field(default_factory=_new_run_uid)
    status: RunStatus = RunStatus.PENDING
    source_uids: list[str] = field(default_factory=list)
    analysis_kind: str | None = None
    analysis_parameters: dict[str, object] = field(default_factory=dict)
