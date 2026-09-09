from __future__ import annotations

import math
from collections.abc import Iterable

from app.models import (
    MeasurementSession,
    RunRecord,
    RunStatus,
    SessionKind,
    SweepProtocol,
)
from app.run_processing import AverageResult, average_runs_with_statistics
from experiments.calibration import CalibrationCurve


def completed_session_runs(
    session: MeasurementSession,
    runs: Iterable[RunRecord],
) -> list[RunRecord]:
    """Return completed raw runs attached to a session in acquisition order."""
    runs_by_uid = {run.uid: run for run in runs}
    completed_runs = []

    for run_uid in session.run_uids:
        run = runs_by_uid.get(run_uid)
        if run is None:
            raise ValueError("Falta una corrida fuente de la sesión")
        if run.session_uid != session.uid:
            raise ValueError("La corrida fuente pertenece a otra sesión")
        if run.status is RunStatus.COMPLETED and run.measurements:
            completed_runs.append(run)

    return completed_runs


def _validate_protocol(
    protocol: SweepProtocol,
    runs: Iterable[RunRecord],
) -> None:
    expected_start = min(protocol.start_position_mm, protocol.end_position_mm)
    expected_end = max(protocol.start_position_mm, protocol.end_position_mm)

    for run in runs:
        positions = [point.position_mm for point in run.measurements]
        if not positions:
            raise ValueError("La corrida no tiene mediciones")
        if run.expected_points != protocol.number_of_points:
            raise ValueError("La corrida no coincide con los puntos del protocolo")
        try:
            stabilization_time_s = float(run.stabilization_time_s or "")
        except ValueError as exc:
            raise ValueError("La corrida no tiene estabilización válida") from exc
        if not math.isclose(
            stabilization_time_s,
            protocol.stabilization_time_s,
            abs_tol=1e-9,
        ):
            raise ValueError(
                "La corrida no coincide con la estabilización del protocolo"
            )
        if not (
            math.isclose(min(positions), expected_start, abs_tol=1e-9)
            and math.isclose(max(positions), expected_end, abs_tol=1e-9)
        ):
            raise ValueError("La corrida no coincide con el rango del protocolo")


def average_session(
    session: MeasurementSession,
    runs: Iterable[RunRecord],
) -> AverageResult:
    """Average completed sources after validating the session protocol."""
    completed_runs = completed_session_runs(session, runs)
    if len(completed_runs) < 2:
        raise ValueError("La sesión necesita al menos dos corridas completas")

    _validate_protocol(session.sweep_protocol(), completed_runs)
    return average_runs_with_statistics(completed_runs)


def calibration_from_session(
    session: MeasurementSession,
    runs: Iterable[RunRecord],
) -> CalibrationCurve:
    """Build a calibration curve from the average of a no-sample session."""
    if session.kind is not SessionKind.CALIBRATION:
        raise ValueError("La sesión debe ser de calibración")

    return CalibrationCurve(average_session(session, runs).measurements)
