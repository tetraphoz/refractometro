from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import StrEnum

from experiments.voltage_sweep import MeasurementPoint


def _new_uid() -> str:
    """Create a stable identifier from the creation timestamp."""
    created_at_ns = time.time_ns()
    return hashlib.sha256(str(created_at_ns).encode()).hexdigest()


class RunStatus(StrEnum):
    """Persistent lifecycle state of a run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class SessionKind(StrEnum):
    """Purpose of a laboratory measurement session."""

    SAMPLE = "sample"
    CALIBRATION = "calibration"
    CONTROL = "control"


class SessionStatus(StrEnum):
    """Lifecycle state of a laboratory measurement session."""

    PREPARED = "prepared"
    ACQUIRING = "acquiring"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


@dataclass
class MeasurementSession:
    """Group of raw runs acquired for one laboratory purpose."""

    label: str
    kind: SessionKind
    expected_runs: int
    created_at: float = field(default_factory=time.time)
    uid: str = field(default_factory=_new_uid)
    status: SessionStatus = SessionStatus.PREPARED
    run_uids: list[str] = field(default_factory=list)
    protocol_parameters: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.expected_runs < 1:
            raise ValueError("Una sesión necesita al menos una corrida")

    def add_run_uid(self, run_uid: str) -> None:
        """Attach a raw run once, preserving acquisition order."""
        if not run_uid:
            raise ValueError("La corrida necesita un UID")
        if run_uid in self.run_uids:
            raise ValueError("La corrida ya pertenece a esta sesión")
        self.run_uids.append(run_uid)


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
    uid: str = field(default_factory=_new_uid)
    status: RunStatus = RunStatus.PENDING
    source_uids: list[str] = field(default_factory=list)
    analysis_kind: str | None = None
    analysis_parameters: dict[str, object] = field(default_factory=dict)
