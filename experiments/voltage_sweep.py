from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from app.errors import OperationCancelled


@dataclass
class MeasurementPoint:
    """
    Resultado de una medición individual.
    """

    position_mm: float
    voltage_v: float


@dataclass(frozen=True)
class BatchProgress:
    """Progress of one sweep within a repeated acquisition."""

    run_number: int
    total_runs: int
    measurements: tuple[MeasurementPoint, ...]


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
        progress_callback: Callable[[list[MeasurementPoint]], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> list[MeasurementPoint]:
        if number_of_points < 2:
            raise ValueError("Se necesitan al menos dos puntos")
        if stabilization_time_s < 0:
            raise ValueError("El tiempo de estabilización no puede ser negativo")

        step_mm = (end_position_mm - start_position_mm) / (number_of_points - 1)

        results: list[MeasurementPoint] = []

        for index in range(number_of_points):
            if cancel_event is not None and cancel_event.is_set():
                raise OperationCancelled

            position_mm = start_position_mm + index * step_mm

            self.motor.move_absolute(position_mm)

            if cancel_event is None:
                time.sleep(stabilization_time_s)
            elif cancel_event.wait(stabilization_time_s):
                raise OperationCancelled

            if cancel_event is not None and cancel_event.is_set():
                raise OperationCancelled

            voltage_v = self.sensor.read_voltage()

            measurement = MeasurementPoint(
                position_mm=position_mm,
                voltage_v=voltage_v,
            )

            results.append(measurement)

            if progress_callback:
                progress_callback(results.copy())

        return results

    def run_batch(
        self,
        start_position_mm: float,
        end_position_mm: float,
        number_of_points: int,
        stabilization_time_s: float,
        number_of_runs: int,
        progress_callback: Callable[[BatchProgress], None] | None = None,
        run_finished_callback: (
            Callable[[int, list[MeasurementPoint]], None] | None
        ) = None,
        cancel_event: threading.Event | None = None,
    ) -> list[list[MeasurementPoint]]:
        """Acquire repeated sweeps while preserving each raw result."""
        if number_of_runs < 1:
            raise ValueError("Se necesita al menos un barrido")

        results: list[list[MeasurementPoint]] = []

        for run_number in range(1, number_of_runs + 1):

            def on_progress(
                measurements: list[MeasurementPoint],
                run_number: int = run_number,
            ) -> None:
                if progress_callback is not None:
                    progress_callback(
                        BatchProgress(
                            run_number=run_number,
                            total_runs=number_of_runs,
                            measurements=tuple(measurements),
                        )
                    )

            measurements = self.run(
                start_position_mm=start_position_mm,
                end_position_mm=end_position_mm,
                number_of_points=number_of_points,
                stabilization_time_s=stabilization_time_s,
                progress_callback=on_progress,
                cancel_event=cancel_event,
            )
            results.append(measurements)

            if run_finished_callback is not None:
                run_finished_callback(run_number, measurements)

        return results

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
                if n == 1 or (
                    v >= sorted_meas[i + 1].voltage_v
                    and v > sorted_meas[i + 1].voltage_v
                ):
                    peaks.append(sorted_meas[i])
                continue

            if i == n - 1:
                if (
                    v >= sorted_meas[i - 1].voltage_v
                    and v > sorted_meas[i - 1].voltage_v
                ):
                    peaks.append(sorted_meas[i])
                continue

            left = sorted_meas[i - 1].voltage_v
            right = sorted_meas[i + 1].voltage_v

            # interior point: local maximum if >= both neighbors
            # and strictly greater than at least one
            if (v >= left and v >= right) and (v > left or v > right):
                peaks.append(sorted_meas[i])

        # sort peaks by voltage descending
        peaks.sort(key=lambda m: m.voltage_v, reverse=True)
        return peaks
