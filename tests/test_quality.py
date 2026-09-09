from __future__ import annotations

import pytest

from app.models import RunRecord, RunStatus
from app.peak_analysis import PeakDetectionSettings
from app.quality import analyze_session_peak_quality, store_session_peak_quality
from experiments.voltage_sweep import MeasurementPoint


def make_peak_run(run_id: int, peak_position: float = 2.0) -> RunRecord:
    return RunRecord(
        id=run_id,
        kind="barrido",
        label=f"Barrido {run_id}",
        curve_tag=f"curve-{run_id}",
        status=RunStatus.COMPLETED,
        measurements=[
            MeasurementPoint(0.0, 0.0),
            MeasurementPoint(1.0, 1.0),
            MeasurementPoint(peak_position, 4.0),
            MeasurementPoint(3.0, 1.0),
            MeasurementPoint(4.0, 0.0),
        ],
    )


def test_session_peak_quality_calculates_repeatability_and_confidence():
    result = analyze_session_peak_quality(
        [make_peak_run(1), make_peak_run(2, 2.1)],
        PeakDetectionSettings(smoothing_window=1, baseline_mode="none"),
    )

    assert result.state == "accepted"
    assert result.outlier_uids == ()
    assert result.position_standard_deviation_mm == pytest.approx(0.05)
    assert result.position_confidence_interval_95_mm is not None
    assert result.signal_to_noise_ratio is not None
    assert result.settings["outlier_method"] == "modified_z_score_median_mad"


def test_session_peak_quality_marks_a_single_extreme_run_for_review():
    outlier = make_peak_run(5, 2.0)
    outlier.measurements[2] = MeasurementPoint(2.0, 40.0)
    result = analyze_session_peak_quality(
        [make_peak_run(1), make_peak_run(2), make_peak_run(3), outlier],
        PeakDetectionSettings(smoothing_window=1, baseline_mode="none"),
    )

    assert result.state == "review"
    assert outlier.uid in result.outlier_uids
    assert result.repeatable_count == 3


def test_session_peak_quality_can_be_stored_on_a_derived_run():
    result_run = make_peak_run(1)
    metrics = analyze_session_peak_quality(
        [result_run, make_peak_run(2)],
        PeakDetectionSettings(smoothing_window=1, baseline_mode="none"),
    )

    store_session_peak_quality(result_run, metrics)

    assert result_run.analysis_parameters["peak_quality"]["state"] == "accepted"
