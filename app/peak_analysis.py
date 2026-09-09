from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise
from statistics import median
from typing import Literal

from app.models import RunRecord
from experiments.voltage_sweep import MeasurementPoint


@dataclass(frozen=True)
class PeakDetectionSettings:
    """Versioned, reproducible parameters used to identify an optical peak."""

    smoothing_window: int = 3
    baseline_mode: Literal["none", "linear"] = "linear"
    minimum_prominence_v: float = 0.0
    minimum_width_mm: float = 0.0
    minimum_distance_mm: float = 0.0
    expected_position_range_mm: tuple[float, float] | None = None

    def __post_init__(self) -> None:
        if self.smoothing_window < 1 or self.smoothing_window % 2 == 0:
            raise ValueError("La ventana de suavizado debe ser impar y positiva")
        if (
            min(
                self.minimum_prominence_v,
                self.minimum_width_mm,
                self.minimum_distance_mm,
            )
            < 0
        ):
            raise ValueError("Los umbrales de pico no pueden ser negativos")
        if self.expected_position_range_mm is not None:
            start, end = self.expected_position_range_mm
            if start > end:
                raise ValueError("El rango esperado del pico no es válido")

    def as_parameters(self) -> dict[str, object]:
        return {
            "analysis_version": "v3",
            "smoothing_window": self.smoothing_window,
            "baseline_mode": self.baseline_mode,
            "minimum_prominence_v": self.minimum_prominence_v,
            "minimum_width_mm": self.minimum_width_mm,
            "minimum_distance_mm": self.minimum_distance_mm,
            "expected_position_range_mm": (
                list(self.expected_position_range_mm)
                if self.expected_position_range_mm is not None
                else None
            ),
        }


@dataclass(frozen=True)
class PeakCandidate:
    """A candidate physical index-change peak and its uncertainty estimate."""

    position_mm: float
    voltage_v: float
    prominence_v: float
    width_mm: float
    position_uncertainty_mm: float
    voltage_uncertainty_v: float


@dataclass(frozen=True)
class PeakAnalysisResult:
    """Peak candidates and the explicitly selected candidate, if any."""

    candidates: tuple[PeakCandidate, ...]
    selected_index: int | None
    processed_measurements: tuple[MeasurementPoint, ...]
    settings: PeakDetectionSettings

    @property
    def selected_peak(self) -> PeakCandidate | None:
        if self.selected_index is None:
            return None
        return self.candidates[self.selected_index]

    def as_parameters(self) -> dict[str, object]:
        return {
            **self.settings.as_parameters(),
            "candidate_count": len(self.candidates),
            "selected_index": self.selected_index,
            "candidates": [
                {
                    "position_mm": peak.position_mm,
                    "voltage_v": peak.voltage_v,
                    "prominence_v": peak.prominence_v,
                    "width_mm": peak.width_mm,
                    "position_uncertainty_mm": peak.position_uncertainty_mm,
                    "voltage_uncertainty_v": peak.voltage_uncertainty_v,
                }
                for peak in self.candidates
            ],
        }


def _smooth(values: list[float], window: int) -> list[float]:
    radius = window // 2
    return [
        sum(values[max(0, index - radius) : index + radius + 1])
        / len(values[max(0, index - radius) : index + radius + 1])
        for index in range(len(values))
    ]


def _remove_baseline(
    positions: list[float],
    values: list[float],
    mode: Literal["none", "linear"],
) -> list[float]:
    if mode == "none" or len(values) < 2:
        return values
    slope = (values[-1] - values[0]) / (positions[-1] - positions[0])
    return [
        value - (values[0] + slope * (position - positions[0]))
        for position, value in zip(positions, values)
    ]


def _crossing_position(
    positions: list[float],
    values: list[float],
    start: int,
    direction: int,
    level: float,
) -> float:
    index = start
    next_index = index + direction
    while 0 <= next_index < len(values) and values[next_index] > level:
        index = next_index
        next_index += direction
    if not 0 <= next_index < len(values):
        return positions[index]
    first, second = values[index], values[next_index]
    if math.isclose(first, second):
        return positions[index]
    ratio = (level - first) / (second - first)
    return positions[index] + ratio * (positions[next_index] - positions[index])


def analyze_peaks(
    measurements: list[MeasurementPoint],
    settings: PeakDetectionSettings | None = None,
    *,
    selected_index: int | None = None,
) -> PeakAnalysisResult:
    """Smooth, baseline-correct, and rank physically plausible peak candidates.

    ``voltage_v`` is the baseline-corrected optical response.  ``position_mm``
    is the motor position of the index-change candidate.  A refractive index is
    intentionally not inferred without an externally validated calibration.
    """
    if len(measurements) < 3:
        raise ValueError("Se necesitan al menos tres puntos para detectar picos")
    settings = settings or PeakDetectionSettings()

    sorted_measurements = sorted(measurements, key=lambda point: point.position_mm)
    positions = [point.position_mm for point in sorted_measurements]
    if len(set(positions)) != len(positions):
        raise ValueError("Las posiciones deben ser únicas para detectar picos")
    raw_values = [point.voltage_v for point in sorted_measurements]
    values = _remove_baseline(
        positions,
        _smooth(raw_values, settings.smoothing_window),
        settings.baseline_mode,
    )
    processed = tuple(
        MeasurementPoint(position, value) for position, value in zip(positions, values)
    )
    spacings = [right - left for left, right in pairwise(positions)]
    position_uncertainty = median(spacings) / 2
    residuals = [
        raw - processed_point.voltage_v
        for raw, processed_point in zip(raw_values, processed)
    ]
    voltage_uncertainty = math.sqrt(
        sum(residual * residual for residual in residuals) / len(residuals)
    )

    candidates: list[PeakCandidate] = []
    for index in range(1, len(values) - 1):
        value = values[index]
        if not (value >= values[index - 1] and value > values[index + 1]):
            continue
        left_base = min(values[: index + 1])
        right_base = min(values[index:])
        prominence = value - max(left_base, right_base)
        half_level = value - prominence / 2
        width = _crossing_position(positions, values, index, -1, half_level)
        width = _crossing_position(positions, values, index, 1, half_level) - width
        if (
            prominence < settings.minimum_prominence_v
            or width < settings.minimum_width_mm
        ):
            continue
        if settings.expected_position_range_mm is not None:
            start, end = settings.expected_position_range_mm
            if not start <= positions[index] <= end:
                continue
        candidates.append(
            PeakCandidate(
                position_mm=positions[index],
                voltage_v=value,
                prominence_v=prominence,
                width_mm=width,
                position_uncertainty_mm=position_uncertainty,
                voltage_uncertainty_v=voltage_uncertainty,
            )
        )

    candidates.sort(key=lambda peak: peak.prominence_v, reverse=True)
    accepted: list[PeakCandidate] = []
    for candidate in candidates:
        if all(
            abs(candidate.position_mm - accepted_peak.position_mm)
            >= settings.minimum_distance_mm
            for accepted_peak in accepted
        ):
            accepted.append(candidate)
    if selected_index is not None and not 0 <= selected_index < len(accepted):
        raise ValueError("El pico seleccionado no existe")
    return PeakAnalysisResult(
        candidates=tuple(accepted),
        selected_index=selected_index,
        processed_measurements=processed,
        settings=settings,
    )


def store_peak_analysis(run: RunRecord, analysis: PeakAnalysisResult) -> None:
    """Attach reproducible detection parameters to a persisted derived result."""
    run.analysis_parameters = {
        **run.analysis_parameters,
        "peak_detection": analysis.as_parameters(),
    }
