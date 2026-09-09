from __future__ import annotations

from pathlib import Path

import pytest

from app.models import (
    MeasurementSession,
    RunRecord,
    RunStatus,
    SessionKind,
    SessionStatus,
    SweepProtocol,
)
from app.run_repository import RunRepository
from app.session_processing import (
    average_session_run,
    calibration_session_run,
    corrected_session_run,
)
from experiments.voltage_sweep import MeasurementPoint


def raw_run(run_id: int, voltages: tuple[float, float]) -> RunRecord:
    return RunRecord(
        id=run_id,
        kind="barrido",
        label=f"Barrido #{run_id}",
        curve_tag=f"curve-{run_id}",
        measurements=[
            MeasurementPoint(0.0, voltages[0]),
            MeasurementPoint(1.0, voltages[1]),
        ],
        expected_points=2,
        stabilization_time_s="0.1",
        status=RunStatus.COMPLETED,
    )


def completed_session(
    repository: RunRepository,
    *,
    label: str,
    kind: SessionKind,
    runs: list[RunRecord],
) -> MeasurementSession:
    session = MeasurementSession(label, kind, expected_runs=len(runs))
    session.set_sweep_protocol(SweepProtocol(0.0, 1.0, 2, 0.1))
    repository.save_session(session)
    session.transition_to(SessionStatus.ACQUIRING)

    for run in runs:
        repository.save(run)
        repository.attach_run_to_session(run, session)

    session.transition_to(SessionStatus.COMPLETED)
    repository.save_session(session)
    return session


def test_persisted_v3_workflow_averages_calibrates_and_corrects(tmp_path: Path):
    database_path = tmp_path / "refractometro.sqlite3"
    repository = RunRepository(database_path)
    calibration_session = completed_session(
        repository,
        label="Blanco",
        kind=SessionKind.CALIBRATION,
        runs=[raw_run(1, (1.0, 1.0)), raw_run(2, (1.2, 1.2))],
    )
    sample_session = completed_session(
        repository,
        label="Muestra A",
        kind=SessionKind.SAMPLE,
        runs=[raw_run(3, (3.0, 4.0)), raw_run(4, (3.2, 4.2))],
    )

    calibration = calibration_session_run(
        calibration_session,
        repository.list_runs_for_session(calibration_session.uid),
        run_id=5,
        curve_tag="curve-5",
    )
    sample_average = average_session_run(
        sample_session,
        repository.list_runs_for_session(sample_session.uid),
        run_id=6,
        curve_tag="curve-6",
    )
    corrected = corrected_session_run(
        sample_average,
        calibration,
        run_id=7,
        curve_tag="curve-7",
    )
    repository.save(calibration)
    repository.save(sample_average)
    repository.save(corrected)
    repository.close()

    restored_repository = RunRepository(database_path)
    restored_sample = restored_repository.get_session(sample_session.uid)
    restored_calibration = restored_repository.get(5)
    restored_average = restored_repository.get(6)
    restored_corrected = restored_repository.get(7)

    assert restored_sample is not None
    assert restored_sample.status is SessionStatus.COMPLETED
    assert len(restored_sample.run_uids) == 2
    assert restored_calibration is not None
    assert restored_average is not None
    assert restored_corrected is not None
    assert restored_calibration.analysis_kind == "calibration_average"
    assert restored_average.analysis_kind == "session_average"
    assert restored_corrected.analysis_kind == "calibration_corrected"
    assert [point.position_mm for point in restored_corrected.measurements] == [
        0.0,
        1.0,
    ]
    assert [
        point.voltage_v for point in restored_corrected.measurements
    ] == pytest.approx([2.0, 3.0])
    assert restored_corrected.source_uids == [
        restored_average.uid,
        restored_calibration.uid,
    ]
    assert restored_corrected.analysis_parameters["sample_average_uid"] == (
        restored_average.uid
    )
    assert restored_corrected.analysis_parameters["calibration_uid"] == (
        restored_calibration.uid
    )
    restored_repository.close()
