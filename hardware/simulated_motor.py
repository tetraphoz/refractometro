from __future__ import annotations

import threading


class SimulatedMotor:
    """Configurable virtual Zaber axis for development and integration tests."""

    def __init__(
        self,
        *,
        latency_per_mm_s: float = 0.05,
        maximum_latency_s: float = 0.2,
        failing_move_numbers: frozenset[int] = frozenset(),
    ) -> None:
        if latency_per_mm_s < 0 or maximum_latency_s < 0:
            raise ValueError("La latencia simulada no puede ser negativa")
        self.position_mm = 0.0
        self.connected = False
        self.latency_per_mm_s = latency_per_mm_s
        self.maximum_latency_s = maximum_latency_s
        self.failing_move_numbers = failing_move_numbers
        self.move_count = 0
        self._stop_requested = threading.Event()

    def connect(
        self,
        port: str = "SIM",
    ) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def move_absolute(
        self,
        position_mm: float,
    ) -> None:
        if not self.connected:
            raise RuntimeError("Motor simulado desconectado")

        self.move_count += 1
        if self.move_count in self.failing_move_numbers:
            raise RuntimeError("Fallo simulado del motor")

        distance = abs(position_mm - self.position_mm)
        self._stop_requested.clear()
        delay_s = min(distance * self.latency_per_mm_s, self.maximum_latency_s)
        if self._stop_requested.wait(delay_s):
            return

        self.position_mm = position_mm

    def stop(self) -> None:
        self._stop_requested.set()
