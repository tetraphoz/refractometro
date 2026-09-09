from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class OperationStatus(StrEnum):
    """Lifecycle state of a hardware operation."""

    IDLE = "idle"
    RUNNING = "running"
    CANCELLING = "cancelling"


@dataclass
class OperationState:
    """Tracks device connection state independently from GUI widgets."""

    sensor_connected: bool = False
    motor_connected: bool = False

    @property
    def operations_enabled(self) -> bool:
        return bool(self.sensor_connected and self.motor_connected)
