from __future__ import annotations

from collections.abc import Sequence

from app.models import RunRecord
from experiments.calibration import CalibrationCurve
from experiments.voltage_sweep import MeasurementPoint


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


def average_runs(runs: Sequence[RunRecord]) -> list[MeasurementPoint]:
    """Average runs on a shared grid over their common position range."""
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

    return [
        MeasurementPoint(
            position_mm=position,
            voltage_v=sum(
                curve.interpolate(
                    [point.position_mm for point in curve.measurements],
                    [point.voltage_v for point in curve.measurements],
                    position,
                )
                for curve in curves
            )
            / len(curves),
        )
        for position in positions
    ]


def format_peak_summary(
    peaks: Sequence[MeasurementPoint],
    limit: int = 5,
) -> str:
    return "\n".join(
        f"{idx}. {peak.voltage_v:.4f}V @ {peak.position_mm:.2f}mm"
        for idx, peak in enumerate(peaks[:limit], start=1)
    )
