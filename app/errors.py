from __future__ import annotations

import csv
from typing import TYPE_CHECKING

from zaber_motion.exceptions import MotionLibException

if TYPE_CHECKING:
    from experiments.voltage_sweep import MeasurementPoint


class OperationCancelled(RuntimeError):
    """Cancellation with the readings acquired before the stop request."""

    def __init__(self, measurements: list[MeasurementPoint] | None = None) -> None:
        super().__init__("Adquisición cancelada")
        self.measurements = measurements if measurements is not None else []


OPERATION_ERRORS = (OSError, RuntimeError, ValueError, csv.Error, MotionLibException)
CALLBACK_ERRORS = (OSError, RuntimeError, ValueError)
