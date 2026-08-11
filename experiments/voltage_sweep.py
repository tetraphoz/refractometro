from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable


@dataclass
class MeasurementPoint:
    """
    Resultado de una medición individual.
    """

    position_mm: float
    voltage_v: float



class VoltageSweep:
    """
    Ejecuta un barrido de posición y voltaje.

    Dependencias inyectadas:
        motor:
            Debe implementar move_absolute(position_mm)

        sensor:
            Debe implementar read_voltage()
    """


    def __init__(
        self,
        motor,
        sensor,
    ):

        self.motor = motor
        self.sensor = sensor



    def run(
        self,
        start_position_mm: float,
        end_position_mm: float,
        number_of_points: int,
        stabilization_time_s: float,
        progress_callback: (
            Callable[
                [
                    MeasurementPoint
                ],
                None
            ]
            | None
        ) = None,
    ) -> list[MeasurementPoint]:


        if number_of_points < 2:
            raise ValueError(
                "Se necesitan al menos dos puntos"
            )


        step_mm = (
            end_position_mm
            -
            start_position_mm
        ) / (
            number_of_points - 1
        )


        results: list[MeasurementPoint] = []


        for index in range(number_of_points):

            position_mm = (
                start_position_mm
                +
                index * step_mm
            )


            self.motor.move_absolute(position_mm)


            time.sleep(stabilization_time_s)


            voltage_v = (
                self.sensor
                .read_voltage()
            )


            measurement = MeasurementPoint(
                position_mm=position_mm,
                voltage_v=voltage_v,
            )


            results.append(measurement)


            if progress_callback:
                progress_callback(results.copy())


        return results



    #TODO: Find multiple peaks
    @staticmethod
    def find_peak(
        measurements: list[MeasurementPoint],
    ) -> MeasurementPoint:

        if not measurements:
            raise ValueError(
                "No hay mediciones"
            )


        return max(
            measurements,
            key=lambda item: item.voltage_v,
        )
