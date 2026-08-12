from experiments.voltage_sweep import MeasurementPoint, VoltageSweep


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
