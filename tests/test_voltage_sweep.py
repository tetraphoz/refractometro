import threading

import pytest

from app.errors import OperationCancelled
from experiments.voltage_sweep import MeasurementPoint, VoltageSweep


def test_sweep_honors_cancellation_before_moving():
    cancel_event = threading.Event()
    cancel_event.set()

    class Motor:
        def move_absolute(self, _position_mm):
            pytest.fail("the motor should not move after cancellation")

    class Sensor:
        def read_voltage(self):
            return 0.0

    with pytest.raises(OperationCancelled):
        VoltageSweep(Motor(), Sensor()).run(
            0.0,
            1.0,
            2,
            0.0,
            cancel_event=cancel_event,
        )


def test_batch_preserves_each_sweep_and_reports_progress():
    class Motor:
        def move_absolute(self, _position_mm):
            pass

    class Sensor:
        def __init__(self):
            self.read_count = 0

        def read_voltage(self):
            self.read_count += 1
            return float(self.read_count)

    progress = []
    completed = []
    results = VoltageSweep(Motor(), Sensor()).run_batch(
        0.0,
        1.0,
        2,
        0.0,
        2,
        progress_callback=progress.append,
        run_finished_callback=lambda run_number, measurements: completed.append(
            (run_number, measurements)
        ),
    )

    assert len(results) == 2
    assert results[0] == [MeasurementPoint(0.0, 1.0), MeasurementPoint(1.0, 2.0)]
    assert results[1] == [MeasurementPoint(0.0, 3.0), MeasurementPoint(1.0, 4.0)]
    assert [item.run_number for item in progress] == [1, 1, 2, 2]
    assert [item.total_runs for item in progress] == [2, 2, 2, 2]
    assert [run_number for run_number, _ in completed] == [1, 2]


def test_batch_retries_a_failed_run_before_reporting_success():
    class Motor:
        def move_absolute(self, _position_mm):
            pass

    class Sensor:
        def __init__(self):
            self.read_count = 0

        def read_voltage(self):
            self.read_count += 1
            if self.read_count == 1:
                raise RuntimeError("transient sensor failure")
            return 1.0

    failures = []
    results = VoltageSweep(Motor(), Sensor()).run_batch(
        0.0,
        1.0,
        2,
        0.0,
        1,
        max_retries=1,
        run_failed_callback=failures.append,
    )

    assert len(results) == 1
    assert failures == []


def test_batch_reports_exhausted_run_and_continues():
    class Motor:
        def move_absolute(self, _position_mm):
            pass

    class Sensor:
        def __init__(self):
            self.read_count = 0

        def read_voltage(self):
            self.read_count += 1
            if self.read_count <= 2:
                raise RuntimeError("persistent sensor failure")
            return 1.0

    failures = []
    completed = []
    results = VoltageSweep(Motor(), Sensor()).run_batch(
        0.0,
        1.0,
        2,
        0.0,
        2,
        max_retries=1,
        run_failed_callback=failures.append,
        run_finished_callback=lambda run_number, _measurements: completed.append(
            run_number
        ),
    )

    assert len(results) == 1
    assert completed == [2]
    assert len(failures) == 1
    assert failures[0].run_number == 1
    assert failures[0].attempts == 2
    assert str(failures[0].error) == "persistent sensor failure"


def test_batch_rejects_negative_retries():
    with pytest.raises(ValueError, match="reintentos"):
        VoltageSweep(object(), object()).run_batch(0.0, 1.0, 2, 0.0, 1, max_retries=-1)


def test_batch_rejects_zero_runs():
    with pytest.raises(ValueError, match="al menos un barrido"):
        VoltageSweep(object(), object()).run_batch(0.0, 1.0, 2, 0.0, 0)


def test_sweep_rejects_negative_stabilization_time():
    with pytest.raises(ValueError, match="no puede ser negativo"):
        VoltageSweep(object(), object()).run(0.0, 1.0, 2, -0.1)


def test_find_peaks_empty():
    assert VoltageSweep.find_peaks([]) == []


def test_find_peaks_single_point():
    mp = MeasurementPoint(position_mm=5.0, voltage_v=0.1234)
    peaks = VoltageSweep.find_peaks([mp])
    assert len(peaks) == 1
    assert peaks[0].position_mm == mp.position_mm
    assert peaks[0].voltage_v == mp.voltage_v


def test_find_peaks_endpoints():
    left = MeasurementPoint(position_mm=0.0, voltage_v=2.0)
    right = MeasurementPoint(position_mm=1.0, voltage_v=1.0)
    peaks = VoltageSweep.find_peaks([left, right])
    # left endpoint is strictly greater than its neighbor -> should be a peak
    assert len(peaks) == 1
    assert peaks[0].position_mm == left.position_mm


def test_find_peaks_plateau_midpoint():
    # plateau on the left (0 and 1 equal), smaller on right -> midpoint should be picked
    m0 = MeasurementPoint(position_mm=0.0, voltage_v=1.0)
    m1 = MeasurementPoint(position_mm=1.0, voltage_v=1.0)
    m2 = MeasurementPoint(position_mm=2.0, voltage_v=0.5)
    peaks = VoltageSweep.find_peaks([m0, m1, m2])
    assert len(peaks) == 1
    assert peaks[0].position_mm == m1.position_mm


def test_find_peaks_multiple_peaks_ordering():
    data = [
        MeasurementPoint(0.0, 0.5),
        MeasurementPoint(1.0, 2.0),  # peak #1
        MeasurementPoint(2.0, 0.3),
        MeasurementPoint(3.0, 1.5),  # peak #2
        MeasurementPoint(4.0, 0.2),
    ]
    peaks = VoltageSweep.find_peaks(data)
    assert len(peaks) == 2
    # peaks should be sorted by voltage_v descending
    assert peaks[0].voltage_v >= peaks[1].voltage_v
    assert {p.position_mm for p in peaks} == {1.0, 3.0}
