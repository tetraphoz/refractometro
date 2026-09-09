from __future__ import annotations

import pytest

from app.models import RunRecord, RunStatus
from app.run_processing import (
    average_runs,
    average_runs_with_statistics,
    averageable_runs,
    format_peak_summary,
    interpolate,
    subtract_reference,
)
from experiments.voltage_sweep import MeasurementPoint


def make_run(
    run_id: int,
    measurements: list[MeasurementPoint],
) -> RunRecord:
    return RunRecord(
        id=run_id,
        kind="test",
        label=f"Run {run_id}",
        curve_tag=f"curva_{run_id}",
        measurements=measurements,
    )


def test_interpolate_clamps_and_interpolates():
    positions = [0.0, 10.0]
    voltages = [0.2, 0.4]

    assert interpolate(positions, voltages, -1.0) == pytest.approx(0.2)
    assert interpolate(positions, voltages, 5.0) == pytest.approx(0.3)
    assert interpolate(positions, voltages, 11.0) == pytest.approx(0.4)


def test_subtract_reference_interpolates_reference_points():
    run = make_run(
        1,
        [
            MeasurementPoint(0.0, 1.0),
            MeasurementPoint(5.0, 1.0),
            MeasurementPoint(10.0, 1.0),
        ],
    )
    reference = make_run(
        2,
        [
            MeasurementPoint(0.0, 0.2),
            MeasurementPoint(10.0, 0.4),
        ],
    )

    corrected = subtract_reference(run, reference)

    assert [point.voltage_v for point in corrected] == pytest.approx([0.8, 0.7, 0.6])


def test_subtract_reference_requires_measurements():
    with pytest.raises(ValueError, match="Ambas corridas"):
        subtract_reference(make_run(1, []), make_run(2, []))


def test_averageable_runs_excludes_incomplete_and_derived_runs():
    completed = make_run(1, [MeasurementPoint(0.0, 0.1)])
    completed.status = RunStatus.COMPLETED

    pending = make_run(2, [MeasurementPoint(0.0, 0.2)])
    derived = make_run(3, [MeasurementPoint(0.0, 0.3)])
    derived.kind = "promedio"
    derived.status = RunStatus.COMPLETED

    assert averageable_runs([completed, pending, derived]) == [completed]


def test_average_runs_with_statistics_tracks_repeatability():
    first = make_run(
        1,
        [
            MeasurementPoint(0.0, 0.0),
            MeasurementPoint(10.0, 1.0),
        ],
    )
    second = make_run(
        2,
        [
            MeasurementPoint(5.0, 1.0),
            MeasurementPoint(15.0, 3.0),
        ],
    )

    result = average_runs_with_statistics([first, second])

    assert result.measurements == [
        MeasurementPoint(5.0, 0.75),
        MeasurementPoint(10.0, 1.5),
    ]
    assert [point.standard_deviation_v for point in result.points] == pytest.approx(
        [0.25, 0.5]
    )
    assert [point.sample_count for point in result.points] == [2, 2]
    assert result.source_uids == (first.uid, second.uid)


def test_average_runs_interpolates_to_common_grid():
    first = make_run(
        1,
        [
            MeasurementPoint(0.0, 0.0),
            MeasurementPoint(10.0, 1.0),
        ],
    )
    second = make_run(
        2,
        [
            MeasurementPoint(5.0, 1.0),
            MeasurementPoint(15.0, 3.0),
        ],
    )

    averaged = average_runs([first, second])

    assert averaged == [MeasurementPoint(5.0, 0.75), MeasurementPoint(10.0, 1.5)]


def test_average_runs_requires_a_common_range():
    first = make_run(1, [MeasurementPoint(0.0, 1.0)])
    second = make_run(2, [MeasurementPoint(2.0, 1.0)])

    with pytest.raises(ValueError, match="rango de posiciones común"):
        average_runs([first, second])


def test_format_peak_summary_limits_output():
    peaks = [
        MeasurementPoint(1.0, 0.1),
        MeasurementPoint(2.0, 0.2),
        MeasurementPoint(3.0, 0.3),
    ]

    assert format_peak_summary(peaks, limit=2) == (
        "1. 0.1000V @ 1.00mm\n2. 0.2000V @ 2.00mm"
    )
    assert format_peak_summary([]) == ""
