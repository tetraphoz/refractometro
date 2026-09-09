from __future__ import annotations

import dearpygui.dearpygui as dpg

from experiments.voltage_sweep import MeasurementPoint


def update_curve(curve_tag: str, measurements: list[MeasurementPoint]) -> None:
    """Update a plot line series from measurement points."""
    if not measurements:
        return

    dpg.set_value(
        curve_tag,
        [
            [measurement.position_mm for measurement in measurements],
            [measurement.voltage_v for measurement in measurements],
        ],
    )
