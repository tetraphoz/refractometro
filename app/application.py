from __future__ import annotations

import threading
from typing import Callable

from storage.csv import save_measurements_csv
from experiments.voltage_sweep import (
    MeasurementPoint,
    VoltageSweep,
)

from experiments.calibration import CalibrationCurve


class ApplicationController:
    """
    Controlador principal de la aplicación.

    Coordina:
        - ESP32
        - Motor Zaber
        - Experimentos
        - Exportación de datos

    La interfaz gráfica solamente llama
    a los métodos públicos de esta clase.
    """


    def __init__(
        self,
        motor,
        sensor,
    ):

        self.motor = motor
        self.sensor = sensor

        self.sweep = VoltageSweep(
            motor=self.motor,
            sensor=self.sensor,
        )

        self._sweep_thread: threading.Thread | None = None

        self.calibration = None
        self._running = False



    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------

    @property
    def sweep_running(self) -> bool:

        return self._running



    # ------------------------------------------------------------------
    # ESP32
    # ------------------------------------------------------------------

    def connect_sensor(
        self,
        port: str,
        baud_rate: int,
    ) -> None:

        self.sensor.connect(
            port,
            baud_rate,
        )



    def disconnect_sensor(self) -> None:

        self.sensor.disconnect()



    # ------------------------------------------------------------------
    # Motor
    # ------------------------------------------------------------------

    def connect_motor(
        self,
        port: str,
    ) -> None:

        self.motor.connect(
            port,
        )



    def disconnect_motor(self) -> None:

        self.motor.disconnect()



    def move_motor(
        self,
        position_mm: float,
    ) -> None:

        self.motor.move_absolute(
            position_mm
        )



    # ------------------------------------------------------------------
    # Barrido
    # ------------------------------------------------------------------

    def start_voltage_sweep(
        self,
        start_position_mm: float,
        end_position_mm: float,
        number_of_points: int,
        stabilization_time_s: float,
        csv_filename: str,
        on_progress: (
            Callable[
                [
                    MeasurementPoint
                ],
                None
            ]
            | None
        ) = None,
        on_finished: (
            Callable[
                [
                    MeasurementPoint
                ],
                None
            ]
            | None
        ) = None,
    ) -> None:


        if self._running:
            return


        self._running = True


        def worker():

            try:

                measurements = (
                    self.sweep.run(
                        start_position_mm=
                            start_position_mm,

                        end_position_mm=
                            end_position_mm,

                        number_of_points=
                            number_of_points,

                        stabilization_time_s=
                            stabilization_time_s,

                        progress_callback=
                            on_progress,
                    )
                )


                # Save CSV with metadata
                metadata = {
                    "start_position_mm": str(start_position_mm),
                    "end_position_mm": str(end_position_mm),
                    "number_of_points": str(number_of_points),
                    "stabilization_time_s": str(stabilization_time_s),
                }

                save_measurements_csv(
                    csv_filename,
                    measurements,
                    metadata=metadata,
                )


                # Find all peaks (may be zero or more) and notify UI
                peaks = self.sweep.find_peaks(measurements)

                if on_finished:
                    # previously on_finished expected one MeasurementPoint;
                    # now it receives a list[MeasurementPoint]
                    on_finished(peaks)


            finally:

                # Attempt to return motor to initial position (best-effort).
                try:
                    # motor may or may not be connected; ignore failures.
                    self.motor.move_absolute(start_position_mm)
                except Exception:
                    pass

                self._running = False



        self._sweep_thread = threading.Thread(
            target=worker,
            daemon=True,
        )

        self._sweep_thread.start()


    def start_calibration(
        self,
        start_position_mm: float,
        end_position_mm: float,
        number_of_points: int,
        stabilization_time_s: float,
        on_progress=None,
        on_finished=None,
    ):

        if self._running:
            return


        self._running = True


        def worker():

            try:

                measurements = (
                    self.sweep.run(
                        start_position_mm=
                        start_position_mm,

                        end_position_mm=
                        end_position_mm,

                        number_of_points=
                        number_of_points,

                        stabilization_time_s=
                        stabilization_time_s,

                        progress_callback=
                        on_progress,
                    )
                )


                self.calibration = (
                    CalibrationCurve(
                        measurements
                    )
                )


                if on_finished:

                    on_finished(
                        measurements
                    )


            finally:

                self._running = False



        thread = threading.Thread(
            target=worker,
            daemon=True,
        )

        thread.start()


