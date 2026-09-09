from __future__ import annotations

import sqlite3

import pytest

from app.models import (
    LaboratoryMetadata,
    MeasurementSession,
    RunRecord,
    SessionKind,
    SessionStatus,
)
from app.run_repository import RunRepository
from experiments.voltage_sweep import MeasurementPoint


def make_run(run_id: int = 1) -> RunRecord:
    return RunRecord(
        id=run_id,
        kind="barrido",
        label=f"Barrido #{run_id}",
        curve_tag=f"curva_barrido_{run_id}",
        measurements=[
            MeasurementPoint(position_mm=0.0, voltage_v=0.2),
            MeasurementPoint(position_mm=1.0, voltage_v=0.4),
        ],
        filename="runs/barrido_1.csv",
        expected_points=2,
        stabilization_time_s="0.1",
        laser_on_time_s=12.5,
        source_uids=["source-a", "source-b"],
        analysis_kind="average",
        analysis_parameters={"source_count": 2},
        created_at=123.0,
    )


def test_repository_round_trips_run_and_measurements(tmp_path):
    repository = RunRepository(tmp_path / "runs.sqlite3")
    run = make_run()

    repository.save(run)

    loaded = repository.get(run.id)

    assert loaded == run
    assert len(run.uid) == 64
    repository.close()


def test_run_records_receive_distinct_uids():
    first = make_run(1)
    second = make_run(2)

    assert first.uid != second.uid


def test_repository_completes_pre_provenance_schema(tmp_path):
    database_path = tmp_path / "old-runs.sqlite3"
    connection = sqlite3.connect(database_path)
    connection.executescript("""
        CREATE TABLE runs (
            id INTEGER PRIMARY KEY,
            uid TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'pending',
            kind TEXT NOT NULL,
            label TEXT NOT NULL,
            curve_tag TEXT NOT NULL,
            filename TEXT,
            expected_points INTEGER,
            stabilization_time_s TEXT,
            laser_on_time_s REAL,
            created_at REAL NOT NULL
        );
        CREATE TABLE measurements (
            run_id INTEGER NOT NULL,
            sequence INTEGER NOT NULL,
            position_mm REAL NOT NULL,
            voltage_v REAL NOT NULL,
            PRIMARY KEY (run_id, sequence)
        );
        """)
    connection.execute(
        """
        INSERT INTO runs (
            id, uid, status, kind, label, curve_tag, filename,
            expected_points, stabilization_time_s, laser_on_time_s, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            1,
            "legacy-uid",
            "completed",
            "barrido",
            "Legacy run",
            "legacy-curve",
            None,
            1,
            "0.1",
            1.0,
            123.0,
        ),
    )
    connection.commit()
    connection.close()

    repository = RunRepository(database_path)
    loaded = repository.get(1)

    assert loaded is not None
    assert loaded.source_uids == []
    assert loaded.analysis_kind is None
    assert loaded.analysis_parameters == {}
    repository.save(make_run())
    repository.close()


def test_repository_persists_sessions_and_their_raw_runs(tmp_path):
    repository = RunRepository(tmp_path / "runs.sqlite3")
    session = MeasurementSession(
        label="Muestra A",
        kind=SessionKind.SAMPLE,
        expected_runs=2,
        protocol_parameters={"number_of_points": 20},
        laboratory_metadata=LaboratoryMetadata(
            project="Proyecto A",
            sample="Muestra A",
            temperature_c=22.5,
        ).as_parameters(),
    )
    run = make_run()

    repository.save_session(session)
    repository.save(run)
    repository.attach_run_to_session(run, session)

    loaded = repository.get_session(session.uid)
    loaded_run = repository.get(run.id)

    assert loaded is not None
    assert loaded.status is SessionStatus.PREPARED
    assert loaded.run_uids == [run.uid]
    assert loaded.protocol_parameters == {"number_of_points": 20}
    assert loaded.laboratory_context().project == "Proyecto A"
    assert loaded.laboratory_context().temperature_c == 22.5
    assert loaded_run is not None
    assert loaded_run.session_uid == session.uid
    assert repository.list_runs_for_session(session.uid) == [loaded_run]
    repository.close()


def test_repository_rejects_reassigning_run_to_another_session(tmp_path):
    repository = RunRepository(tmp_path / "runs.sqlite3")
    first = MeasurementSession("Muestra A", SessionKind.SAMPLE, expected_runs=1)
    second = MeasurementSession("Muestra B", SessionKind.SAMPLE, expected_runs=1)
    run = make_run()

    repository.save_session(first)
    repository.save_session(second)
    repository.save(run)
    repository.attach_run_to_session(run, first)

    with pytest.raises(ValueError, match="otra sesión"):
        repository.attach_run_to_session(run, second)
    repository.close()


def test_repository_updates_measurements_atomically(tmp_path):
    repository = RunRepository(tmp_path / "runs.sqlite3")
    run = make_run()
    repository.save(run)

    run.measurements = [MeasurementPoint(position_mm=2.0, voltage_v=0.9)]
    repository.save(run)

    loaded = repository.get(run.id)
    assert loaded is not None
    assert loaded.measurements == run.measurements
    assert repository.list_runs() == [run]
    repository.close()


def test_repository_deletes_run_and_measurements(tmp_path):
    repository = RunRepository(tmp_path / "runs.sqlite3")
    repository.save(make_run())

    repository.delete(1)

    assert repository.get(1) is None
    assert repository.list_runs() == []
    repository.close()
