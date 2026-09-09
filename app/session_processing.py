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


def average_session_run(
    session: MeasurementSession,
    runs: Iterable[RunRecord],
    *,
    run_id: int,
    curve_tag: str,
) -> RunRecord:
    """Create a completed derived run with average provenance and statistics."""
    average = average_session(session, runs)
    positions = [point.position_mm for point in average.points]
    return RunRecord(
        id=run_id,
        kind="promedio",
        label=f"Promedio de {session.label}",
        curve_tag=curve_tag,
        measurements=average.measurements,
        expected_points=len(average.points),
        status=RunStatus.COMPLETED,
        source_uids=list(average.source_uids),
        analysis_kind="session_average",
        analysis_parameters={
            "analysis_version": "v3",
            "source_session_uid": session.uid,
            "source_count": len(average.source_uids),
            "position_range_mm": [min(positions), max(positions)],
            "point_count": len(average.points),
            "interpolation": "linear_common_grid",
            "protocol": session.sweep_protocol().as_parameters(),
            "standard_deviation_v": [
                point.standard_deviation_v for point in average.points
            ],
            "sample_counts": [point.sample_count for point in average.points],
        },
    )


def calibration_session_run(
    session: MeasurementSession,
    runs: Iterable[RunRecord],
    *,
    run_id: int,
    curve_tag: str,
) -> RunRecord:
    """Create a derived calibration run from an averaged no-sample session."""
    if session.kind is not SessionKind.CALIBRATION:
        raise ValueError("La sesión debe ser de calibración")

    calibration = average_session_run(
        session,
        runs,
        run_id=run_id,
        curve_tag=curve_tag,
    )
    calibration.kind = "calibracion"
    calibration.label = f"Calibración promedio de {session.label}"
    calibration.analysis_kind = "calibration_average"
    return calibration


def corrected_session_run(
    sample_average: RunRecord,
    calibration: RunRecord,
    *,
    run_id: int,
    curve_tag: str,
) -> RunRecord:
    """Subtract a compatible averaged calibration from an averaged sample."""
    if sample_average.analysis_kind != "session_average":
        raise ValueError("La muestra debe ser un promedio de sesión")
    if calibration.analysis_kind != "calibration_average":
        raise ValueError("La referencia debe ser una calibración promedio")
    if (
        sample_average.status is not RunStatus.COMPLETED
        or calibration.status is not RunStatus.COMPLETED
    ):
        raise ValueError("La muestra y la calibración deben estar completadas")

    sample_protocol = SweepProtocol.from_parameters(
        sample_average.analysis_parameters.get("protocol", {})
    )
    calibration_protocol = SweepProtocol.from_parameters(
        calibration.analysis_parameters.get("protocol", {})
    )
    if sample_protocol != calibration_protocol:
        raise ValueError("La calibración no es compatible con el protocolo de muestra")

    measurements = CalibrationCurve(calibration.measurements).subtract(
        sample_average.measurements
    )
    return RunRecord(
        id=run_id,
        kind="corregido",
        label=f"Corregido de {sample_average.label}",
        curve_tag=curve_tag,
        measurements=measurements,
        expected_points=len(measurements),
        status=RunStatus.COMPLETED,
        source_uids=[sample_average.uid, calibration.uid],
        analysis_kind="calibration_corrected",
        analysis_parameters={
            "analysis_version": "v3",
            "correction_order": "average_then_subtract_calibration",
            "sample_average_uid": sample_average.uid,
            "calibration_uid": calibration.uid,
            "protocol": sample_protocol.as_parameters(),
        },
    )


def calibration_from_session(
    session: MeasurementSession,
    runs: Iterable[RunRecord],
) -> CalibrationCurve:
    """Build a calibration curve from the average of a no-sample session."""
    if session.kind is not SessionKind.CALIBRATION:
        raise ValueError("La sesión debe ser de calibración")

    return CalibrationCurve(average_session(session, runs).measurements)
