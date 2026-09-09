from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from app.models import RunRecord, RunStatus
from experiments.calibration import CalibrationCurve
from experiments.voltage_sweep import MeasurementPoint


@dataclass(frozen=True)
class AveragePoint:
    """A point in an averaged curve and its repeatability statistics."""

    position_mm: float
    voltage_v: float
    standard_deviation_v: float
    sample_count: int


@dataclass(frozen=True)
class AverageResult:
    """Average of several runs on a shared position grid."""

    points: tuple[AveragePoint, ...]
    source_uids: tuple[str, ...]

    @property
    def measurements(self) -> list[MeasurementPoint]:
        """Return the averaged curve in the format used by the plotter."""
        return [
            MeasurementPoint(point.position_mm, point.voltage_v)
            for point in self.points
        ]


def interpolate(
    positions: Sequence[float],
    voltages: Sequence[float],
    x: float,
) -> float:
    return CalibrationCurve.interpolate(
        list(positions),
        list(voltages),
        x,
    )


def subtract_reference(
    run: RunRecord,
    reference: RunRecord,
) -> list[MeasurementPoint]:
    """Subtract a reference run from another run using linear interpolation."""

    measurements = run.measurements
    reference_measurements = reference.measurements

    if not measurements or not reference_measurements:
        raise ValueError("Ambas corridas necesitan mediciones para poder restar")

    return CalibrationCurve(reference_measurements).subtract(measurements)


def averageable_runs(runs: Sequence[RunRecord]) -> list[RunRecord]:
    """Return completed source runs that can participate in an average."""
    return [
        run
        for run in runs
        if run.kind != "promedio"
        and run.status is RunStatus.COMPLETED
        and run.measurements
    ]


def _common_positions(
    runs: Sequence[RunRecord],
) -> tuple[list[CalibrationCurve], list[float]]:
    if not runs:
        raise ValueError("Se necesita al menos una corrida para promediar")
    if any(not run.measurements for run in runs):
        raise ValueError("Todas las corridas necesitan mediciones")

    curves = [CalibrationCurve(run.measurements) for run in runs]
    ranges = [
        (curve.measurements[0].position_mm, curve.measurements[-1].position_mm)
        for curve in curves
    ]
    start = max(first for first, _ in ranges)
    end = min(last for _, last in ranges)

    if start > end:
        raise ValueError("Las corridas no tienen un rango de posiciones común")

    sample_count = min(len(curve.measurements) for curve in curves)
    if start == end:
        positions = [start]
    else:
        positions = [
            start + index * (end - start) / (sample_count - 1)
            for index in range(sample_count)
        ]

    return curves, positions


def _interpolated_values(
    curves: Sequence[CalibrationCurve],
    position: float,
) -> list[float]:
    return [
        curve.interpolate(
            [point.position_mm for point in curve.measurements],
            [point.voltage_v for point in curve.measurements],
            position,
        )
        for curve in curves
    ]


def average_runs_with_statistics(runs: Sequence[RunRecord]) -> AverageResult:
    """Average runs and calculate point-wise repeatability statistics."""
    curves, positions = _common_positions(runs)
    points = []

    for position in positions:
        values = _interpolated_values(curves, position)
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        points.append(
            AveragePoint(
                position_mm=position,
                voltage_v=mean,
                standard_deviation_v=math.sqrt(variance),
                sample_count=len(values),
            )
        )

    return AverageResult(
        points=tuple(points),
        source_uids=tuple(run.uid for run in runs),
    )


def average_runs(runs: Sequence[RunRecord]) -> list[MeasurementPoint]:
    """Average runs on a shared grid over their common position range."""
    return average_runs_with_statistics(runs).measurements


def format_peak_summary(
    peaks: Sequence[MeasurementPoint],
    limit: int = 5,
) -> str:
    return "\n".join(
        f"{idx}. {peak.voltage_v:.4f}V @ {peak.position_mm:.2f}mm"
        for idx, peak in enumerate(peaks[:limit], start=1)
    )
