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


@dataclass(frozen=True)
class SweepProtocol:
    """Acquisition settings shared by every raw run in a session."""

    start_position_mm: float
    end_position_mm: float
    number_of_points: int
    stabilization_time_s: float

    def __post_init__(self) -> None:
        if self.number_of_points < 2:
            raise ValueError("El protocolo necesita al menos dos puntos")
        if self.stabilization_time_s < 0:
            raise ValueError("El tiempo de estabilización no puede ser negativo")

    def as_parameters(self) -> dict[str, float | int]:
        """Serialize the protocol as JSON-compatible session parameters."""
        return {
            "start_position_mm": self.start_position_mm,
            "end_position_mm": self.end_position_mm,
            "number_of_points": self.number_of_points,
            "stabilization_time_s": self.stabilization_time_s,
        }

    @classmethod
    def from_parameters(cls, parameters: dict[str, object]) -> SweepProtocol:
        """Build a protocol from persisted JSON-compatible parameters."""
        try:
            return cls(
                start_position_mm=float(parameters["start_position_mm"]),
                end_position_mm=float(parameters["end_position_mm"]),
                number_of_points=int(parameters["number_of_points"]),
                stabilization_time_s=float(parameters["stabilization_time_s"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                "La sesión no tiene un protocolo de barrido válido"
            ) from exc


class SessionStatus(StrEnum):
    """Lifecycle state of a laboratory measurement session."""

    PREPARED = "prepared"
    ACQUIRING = "acquiring"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


_SESSION_TRANSITIONS = {
    SessionStatus.PREPARED: {SessionStatus.ACQUIRING, SessionStatus.CANCELLED},
    SessionStatus.ACQUIRING: {
        SessionStatus.PAUSED,
        SessionStatus.COMPLETED,
        SessionStatus.CANCELLED,
        SessionStatus.FAILED,
        SessionStatus.INTERRUPTED,
    },
    SessionStatus.PAUSED: {
        SessionStatus.ACQUIRING,
        SessionStatus.CANCELLED,
        SessionStatus.INTERRUPTED,
    },
    SessionStatus.COMPLETED: set(),
    SessionStatus.CANCELLED: set(),
    SessionStatus.FAILED: set(),
    SessionStatus.INTERRUPTED: set(),
}


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

    def transition_to(self, status: SessionStatus) -> None:
        """Apply a valid lifecycle transition to the session."""
        if status not in _SESSION_TRANSITIONS[self.status]:
            raise ValueError(
                f"No se puede cambiar una sesión de {self.status} a {status}"
            )
        self.status = status

    def set_protocol_parameters(self, parameters: dict[str, object]) -> None:
        """Set acquisition settings before the session starts."""
        if self.status is not SessionStatus.PREPARED:
            raise ValueError("El protocolo solo puede cambiarse antes de adquirir")
        self.protocol_parameters = dict(parameters)

    def set_sweep_protocol(self, protocol: SweepProtocol) -> None:
        """Set the typed sweep settings used for all raw session runs."""
        self.set_protocol_parameters(protocol.as_parameters())

    def sweep_protocol(self) -> SweepProtocol:
        """Return the persisted typed acquisition settings for the session."""
        return SweepProtocol.from_parameters(self.protocol_parameters)

    def add_run_uid(self, run_uid: str) -> None:
        """Attach a raw run once, preserving acquisition order."""
        if self.status not in {
            SessionStatus.PREPARED,
            SessionStatus.ACQUIRING,
            SessionStatus.PAUSED,
        }:
            raise ValueError("No se pueden agregar corridas a una sesión finalizada")
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
    session_uid: str | None = None
