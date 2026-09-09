from __future__ import annotations

import csv

from zaber_motion.exceptions import MotionLibException


class OperationCancelled(RuntimeError):
    """Raised when a running hardware operation is cancelled by the user."""


OPERATION_ERRORS = (OSError, RuntimeError, ValueError, csv.Error, MotionLibException)
CALLBACK_ERRORS = (OSError, RuntimeError, ValueError)
