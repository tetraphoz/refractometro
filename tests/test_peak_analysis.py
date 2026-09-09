from __future__ import annotations

import pytest

from app.models import RunRecord
from app.peak_analysis import PeakDetectionSettings, analyze_peaks, store_peak_analysis
from experiments.voltage_sweep import MeasurementPoint


def points(values: list[float]) -> list[MeasurementPoint]:
    return [MeasurementPoint(float(index), value) for index, value in enumerate(values)]


def test_analyze_peaks_returns_candidates_with_uncertainty_and_parameters():
    result = analyze_peaks(
        points([0.0, 0.2, 2.0, 0.2, 0.0]),
        PeakDetectionSettings(
            smoothing_window=1,
            baseline_mode="linear",
            minimum_prominence_v=1.0,
        ),
        selected_index=0,
    )

    peak = result.selected_peak
    assert peak is not None
    assert peak.position_mm == 2.0
    assert peak.prominence_v == pytest.approx(2.0)
    assert peak.position_uncertainty_mm == 0.5
    assert result.as_parameters()["selected_index"] == 0
    assert result.as_parameters()["candidate_count"] == 1


def test_analyze_peaks_filters_candidates_outside_expected_range():
    result = analyze_peaks(
        points([0.0, 2.0, 0.0, 0.0, 3.0, 0.0]),
        PeakDetectionSettings(
            smoothing_window=1,
            baseline_mode="none",
            expected_position_range_mm=(3.0, 5.0),
        ),
    )

    assert [peak.position_mm for peak in result.candidates] == [4.0]


def test_analyze_peaks_rejects_invalid_selected_candidate():
    with pytest.raises(ValueError, match="no existe"):
        analyze_peaks(points([0.0, 2.0, 0.0]), selected_index=0)


def test_store_peak_analysis_preserves_existing_result_provenance():
    run = RunRecord(
        id=1,
        kind="corregido",
        label="Muestra corregida",
        curve_tag="curve-1",
        measurements=points([0.0, 2.0, 0.0]),
        analysis_parameters={"calibration_uid": "calibration-1"},
    )
    analysis = analyze_peaks(
        run.measurements,
        PeakDetectionSettings(smoothing_window=1, baseline_mode="none"),
        selected_index=0,
    )

    store_peak_analysis(run, analysis)

    assert run.analysis_parameters["calibration_uid"] == "calibration-1"
    assert run.analysis_parameters["peak_detection"]["selected_index"] == 0


def test_peak_detection_settings_validate_inputs():
    with pytest.raises(ValueError, match="impar"):
        PeakDetectionSettings(smoothing_window=2)
    with pytest.raises(ValueError, match="umbral"):
        PeakDetectionSettings(minimum_prominence_v=-1)
