from experiments.voltage_sweep import MeasurementPoint
from storage.csv import import_measurements_csv, save_measurements_csv


def test_save_and_import_with_metadata(tmp_path):
    meas = [
        MeasurementPoint(position_mm=0.0, voltage_v=0.1),
        MeasurementPoint(position_mm=1.0, voltage_v=0.2),
    ]
    metadata = {
        "label": "fixture-run",
        "kind": "barrido",
        "number_of_points": "2",
        "start_position_mm": "0.0",
        "end_position_mm": "1.0",
        "stabilization_time_s": "0.1",
    }

    path = tmp_path / "with_meta.csv"
    save_measurements_csv(str(path), meas, metadata=metadata)

    imported_measurements, imported_meta = import_measurements_csv(str(path))

    assert len(imported_measurements) == 2
    assert imported_meta.get("label") == "fixture-run"
    assert imported_meta.get("number_of_points") == "2"
    # numeric values preserved
    assert imported_measurements[0].position_mm == 0.0
    assert imported_measurements[1].voltage_v == 0.2


def test_save_and_import_without_metadata(tmp_path):
    meas = [
        MeasurementPoint(position_mm=0.0, voltage_v=0.05),
        MeasurementPoint(position_mm=2.0, voltage_v=0.3),
    ]

    path = tmp_path / "no_meta.csv"
    save_measurements_csv(str(path), meas, metadata=None)

    imported_measurements, imported_meta = import_measurements_csv(str(path))

    assert imported_meta["kind"] == "imported"
    assert imported_meta["number_of_points"] == str(len(meas))
    assert imported_measurements[0].position_mm == 0.0


def test_import_empty_file_uses_defaults(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("")  # create an empty file

    imported_measurements, imported_meta = import_measurements_csv(str(path))

    assert imported_measurements == []
    assert imported_meta.get("number_of_points") == "0"
    assert imported_meta.get("kind") == "imported"
    # label should default to the filename (without extension)
    assert imported_meta.get("label") == "empty"
