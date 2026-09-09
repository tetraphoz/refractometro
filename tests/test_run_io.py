from __future__ import annotations

import json

from app.models import RunRecord
from app.run_io import export_run_csv, import_run_csv
from experiments.voltage_sweep import MeasurementPoint


def test_export_run_updates_filename_and_round_trips(tmp_path):
    run = RunRecord(
        id=1,
        kind="barrido",
        label="Barrido #1",
        curve_tag="curva_barrido_1",
        measurements=[MeasurementPoint(0.0, 0.25)],
        laser_on_time_s=4.5,
        source_uids=["source-a"],
        analysis_kind="average",
        analysis_parameters={"source_count": 1},
    )
    filename = tmp_path / "export.csv"

    export_run_csv(run, str(filename))

    assert run.filename == str(filename)
    measurements, metadata = import_run_csv(str(filename))
    assert measurements == run.measurements
    assert metadata["label"] == run.label
    assert metadata["laser_on_time_s"] == "4.5"
    assert metadata["analysis_kind"] == "average"
    assert json.loads(metadata["source_uids"]) == ["source-a"]
    assert json.loads(metadata["analysis_parameters"]) == {"source_count": 1}
