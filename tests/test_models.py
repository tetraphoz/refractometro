from __future__ import annotations

import pytest

from app.models import MeasurementSession, SessionKind, SessionStatus


def test_measurement_session_tracks_raw_runs_in_acquisition_order():
    session = MeasurementSession(
        label="Muestra A",
        kind=SessionKind.SAMPLE,
        expected_runs=3,
        protocol_parameters={"number_of_points": 20},
    )

    session.add_run_uid("run-2")
    session.add_run_uid("run-1")

    assert session.status is SessionStatus.PREPARED
    assert session.run_uids == ["run-2", "run-1"]
    assert session.protocol_parameters == {"number_of_points": 20}


def test_measurement_session_rejects_invalid_or_duplicate_runs():
    with pytest.raises(ValueError, match="al menos una corrida"):
        MeasurementSession("Vacío", SessionKind.CALIBRATION, expected_runs=0)

    session = MeasurementSession("Blanco", SessionKind.CALIBRATION, expected_runs=1)

    with pytest.raises(ValueError, match="necesita un UID"):
        session.add_run_uid("")

    session.add_run_uid("run-1")
    with pytest.raises(ValueError, match="ya pertenece"):
        session.add_run_uid("run-1")
