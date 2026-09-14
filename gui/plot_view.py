from __future__ import annotations

import math

import dearpygui.dearpygui as dpg

from experiments.voltage_sweep import MeasurementPoint

# Plot input is deliberately configured here instead of being spread across the
# interface.  ImPlot already provides the interactions we need: the wheel zooms
# around the cursor, dragging pans, and a double left click fits the visible
# series.  Keeping these settings together makes it much harder for a new plot
# to accidentally fall back to the old button-based interaction.
PLOT_INTERACTION = {
    # Middle drag remains available through ImPlot; left drag is handled
    # explicitly so it also works when a parent child-window captures input.
    "pan_button": dpg.mvMouseButton_Middle,
    # Fit is handled explicitly so double click returns to the application's
    # known initial range rather than merely fitting the currently visible data.
    "fit_button": dpg.mvMouseButton_X2,
    # Wheel zoom is handled explicitly by ``zoom_plot_at_cursor``.  Requiring
    # Ctrl here prevents ImPlot and the explicit handler from applying zoom
    # twice to the same wheel event.
    "zoom_mod": dpg.mvKey_ModCtrl,
    "zoom_rate": 0.1,
    "crosshairs": True,
}


def update_curve(curve_tag: str, measurements: list[MeasurementPoint]) -> None:
    """Update a plot line series, including clearing a completed empty run."""
    if not dpg.does_item_exist(curve_tag):
        return

    dpg.set_value(
        curve_tag,
        [
            [measurement.position_mm for measurement in measurements],
            [measurement.voltage_v for measurement in measurements],
        ],
    )


def plot_interaction_options() -> dict[str, object]:
    """Return a copy of the standard, mouse-first plot interaction options."""
    return dict(PLOT_INTERACTION)


def zoom_plot_at_cursor(
    plot_tag: str,
    x_axis_tag: str,
    y_axis_tag: str,
    wheel_delta: float,
) -> None:
    """Zoom both axes around the current cursor position.

    DearPyGui's native plot wheel handling depends on the parent child-window
    capturing the wheel first.  The application uses a global wheel handler so
    this remains reliable when the plot is embedded in a resizable layout.
    """
    if wheel_delta == 0 or not dpg.does_item_exist(plot_tag):
        return
    try:
        cursor_x, cursor_y = dpg.get_plot_mouse_pos()
        x_min, x_max = dpg.get_axis_limits(x_axis_tag)
        y_min, y_max = dpg.get_axis_limits(y_axis_tag)
    except (KeyError, RuntimeError):
        return

    # Positive wheel deltas zoom in.  Exponential scaling keeps each wheel
    # notch proportional at every zoom level and works with touchpad deltas.
    factor = math.pow(0.9, float(wheel_delta))
    dpg.set_axis_limits(
        x_axis_tag,
        cursor_x + (x_min - cursor_x) * factor,
        cursor_x + (x_max - cursor_x) * factor,
    )
    dpg.set_axis_limits(
        y_axis_tag,
        cursor_y + (y_min - cursor_y) * factor,
        cursor_y + (y_max - cursor_y) * factor,
    )


def pan_plot(
    plot_tag: str,
    x_axis_tag: str,
    y_axis_tag: str,
    delta_x_px: float,
    delta_y_px: float,
) -> None:
    """Translate plot limits using a screen-space drag delta."""
    if not dpg.does_item_exist(plot_tag):
        return
    try:
        width, height = dpg.get_item_rect_size(plot_tag)
        x_min, x_max = dpg.get_axis_limits(x_axis_tag)
        y_min, y_max = dpg.get_axis_limits(y_axis_tag)
    except (KeyError, RuntimeError):
        return
    if width <= 0 or height <= 0:
        return

    x_shift = -(x_max - x_min) * float(delta_x_px) / width
    y_shift = (y_max - y_min) * float(delta_y_px) / height
    dpg.set_axis_limits(x_axis_tag, x_min + x_shift, x_max + x_shift)
    dpg.set_axis_limits(y_axis_tag, y_min + y_shift, y_max + y_shift)
