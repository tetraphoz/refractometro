from __future__ import annotations

import json

from app.models import RunRecord
from experiments.voltage_sweep import MeasurementPoint
from storage.csv import import_measurements_csv, save_measurements_csv


def export_run_csv(run: RunRecord, filename: str) -> None:
    measurements = run.measurements

    metadata = {
        "kind": run.kind,
        "label": run.label,
        "id": str(run.id),
        "stabilization_time_s": str(run.stabilization_time_s or ""),
        "laser_on_time_s": str(run.laser_on_time_s or ""),
        "analysis_kind": run.analysis_kind or "",
        "source_uids": json.dumps(run.source_uids),
        "analysis_parameters": json.dumps(run.analysis_parameters),
    }

    save_measurements_csv(filename, measurements, metadata=metadata)
    run.filename = filename


def import_run_csv(filename: str) -> tuple[list[MeasurementPoint], dict]:
    return import_measurements_csv(filename)
