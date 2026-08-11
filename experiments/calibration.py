from __future__ import annotations

import bisect

from experiments.voltage_sweep import MeasurementPoint

class CalibrationCurve:
    """
    Curva de referencia obtenida sin muestra.

    ```
    Permite restar el fondo (offset / ruido del sistema)
    a una medición real.

    La referencia se interpola linealmente para permitir
    distintas cantidades de puntos entre ambas corridas.
    """

    def __init__(
        self,
        measurements: list[MeasurementPoint],
    ):

        if not measurements:
            raise ValueError(
                "La calibración no contiene mediciones"
            )

        self.measurements = sorted(
            measurements,
            key=lambda m: m.position_mm,
        )

    def subtract(
        self,
        measurements: list[MeasurementPoint],
    ) -> list[MeasurementPoint]:

        positions = [
            m.position_mm
            for m in self.measurements
        ]

        voltages = [
            m.voltage_v
            for m in self.measurements
        ]

        corrected: list[MeasurementPoint] = []

        for measurement in measurements:

            baseline_voltage = self.interpolate(
                positions,
                voltages,
                measurement.position_mm,
            )

            corrected.append(
                MeasurementPoint(
                    position_mm=
                    measurement.position_mm,

                    voltage_v=
                    measurement.voltage_v
                    -
                    baseline_voltage,
                )
            )

        return corrected

    @staticmethod
    def interpolate(
        positions: list[float],
        voltages: list[float],
        x: float,
    ) -> float:

        count = len(positions)

        if count == 0:
            return 0.0

        if count == 1:
            return voltages[0]

        if x <= positions[0]:
            return voltages[0]

        if x >= positions[-1]:
            return voltages[-1]

        index = bisect.bisect_left(
            positions,
            x,
        )

        x0 = positions[index - 1]
        x1 = positions[index]

        y0 = voltages[index - 1]
        y1 = voltages[index]

        if x1 == x0:
            return y0

        t = (
            (x - x0)
            /
            (x1 - x0)
        )

        return (
            y0
            +
            t * (y1 - y0)
        )
