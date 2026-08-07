from __future__ import annotations

from experiments.voltage_sweep import MeasurementPoint


class CalibrationCurve:
    """
    Stores a reference measurement
    taken without a sample.
    """


    def __init__(
        self,
        measurements: list[MeasurementPoint],
    ):

        self.measurements = measurements



    def subtract(
        self,
        measurements: list[MeasurementPoint],
    ) -> list[MeasurementPoint]:
        """
        Subtracts the calibration background
        from a measurement.
        """


        if len(measurements) != len(
            self.measurements
        ):

            raise ValueError(
                "La calibración y la medición "
                "deben tener el mismo número de puntos"
            )


        corrected = []


        for measurement, baseline in zip(
            measurements,
            self.measurements,
        ):

            corrected.append(
                MeasurementPoint(
                    position_mm=
                    measurement.position_mm,

                    voltage_v=
                    (
                        measurement.voltage_v
                        -
                        baseline.voltage_v
                    ),
                )
            )


        return corrected
