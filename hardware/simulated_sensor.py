from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence


class SimulatedESP32Sensor:
    """Configurable optoelectronic voltage sensor for development and tests.

    The default configuration preserves the original simulated curve.  Tests can
    set ``noise_amplitude_v=0`` and a ``random_seed`` for deterministic data, or
    inject drift, outliers, and selected read failures to exercise batch quality
    handling without real hardware.
    """

    def __init__(
        self,
        motor,
        *,
        baseline_voltage_v: float = 0.2,
        peaks: Sequence[tuple[float, float, float]] | None = None,
        noise_amplitude_v: float = 0.03,
        drift_per_read_v: float = 0.0,
        outlier_offsets_v: Mapping[int, float] | None = None,
        failing_read_numbers: frozenset[int] = frozenset(),
        random_seed: int | None = None,
    ) -> None:
        if noise_amplitude_v < 0:
            raise ValueError("El ruido simulado no puede ser negativo")
        self.motor = motor
        self.connected = False
        self.baseline_voltage_v = baseline_voltage_v
        self.peaks = tuple(peaks or ((6.0, 2.5, 2.0),))
        self.noise_amplitude_v = noise_amplitude_v
        self.drift_per_read_v = drift_per_read_v
        self.outlier_offsets_v = dict(outlier_offsets_v or {})
        self.failing_read_numbers = failing_read_numbers
        self.read_count = 0
        self._random = random.Random(random_seed)

    def connect(
        self,
        port: str = "SIM",
        baud_rate: int = 115200,
    ) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def read_voltage(self) -> float:
        if not self.connected:
            raise RuntimeError("Sensor simulado desconectado")

        self.read_count += 1
        if self.read_count in self.failing_read_numbers:
            raise RuntimeError("Fallo simulado del sensor")

        x = self.motor.position_mm
        signal = sum(
            intensity * math.exp(-((x - position) ** 2) / width)
            for position, intensity, width in self.peaks
        )
        noise = self._random.uniform(-self.noise_amplitude_v, self.noise_amplitude_v)
        drift = (self.read_count - 1) * self.drift_per_read_v
        outlier = self.outlier_offsets_v.get(self.read_count, 0.0)
        return self.baseline_voltage_v + signal + noise + drift + outlier
