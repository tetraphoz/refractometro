from __future__ import annotations

import pytest

from experiments.calibration import CalibrationCurve
from experiments.voltage_sweep import MeasurementPoint, VoltageSweep
from storage.csv import import_measurements_csv, save_measurements_csv


def test_find_peaks_simple():
    # Create measurements with two peaks: at x=1 (v=1.0) and x=3 (v=1.5)
    measurements = [
        MeasurementPoint(position_mm=0.0, voltage_v=0.0),
        MeasurementPoint(position_mm=1.0, voltage_v=1.0),
        MeasurementPoint(position_mm=2.0, voltage_v=0.9),
        MeasurementPoint(position_mm=3.0, voltage_v=1.5),
        MeasurementPoint(position_mm=4.0, voltage_v=0.1),
    ]

    peaks = VoltageSweep.find_peaks(measurements)

    # Peaks should be sorted by voltage descending: first the 1.5V peak, then 1.0V
    assert len(peaks) == 2
    assert peaks[0].position_mm == pytest.approx(3.0)
    assert peaks[0].voltage_v == pytest.approx(1.5)
    assert peaks[1].position_mm == pytest.approx(1.0)
    assert peaks[1].voltage_v == pytest.approx(1.0)


def test_calibration_interpolate_and_subtract():
    # Calibration curve with two points: (0 -> 0.2), (10 -> 0.4)
    calib_points = [
        MeasurementPoint(position_mm=0.0, voltage_v=0.2),
        MeasurementPoint(position_mm=10.0, voltage_v=0.4),
    ]
    calib = CalibrationCurve(calib_points)

    # Interpolate at the midpoint
    mid = calib.interpolate(
        [p.position_mm for p in calib_points], [p.voltage_v for p in calib_points], 5.0
    )
    assert mid == pytest.approx(0.3)

    # Subtract baseline from a measurement at 5.0 mm with voltage 1.0 V
    measured = [MeasurementPoint(position_mm=5.0, voltage_v=1.0)]
    corrected = calib.subtract(measured)
    assert len(corrected) == 1
    assert corrected[0].position_mm == pytest.approx(5.0)
    assert corrected[0].voltage_v == pytest.approx(1.0 - 0.3)


def test_csv_roundtrip(tmp_path):
    measurements = [
        MeasurementPoint(position_mm=0.0, voltage_v=0.1),
        MeasurementPoint(position_mm=1.0, voltage_v=0.2),
        MeasurementPoint(position_mm=2.0, voltage_v=0.3),
    ]

    # Save CSV without metadata
    p = tmp_path / "sample_run.csv"
    save_measurements_csv(str(p), measurements, metadata=None)

    # Import back
    imported_measurements, metadata = import_measurements_csv(str(p))

    assert len(imported_measurements) == len(measurements)
    for a, b in zip(imported_measurements, measurements):
        assert a.position_mm == pytest.approx(b.position_mm)
        assert a.voltage_v == pytest.approx(b.voltage_v)

    # Metadata should provide defaults
    assert metadata.get("kind") == "imported"
    assert metadata.get("number_of_points") == str(len(measurements))
    # Label defaults to filename base
    assert metadata.get("label") == p.stem
