from __future__ import annotations

import pytest

from app.models import (
    MeasurementSession,
    RunRecord,
    RunStatus,
    SessionKind,
    SweepProtocol,
)
from app.session_processing import (
    average_session,
    average_session_run,
    calibration_from_session,
    completed_session_runs,
)
from experiments.voltage_sweep import MeasurementPoint


def make_run(
    run_id: int,
    session_uid: str,
    status: RunStatus = RunStatus.COMPLETED,
) -> RunRecord:
    return RunRecord(
        id=run_id,
        kind="barrido",
        label=f"Barrido #{run_id}",
        curve_tag=f"curve-{run_id}",
        measurements=[
            MeasurementPoint(0.0, float(run_id)),
            MeasurementPoint(1.0, float(run_id + 1)),
        ],
        status=status,
        expected_points=2,
        stabilization_time_s="0.1",
        session_uid=session_uid,
    )


def test_completed_session_runs_excludes_non_completed_sources():
    session = MeasurementSession("Muestra A", SessionKind.SAMPLE, expected_runs=3)
    first = make_run(1, session.uid)
    failed = make_run(2, session.uid, RunStatus.FAILED)
    last = make_run(3, session.uid)
    for run in (first, failed, last):
        session.add_run_uid(run.uid)

    assert completed_session_runs(session, [first, failed, last]) == [first, last]


def test_average_session_uses_explicit_session_sources():
    session = MeasurementSession("Muestra A", SessionKind.SAMPLE, expected_runs=2)
    session.set_sweep_protocol(SweepProtocol(0.0, 1.0, 2, 0.1))
    first = make_run(1, session.uid)
    second = make_run(3, session.uid)
    unrelated = make_run(10, "other-session")
    session.add_run_uid(first.uid)
    session.add_run_uid(second.uid)

    average = average_session(session, [unrelated, second, first])

    assert average.measurements == [
        MeasurementPoint(0.0, 2.0),
        MeasurementPoint(1.0, 3.0),
    ]
    assert average.source_uids == (first.uid, second.uid)


def test_average_session_requires_two_completed_runs():
    session = MeasurementSession("Muestra A", SessionKind.SAMPLE, expected_runs=2)
    session.set_sweep_protocol(SweepProtocol(0.0, 1.0, 2, 0.1))
    run = make_run(1, session.uid)
    session.add_run_uid(run.uid)

    with pytest.raises(ValueError, match="al menos dos"):
        average_session(session, [run])


def test_average_session_run_keeps_provenance_and_repeatability_data():
    session = MeasurementSession("Muestra A", SessionKind.SAMPLE, expected_runs=2)
    session.set_sweep_protocol(SweepProtocol(0.0, 1.0, 2, 0.1))
    first = make_run(1, session.uid)
    second = make_run(3, session.uid)
    session.add_run_uid(first.uid)
    session.add_run_uid(second.uid)

    derived = average_session_run(
        session,
        [first, second],
        run_id=10,
        curve_tag="curve-10",
    )

    assert derived.kind == "promedio"
    assert derived.status is RunStatus.COMPLETED
    assert derived.source_uids == [first.uid, second.uid]
    assert derived.session_uid is None
    assert derived.analysis_kind == "session_average"
    assert derived.analysis_parameters == {
        "analysis_version": "v3",
        "source_session_uid": session.uid,
        "source_count": 2,
        "position_range_mm": [0.0, 1.0],
        "point_count": 2,
        "interpolation": "linear_common_grid",
        "protocol": session.sweep_protocol().as_parameters(),
        "standard_deviation_v": [1.0, 1.0],
        "sample_counts": [2, 2],
    }


def test_calibration_from_session_requires_calibration_kind():
    session = MeasurementSession("Muestra A", SessionKind.SAMPLE, expected_runs=2)

    with pytest.raises(ValueError, match="de calibración"):
        calibration_from_session(session, [])


def test_calibration_from_session_averages_calibration_runs():
    session = MeasurementSession("Blanco", SessionKind.CALIBRATION, expected_runs=2)
    session.set_sweep_protocol(SweepProtocol(0.0, 1.0, 2, 0.1))
    first = make_run(1, session.uid)
    second = make_run(3, session.uid)
    session.add_run_uid(first.uid)
    session.add_run_uid(second.uid)

    calibration = calibration_from_session(session, [first, second])

    assert calibration.measurements == [
        MeasurementPoint(0.0, 2.0),
        MeasurementPoint(1.0, 3.0),
    ]


def test_average_session_rejects_a_run_with_a_different_protocol():
    session = MeasurementSession("Muestra A", SessionKind.SAMPLE, expected_runs=2)
    session.set_sweep_protocol(SweepProtocol(0.0, 1.0, 2, 0.1))
    first = make_run(1, session.uid)
    second = make_run(2, session.uid)
    second.expected_points = 3
    session.add_run_uid(first.uid)
    session.add_run_uid(second.uid)

    with pytest.raises(ValueError, match="puntos del protocolo"):
        average_session(session, [first, second])
