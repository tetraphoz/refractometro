from __future__ import annotations

import pytest

from app.models import MeasurementSession, SessionKind
from app.run_repository import RunRepository


def test_session_can_exclude_and_reinclude_a_run_with_reason():
    session = MeasurementSession("Muestra", SessionKind.SAMPLE, expected_runs=2)
    session.add_run_uid("run-1")
    session.add_run_uid("run-2")

    session.exclude_run("run-1", "Lectura atípica")
    assert session.excluded_runs == {"run-1": "Lectura atípica"}
    session.include_run("run-1")
    assert session.excluded_runs == {}

    with pytest.raises(ValueError, match="razón"):
        session.exclude_run("run-2", "  ")


def test_repository_persists_exclusion_audit_trail(tmp_path):
    repository = RunRepository(tmp_path / "runs.sqlite3")
    session = MeasurementSession("Agua", SessionKind.SAMPLE, expected_runs=1)
    session.add_run_uid("run-1")
    session.exclude_run("run-1", "Pico atípico")
    repository.save_session(session)

    loaded = repository.get_session(session.uid)

    assert loaded is not None
    assert loaded.excluded_runs == {"run-1": "Pico atípico"}
    repository.close()


def test_repository_deletes_an_empty_session(tmp_path):
    repository = RunRepository(tmp_path / "runs.sqlite3")
    session = MeasurementSession("Agua", SessionKind.SAMPLE, expected_runs=20)
    repository.save_session(session)

    repository.delete_session(session.uid)

    assert repository.get_session(session.uid) is None
    repository.close()


def test_sessions_with_the_same_sample_name_are_persisted_separately(tmp_path):
    repository = RunRepository(tmp_path / "runs.sqlite3")
    first = MeasurementSession("Agua", SessionKind.SAMPLE, expected_runs=20)
    second = MeasurementSession("Agua", SessionKind.SAMPLE, expected_runs=20)

    repository.save_session(first)
    repository.save_session(second)

    sessions = repository.list_sessions()

    assert first.uid != second.uid
    assert [(session.uid, session.label) for session in sessions] == [
        (first.uid, "Agua"),
        (second.uid, "Agua"),
    ]
    repository.close()
