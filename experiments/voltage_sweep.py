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

    @staticmethod
    def find_peaks(
        measurements: list[MeasurementPoint],
    ) -> list[MeasurementPoint]:
        """
        Find local maxima (3-point neighborhood test, tolerant to small
        plateaus). Returns peaks sorted by voltage_v descending.
        """

        if not measurements:
            return []

        # Sort by position to ensure neighbor order
        sorted_meas = sorted(measurements, key=lambda m: m.position_mm)
        n = len(sorted_meas)

        peaks: list[MeasurementPoint] = []

        for i in range(n):
            v = sorted_meas[i].voltage_v

            # endpoints: compare with the single neighbor
            if i == 0:
                if n == 1:
                    peaks.append(sorted_meas[i])
                elif v >= sorted_meas[i + 1].voltage_v and v > sorted_meas[i + 1].voltage_v:
                    peaks.append(sorted_meas[i])
                continue

            if i == n - 1:
                if v >= sorted_meas[i - 1].voltage_v and v > sorted_meas[i - 1].voltage_v:
                    peaks.append(sorted_meas[i])
                continue

            left = sorted_meas[i - 1].voltage_v
            right = sorted_meas[i + 1].voltage_v

            # interior point: local maximum if >= both neighbors and strictly greater than at least one
            if (v >= left and v >= right) and (v > left or v > right):
                peaks.append(sorted_meas[i])

        # sort peaks by voltage descending
        peaks.sort(key=lambda m: m.voltage_v, reverse=True)
        return peaks
