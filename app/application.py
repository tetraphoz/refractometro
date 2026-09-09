from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from app.errors import CALLBACK_ERRORS, OPERATION_ERRORS, OperationCancelled
from app.operation_state import OperationStatus
from experiments.calibration import CalibrationCurve
from experiments.voltage_sweep import BatchProgress, MeasurementPoint, VoltageSweep
from hardware.protocols import Motor, Sensor
from storage.csv import save_measurements_csv

logger = logging.getLogger(__name__)


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
        motor: Motor,
        sensor: Sensor,
    ):
        self.motor = motor
        self.sensor = sensor

        self.sweep = VoltageSweep(
            motor=self.motor,
            sensor=self.sensor,
        )

        self._sweep_thread: threading.Thread | None = None
        self._state_lock = threading.Lock()
        self._cancel_event: threading.Event | None = None
        self._laser_started_at = time.monotonic()
        self._operation_status = OperationStatus.IDLE

        self.calibration = None

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------

    @property
    def laser_on_time_s(self) -> float:
        """Elapsed laser-on time, assuming the laser starts with the app."""
        return max(0.0, time.monotonic() - self._laser_started_at)

    @property
    def operation_status(self) -> OperationStatus:
        with self._state_lock:
            return self._operation_status

    @property
    def sweep_running(self) -> bool:
        return self.operation_status is not OperationStatus.IDLE

    def _begin_operation(self) -> threading.Event:
        with self._state_lock:
            if self._operation_status is not OperationStatus.IDLE:
                raise RuntimeError("Ya hay una operación en curso")
            self._operation_status = OperationStatus.RUNNING
            self._cancel_event = threading.Event()
            return self._cancel_event

    def _end_operation(self) -> None:
        with self._state_lock:
            self._operation_status = OperationStatus.IDLE
            self._cancel_event = None

    def cancel_operation(self) -> bool:
        """Request cancellation and stop the motor when supported."""
        with self._state_lock:
            cancel_event = self._cancel_event
            if self._operation_status is not OperationStatus.RUNNING:
                return False
            self._operation_status = OperationStatus.CANCELLING

        if cancel_event is None:
            return False

        cancel_event.set()

        try:
            self.motor.stop()
        except OPERATION_ERRORS:
            logger.exception("Failed to stop motor after cancellation")

        return True

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
        self.motor.move_absolute(position_mm)

    # ------------------------------------------------------------------
    # Barrido
    # ------------------------------------------------------------------

    @staticmethod
    def _notify_error(
        callback: Callable[[Exception], None] | None,
        exc: Exception,
        operation: str,
    ) -> None:
        logger.error(
            "%s failed",
            operation,
            exc_info=(type(exc), exc, exc.__traceback__),
        )

        if callback is None:
            return

        try:
            callback(exc)
        except CALLBACK_ERRORS:
            logger.exception("%s error callback failed", operation)

    @staticmethod
    def _notify_finished(
        callback: Callable[[list[MeasurementPoint]], None] | None,
        result: list[MeasurementPoint],
        operation: str,
    ) -> None:
        if callback is None:
            return

        try:
            callback(result)
        except CALLBACK_ERRORS:
            logger.exception("%s finished callback failed", operation)

    @staticmethod
    def _notify_cancelled(
        callback: Callable[[list[MeasurementPoint]], None] | None,
        result: list[MeasurementPoint],
        operation: str,
    ) -> None:
        if callback is None:
            return

        try:
            callback(result)
        except CALLBACK_ERRORS:
            logger.exception("%s cancellation callback failed", operation)

    def start_voltage_sweep(
        self,
        start_position_mm: float,
        end_position_mm: float,
        number_of_points: int,
        stabilization_time_s: float,
        filename: str,
        on_progress: Callable[[list[MeasurementPoint]], None] | None = None,
        on_finished: Callable[[list[MeasurementPoint]], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        on_cancelled: Callable[[list[MeasurementPoint]], None] | None = None,
    ) -> None:
        laser_on_time_s = self.laser_on_time_s
        cancel_event = self._begin_operation()

        def worker():
            measurements: list[MeasurementPoint] = []
            peaks: list[MeasurementPoint] = []
            error: Exception | None = None
            cancelled = False

            try:
                measurements = self.sweep.run(
                    start_position_mm=start_position_mm,
                    end_position_mm=end_position_mm,
                    number_of_points=number_of_points,
                    stabilization_time_s=stabilization_time_s,
                    progress_callback=on_progress,
                    cancel_event=cancel_event,
                )

                # Save CSV with metadata
                metadata = {
                    "start_position_mm": str(start_position_mm),
                    "end_position_mm": str(end_position_mm),
                    "number_of_points": str(number_of_points),
                    "stabilization_time_s": str(stabilization_time_s),
                    "laser_on_time_s": f"{laser_on_time_s:.6f}",
                }

                save_measurements_csv(
                    filename,
                    measurements,
                    metadata=metadata,
                )

                # Find all peaks (may be zero or more) and notify UI
                peaks = self.sweep.find_peaks(measurements)

            except OperationCancelled:
                cancelled = True
            except OPERATION_ERRORS as exc:
                error = exc

            finally:
                # Attempt to return motor to initial position (best-effort).
                try:
                    # motor may or may not be connected; ignore failures.
                    self.motor.move_absolute(start_position_mm)
                except OPERATION_ERRORS:
                    # Best-effort: log failure to return motor to initial position
                    # for debugging.
                    logger.debug(
                        "Failed to return motor to initial position", exc_info=True
                    )
                finally:
                    self._end_operation()

            if cancelled:
                self._notify_cancelled(on_cancelled, measurements, "Voltage sweep")
            elif error is not None:
                self._notify_error(on_error, error, "Voltage sweep")
            else:
                self._notify_finished(on_finished, peaks, "Voltage sweep")

        self._sweep_thread = threading.Thread(
            target=worker,
            daemon=True,
        )

        self._sweep_thread.start()

    @staticmethod
    def _notify_batch_error(
        callback: Callable[[Exception, list[list[MeasurementPoint]]], None] | None,
        exc: Exception,
        partial_results: list[list[MeasurementPoint]],
        operation: str,
    ) -> None:
        logger.error(
            "%s failed after %d completed runs",
            operation,
            len(partial_results),
            exc_info=(type(exc), exc, exc.__traceback__),
        )

        if callback is None:
            return

        try:
            callback(exc, partial_results)
        except CALLBACK_ERRORS:
            logger.exception("%s error callback failed", operation)

    @staticmethod
    def _notify_batch_finished(
        callback: Callable[[list[list[MeasurementPoint]]], None] | None,
        results: list[list[MeasurementPoint]],
        operation: str,
    ) -> None:
        if callback is None:
            return

        try:
            callback(results)
        except CALLBACK_ERRORS:
            logger.exception("%s finished callback failed", operation)

    @staticmethod
    def _notify_batch_cancelled(
        callback: Callable[[list[list[MeasurementPoint]]], None] | None,
        partial_results: list[list[MeasurementPoint]],
        operation: str,
    ) -> None:
        if callback is None:
            return

        try:
            callback(partial_results)
        except CALLBACK_ERRORS:
            logger.exception("%s cancellation callback failed", operation)

    def start_voltage_batch(
        self,
        start_position_mm: float,
        end_position_mm: float,
        number_of_points: int,
        stabilization_time_s: float,
        number_of_runs: int,
        filename_factory: Callable[[int], str],
        metadata: dict[str, str] | None = None,
        on_progress: Callable[[BatchProgress], None] | None = None,
        on_run_finished: Callable[[int, list[MeasurementPoint]], None] | None = None,
        on_finished: Callable[[list[list[MeasurementPoint]]], None] | None = None,
        on_error: (
            Callable[[Exception, list[list[MeasurementPoint]]], None] | None
        ) = None,
        on_cancelled: Callable[[list[list[MeasurementPoint]]], None] | None = None,
    ) -> None:
        """Acquire and persist repeated raw sweeps as one batch."""
        laser_on_time_s = self.laser_on_time_s
        cancel_event = self._begin_operation()
        partial_results: list[list[MeasurementPoint]] = []
        base_metadata = dict(metadata or {})
        base_metadata.update(
            {
                "start_position_mm": str(start_position_mm),
                "end_position_mm": str(end_position_mm),
                "number_of_points": str(number_of_points),
                "stabilization_time_s": str(stabilization_time_s),
                "number_of_runs": str(number_of_runs),
                "laser_on_time_s": f"{laser_on_time_s:.6f}",
            }
        )

        def worker() -> None:
            error: Exception | None = None
            cancelled = False

            def save_run(
                run_number: int,
                measurements: list[MeasurementPoint],
            ) -> None:
                run_metadata = {
                    **base_metadata,
                    "run_number": str(run_number),
                }
                save_measurements_csv(
                    filename_factory(run_number),
                    measurements,
                    metadata=run_metadata,
                )
                partial_results.append(measurements)
                if on_run_finished is not None:
                    on_run_finished(run_number, measurements)

            try:
                results = self.sweep.run_batch(
                    start_position_mm=start_position_mm,
                    end_position_mm=end_position_mm,
                    number_of_points=number_of_points,
                    stabilization_time_s=stabilization_time_s,
                    number_of_runs=number_of_runs,
                    progress_callback=on_progress,
                    run_finished_callback=save_run,
                    cancel_event=cancel_event,
                )
            except OperationCancelled:
                cancelled = True
                results = partial_results
            except OPERATION_ERRORS as exc:
                error = exc
                results = partial_results
            finally:
                try:
                    self.motor.move_absolute(start_position_mm)
                except OPERATION_ERRORS:
                    logger.debug(
                        "Failed to return motor to initial position", exc_info=True
                    )
                finally:
                    self._end_operation()

            if cancelled:
                self._notify_batch_cancelled(
                    on_cancelled,
                    partial_results,
                    "Voltage batch",
                )
            elif error is not None:
                self._notify_batch_error(
                    on_error,
                    error,
                    partial_results,
                    "Voltage batch",
                )
            else:
                self._notify_batch_finished(on_finished, results, "Voltage batch")

        self._sweep_thread = threading.Thread(target=worker, daemon=True)
        self._sweep_thread.start()

    def start_calibration(
        self,
        start_position_mm: float,
        end_position_mm: float,
        number_of_points: int,
        stabilization_time_s: float,
        on_progress: Callable[[list[MeasurementPoint]], None] | None = None,
        on_finished: Callable[[list[MeasurementPoint]], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        on_cancelled: Callable[[list[MeasurementPoint]], None] | None = None,
    ) -> None:
        cancel_event = self._begin_operation()

        def worker():
            measurements: list[MeasurementPoint] = []
            error: Exception | None = None
            cancelled = False

            try:
                measurements = self.sweep.run(
                    start_position_mm=start_position_mm,
                    end_position_mm=end_position_mm,
                    number_of_points=number_of_points,
                    stabilization_time_s=stabilization_time_s,
                    progress_callback=on_progress,
                    cancel_event=cancel_event,
                )

                self.calibration = CalibrationCurve(measurements)

            except OperationCancelled:
                cancelled = True
            except OPERATION_ERRORS as exc:
                error = exc

            finally:
                try:
                    self.motor.move_absolute(start_position_mm)
                except OPERATION_ERRORS:
                    logger.debug(
                        "Failed to return motor to initial position", exc_info=True
                    )
                finally:
                    self._end_operation()

            if cancelled:
                self._notify_cancelled(on_cancelled, measurements, "Calibration")
            elif error is not None:
                self._notify_error(on_error, error, "Calibration")
            else:
                self._notify_finished(on_finished, measurements, "Calibration")

        thread = threading.Thread(
            target=worker,
            daemon=True,
        )

        self._sweep_thread = thread
        thread.start()
