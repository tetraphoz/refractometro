from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import RLock

from app.models import RunRecord, RunStatus
from experiments.voltage_sweep import MeasurementPoint

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
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
    source_uids TEXT NOT NULL DEFAULT '[]',
    analysis_kind TEXT,
    analysis_parameters TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS measurements (
    run_id INTEGER NOT NULL,
    sequence INTEGER NOT NULL,
    position_mm REAL NOT NULL,
    voltage_v REAL NOT NULL,
    PRIMARY KEY (run_id, sequence),
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS measurements_run_id_idx
    ON measurements (run_id);
"""


class RunRepository:
    """SQLite persistence for runs and their measurements.

    UI-only fields such as DearPyGui tags and calculated peaks are deliberately
    not stored. Peaks can be recalculated from the persisted measurements.
    """

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        self._lock = RLock()

        if self.database_path != ":memory:":
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)

        self._connection = sqlite3.connect(
            self.database_path,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.executescript(_SCHEMA)
        self._ensure_run_columns()
        self._connection.commit()

    def _ensure_run_columns(self) -> None:
        """Complete databases created before the current run metadata fields."""
        columns = {
            row[1] for row in self._connection.execute("PRAGMA table_info(runs)")
        }
        missing_columns = {
            "source_uids": "TEXT NOT NULL DEFAULT '[]'",
            "analysis_kind": "TEXT",
            "analysis_parameters": "TEXT NOT NULL DEFAULT '{}'",
        }
        for column, definition in missing_columns.items():
            if column not in columns:
                self._connection.execute(
                    f"ALTER TABLE runs ADD COLUMN {column} {definition}"
                )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def save(self, run: RunRecord) -> None:
        """Insert or update a run and replace its measurements atomically."""
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO runs (
                    id, uid, status, kind, label, curve_tag, filename,
                    expected_points, stabilization_time_s, laser_on_time_s,
                    source_uids, analysis_kind, analysis_parameters, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    uid = excluded.uid,
                    status = excluded.status,
                    kind = excluded.kind,
                    label = excluded.label,
                    curve_tag = excluded.curve_tag,
                    filename = excluded.filename,
                    expected_points = excluded.expected_points,
                    stabilization_time_s = excluded.stabilization_time_s,
                    laser_on_time_s = excluded.laser_on_time_s,
                    source_uids = excluded.source_uids,
                    analysis_kind = excluded.analysis_kind,
                    analysis_parameters = excluded.analysis_parameters,
                    created_at = excluded.created_at
                """,
                (
                    run.id,
                    run.uid,
                    run.status.value,
                    run.kind,
                    run.label,
                    run.curve_tag,
                    run.filename,
                    run.expected_points,
                    run.stabilization_time_s,
                    run.laser_on_time_s,
                    json.dumps(run.source_uids),
                    run.analysis_kind,
                    json.dumps(run.analysis_parameters),
                    run.created_at,
                ),
            )
            self._connection.execute(
                "DELETE FROM measurements WHERE run_id = ?",
                (run.id,),
            )
            self._connection.executemany(
                """
                INSERT INTO measurements (run_id, sequence, position_mm, voltage_v)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (run.id, sequence, point.position_mm, point.voltage_v)
                    for sequence, point in enumerate(run.measurements)
                ],
            )

    def get(self, run_id: int) -> RunRecord | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                return None
            return self._build_run(row)

    def list_runs(self) -> list[RunRecord]:
        with self._lock:
            rows = self._connection.execute("SELECT * FROM runs ORDER BY id").fetchall()
            return [self._build_run(row) for row in rows]

    def delete(self, run_id: int) -> None:
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM runs WHERE id = ?", (run_id,))

    def clear(self) -> None:
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM runs")

    def _build_run(self, row: sqlite3.Row) -> RunRecord:
        measurements = self._connection.execute(
            """
            SELECT position_mm, voltage_v
            FROM measurements
            WHERE run_id = ?
            ORDER BY sequence
            """,
            (row["id"],),
        ).fetchall()

        return RunRecord(
            id=row["id"],
            uid=row["uid"],
            status=RunStatus(row["status"] or RunStatus.COMPLETED),
            kind=row["kind"],
            label=row["label"],
            curve_tag=row["curve_tag"],
            measurements=[
                MeasurementPoint(
                    position_mm=measurement["position_mm"],
                    voltage_v=measurement["voltage_v"],
                )
                for measurement in measurements
            ],
            filename=row["filename"],
            expected_points=row["expected_points"],
            stabilization_time_s=row["stabilization_time_s"],
            laser_on_time_s=row["laser_on_time_s"],
            source_uids=json.loads(row["source_uids"]),
            analysis_kind=row["analysis_kind"],
            analysis_parameters=json.loads(row["analysis_parameters"]),
            created_at=row["created_at"],
        )
