from __future__ import annotations

from app.models import MeasurementSession, SessionKind
from app.run_repository import RunRepository


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
