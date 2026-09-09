from __future__ import annotations

from collections.abc import Iterable

from app.models import MeasurementSession, RunRecord, RunStatus, SessionKind
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


def average_session(
    session: MeasurementSession,
    runs: Iterable[RunRecord],
) -> AverageResult:
    """Average the valid raw runs explicitly attached to a session."""
    completed_runs = completed_session_runs(session, runs)
    if len(completed_runs) < 2:
        raise ValueError("La sesión necesita al menos dos corridas completas")

    return average_runs_with_statistics(completed_runs)


def calibration_from_session(
    session: MeasurementSession,
    runs: Iterable[RunRecord],
) -> CalibrationCurve:
    """Build a calibration curve from the average of a no-sample session."""
    if session.kind is not SessionKind.CALIBRATION:
        raise ValueError("La sesión debe ser de calibración")

    return CalibrationCurve(average_session(session, runs).measurements)
