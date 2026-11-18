from __future__ import annotations

import pytest

from app.models import MeasurementSession, RunStatus, SessionKind, SessionStatus
from app.run_history import RunHistory
from app.run_repository import RunRepository
from experiments.voltage_sweep import MeasurementPoint


def test_run_history_creates_runs_with_stable_tags():
    history = RunHistory()
    run_id = history.reserve_id()

    run = history.create_run(
        run_id=run_id,
        kind="barrido",
        label="Barrido #1",
        curve_tag="curva_barrido_1",
        measurements=[MeasurementPoint(0.0, 0.1)],
    )

    assert history.counter == 1
    assert history.next_id == 2
    assert history.get(run_id) is run
    assert history.get_by_uid(run.uid) is run
    assert history.runs == [run]
    assert run.row_tag == "historial_fila_1"
    assert run.text_tag == "historial_texto_1"
    assert run.measurements == [MeasurementPoint(0.0, 0.1)]


def test_run_history_create_run_advances_counter_without_reserve():
    history = RunHistory()

    history.create_run(
        run_id=3,
        kind="barrido",
        label="Barrido #3",
        curve_tag="curva_barrido_3",
    )

    assert history.counter == 3
    assert history.next_id == 4


def test_run_history_rejects_duplicate_ids():
    history = RunHistory()
    run = history.create_run(
        run_id=1,
        kind="barrido",
        label="Barrido #1",
        curve_tag="curva_barrido_1",
    )

    with pytest.raises(ValueError, match="Ya existe"):
        history.add(run)


def test_run_history_active_run_is_cleared_when_removed():
    history = RunHistory()
    run = history.create_run(
        run_id=1,
        kind="barrido",
        label="Barrido #1",
        curve_tag="curva_barrido_1",
    )

    history.set_active(run)
    history.remove(run)

    assert history.active_run is None
    assert history.get(1) is None
    assert history.runs == []


def test_run_history_marks_unfinished_runs_as_interrupted(tmp_path):
    repository = RunRepository(tmp_path / "runs.sqlite3")
    history = RunHistory(repository)
    run = history.create_run(
        run_id=5,
        kind="barrido",
        label="Barrido #5",
        curve_tag="curva_barrido_5",
    )
    run.status = RunStatus.RUNNING
    history.save(run)

    restored = RunHistory(repository)

    assert restored.get(5) is not None
    assert restored.get(5).status is RunStatus.INTERRUPTED
    repository.close()


@pytest.mark.parametrize("status", [SessionStatus.ACQUIRING, SessionStatus.PAUSED])
def test_reopening_abandoned_batch_preserves_partial_data(tmp_path, status):
    database = tmp_path / "runs.sqlite3"
    repository = RunRepository(database)
    history = RunHistory(repository)
    session = MeasurementSession("Muestra", SessionKind.SAMPLE, 2, status=status)
    repository.save_session(session)
    for run_id, run_status in enumerate([RunStatus.COMPLETED, RunStatus.RUNNING], 1):
        run = history.create_run(
            run_id=run_id, kind="barrido", label="Crudo", curve_tag=f"curve-{run_id}"
        )
        run.status = run_status
        run.measurements = [MeasurementPoint(0.0, 0.42)]
        history.save(run)
        repository.attach_run_to_session(run, session)
    repository.close()

    repository = RunRepository(database)
    restored = RunHistory(repository)
    assert repository.get_session(session.uid).status is SessionStatus.INTERRUPTED
    assert restored.get(1).status is RunStatus.COMPLETED
    assert restored.get(2).status is RunStatus.INTERRUPTED
    assert restored.get(2).measurements == [MeasurementPoint(0.0, 0.42)]
    repository.close()


def test_run_history_persists_and_restores_runs(tmp_path):
    repository = RunRepository(tmp_path / "runs.sqlite3")
    history = RunHistory(repository)
    run = history.create_run(
        run_id=4,
        kind="calibracion",
        label="Calibración #4",
        curve_tag="curva_calibracion_4",
        measurements=[MeasurementPoint(0.0, 0.25)],
    )
    run.filename = "runs/calibracion_4.csv"
    history.save(run)

    restored = RunHistory(repository)
    loaded = restored.get(4)

    assert loaded is not None
    assert loaded.measurements == run.measurements
    assert loaded.filename == run.filename
    assert loaded.row_tag == "historial_fila_4"
    assert loaded.text_tag == "historial_texto_4"
    assert restored.next_id == 5
    repository.close()
