from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import median, pstdev
from typing import Literal

from app.models import RunRecord, RunStatus
from app.peak_analysis import PeakDetectionSettings, analyze_peaks

QualityState = Literal[
    "insufficient_data",
    "no_repeatable_peak",
    "accepted",
    "review",
]


@dataclass(frozen=True)
class RunPeakMeasurement:
    """Strongest detected peak for one raw run in a quality review."""

    run_uid: str
    position_mm: float
    voltage_v: float
    prominence_v: float
    signal_to_noise: float


@dataclass(frozen=True)
class PeakRepeatabilityMetrics:
    """Repeatability and confidence metrics for one session's raw peaks."""

    state: QualityState
    measurements: tuple[RunPeakMeasurement, ...]
    outlier_uids: tuple[str, ...]
    median_position_mm: float | None
    median_voltage_v: float | None
    position_standard_deviation_mm: float | None
    voltage_standard_deviation_v: float | None
    position_confidence_interval_95_mm: tuple[float, float] | None
    voltage_confidence_interval_95_v: tuple[float, float] | None
    signal_to_noise_ratio: float | None
    settings: dict[str, object]

    @property
    def repeatable_count(self) -> int:
        return len(self.measurements) - len(self.outlier_uids)

    def as_parameters(self) -> dict[str, object]:
        return {
            "quality_version": "v3",
            "state": self.state,
            "run_uids": [measurement.run_uid for measurement in self.measurements],
            "outlier_uids": list(self.outlier_uids),
            "median_position_mm": self.median_position_mm,
            "median_voltage_v": self.median_voltage_v,
            "position_standard_deviation_mm": self.position_standard_deviation_mm,
            "voltage_standard_deviation_v": self.voltage_standard_deviation_v,
            "position_confidence_interval_95_mm": (
                list(self.position_confidence_interval_95_mm)
                if self.position_confidence_interval_95_mm is not None
                else None
            ),
            "voltage_confidence_interval_95_v": (
                list(self.voltage_confidence_interval_95_v)
                if self.voltage_confidence_interval_95_v is not None
                else None
            ),
            "signal_to_noise_ratio": self.signal_to_noise_ratio,
            "settings": self.settings,
        }


def _confidence_interval(values: list[float]) -> tuple[float, float] | None:
    if not values:
        return None
    centre = sum(values) / len(values)
    if len(values) == 1:
        return (centre, centre)
    margin = 1.96 * pstdev(values) / math.sqrt(len(values))
    return (centre - margin, centre + margin)


def _modified_z_outliers(
    values: list[float],
    uids: list[str],
    threshold: float,
) -> set[str]:
    if len(values) < 3:
        return set()
    centre = median(values)
    deviations = [abs(value - centre) for value in values]
    mad = median(deviations)
    if math.isclose(mad, 0.0):
        return {
            uid
            for uid, value in zip(uids, values)
            if not math.isclose(value, centre, abs_tol=1e-12)
        }
    return {
        uid
        for uid, value in zip(uids, values)
        if abs(0.6745 * (value - centre) / mad) > threshold
    }


def analyze_session_peak_quality(
    runs: list[RunRecord],
    settings: PeakDetectionSettings | None = None,
    *,
    outlier_z_threshold: float = 3.5,
) -> PeakRepeatabilityMetrics:
    """Evaluate peak repeatability using the strongest candidate per run.

    A run is an outlier when its position or voltage has a modified z-score
    above ``outlier_z_threshold``. The modified z-score uses the median and
    median absolute deviation, so the criterion remains useful for small
    batches and is recorded in ``settings`` for reproducibility.
    """
    if outlier_z_threshold <= 0:
        raise ValueError("El umbral de atípicos debe ser positivo")
    settings = settings or PeakDetectionSettings()
    peak_measurements: list[RunPeakMeasurement] = []
    for run in runs:
        if run.status is not RunStatus.COMPLETED or not run.measurements:
            continue
        analysis = analyze_peaks(run.measurements, settings)
        peak = analysis.candidates[0] if analysis.candidates else None
        if peak is None:
            continue
        noise = peak.voltage_uncertainty_v
        signal_to_noise = peak.prominence_v / noise if noise > 0 else float("inf")
        peak_measurements.append(
            RunPeakMeasurement(
                run_uid=run.uid,
                position_mm=peak.position_mm,
                voltage_v=peak.voltage_v,
                prominence_v=peak.prominence_v,
                signal_to_noise=signal_to_noise,
            )
        )

    positions = [measurement.position_mm for measurement in peak_measurements]
    voltages = [measurement.voltage_v for measurement in peak_measurements]
    uids = [measurement.run_uid for measurement in peak_measurements]
    outlier_uids = _modified_z_outliers(
        positions, uids, outlier_z_threshold
    ) | _modified_z_outliers(voltages, uids, outlier_z_threshold)
    repeatable_positions = [
        value for value, uid in zip(positions, uids) if uid not in outlier_uids
    ]
    repeatable_voltages = [
        value for value, uid in zip(voltages, uids) if uid not in outlier_uids
    ]
    if len(peak_measurements) < 2:
        state: QualityState = "insufficient_data"
    elif len(repeatable_positions) < 2:
        state = "no_repeatable_peak"
    elif outlier_uids:
        state = "review"
    else:
        state = "accepted"

    snr_values = [
        measurement.signal_to_noise
        for measurement, uid in zip(peak_measurements, uids)
        if uid not in outlier_uids
    ]
    return PeakRepeatabilityMetrics(
        state=state,
        measurements=tuple(peak_measurements),
        outlier_uids=tuple(uid for uid in uids if uid in outlier_uids),
        median_position_mm=(
            median(repeatable_positions) if repeatable_positions else None
        ),
        median_voltage_v=median(repeatable_voltages) if repeatable_voltages else None,
        position_standard_deviation_mm=(
            pstdev(repeatable_positions) if len(repeatable_positions) > 1 else None
        ),
        voltage_standard_deviation_v=(
            pstdev(repeatable_voltages) if len(repeatable_voltages) > 1 else None
        ),
        position_confidence_interval_95_mm=_confidence_interval(repeatable_positions),
        voltage_confidence_interval_95_v=_confidence_interval(repeatable_voltages),
        signal_to_noise_ratio=median(snr_values) if snr_values else None,
        settings={
            "peak_detection": settings.as_parameters(),
            "outlier_method": "modified_z_score_median_mad",
            "outlier_z_threshold": outlier_z_threshold,
        },
    )


def store_session_peak_quality(
    result_run: RunRecord,
    metrics: PeakRepeatabilityMetrics,
) -> None:
    """Persist quality metrics as reproducible analysis metadata."""
    result_run.analysis_parameters = {
        **result_run.analysis_parameters,
        "peak_quality": metrics.as_parameters(),
    }
