from __future__ import annotations

import threading

import pytest

from app.application import ApplicationController
from app.operation_state import OperationStatus
from hardware.simulated_motor import SimulatedMotor
from hardware.simulated_sensor import SimulatedESP32Sensor


class RecordingMotor:
    def __init__(self) -> None:
        self.positions: list[float] = []

    def move_absolute(self, position_mm: float) -> None:
        self.positions.append(position_mm)

    def stop(self) -> None:
        pass


class FailingSensor:
    def read_voltage(self) -> float:
        raise RuntimeError("sensor failed")


class ConstantSensor:
    def read_voltage(self) -> float:
        return 0.5


class CleanupFailingMotor(RecordingMotor):
    def move_absolute(self, position_mm: float) -> None:
        super().move_absolute(position_mm)

        if len(self.positions) > 1:
            raise ValueError("cleanup failed")


def test_voltage_sweep_notifies_error_and_clears_running(tmp_path):
    controller = ApplicationController(
        motor=RecordingMotor(),
        sensor=FailingSensor(),
    )
    error_event = threading.Event()
    finished_event = threading.Event()
    errors: list[Exception] = []
    running_states: list[bool] = []

    def on_error(exc: Exception) -> None:
        running_states.append(controller.sweep_running)
        errors.append(exc)
        error_event.set()

    controller.start_voltage_sweep(
        start_position_mm=0.0,
        end_position_mm=1.0,
        number_of_points=2,
        stabilization_time_s=0.0,
        filename=str(tmp_path / "failed.csv"),
        on_finished=lambda _peaks: finished_event.set(),
        on_error=on_error,
    )

    assert error_event.wait(timeout=1.0)
    assert controller._sweep_thread is not None
    controller._sweep_thread.join(timeout=1.0)

    assert not controller.sweep_running
    assert not finished_event.is_set()
    assert running_states == [False]
    assert len(errors) == 1
    assert str(errors[0]) == "sensor failed"


def test_voltage_batch_persists_each_raw_run(tmp_path):
    controller = ApplicationController(
        motor=RecordingMotor(),
        sensor=ConstantSensor(),
    )
    finished_event = threading.Event()
    callback_states: list[bool] = []
    results: list[list] = []

    def on_finished(batch):
        callback_states.append(controller.sweep_running)
        results.extend(batch)
        finished_event.set()

    controller.start_voltage_batch(
        start_position_mm=0.0,
        end_position_mm=1.0,
        number_of_points=2,
        stabilization_time_s=0.0,
        number_of_runs=2,
        filename_factory=lambda run_number: str(tmp_path / f"raw-{run_number}.csv"),
        on_finished=on_finished,
    )

    assert finished_event.wait(timeout=1.0)
    assert controller._sweep_thread is not None
    controller._sweep_thread.join(timeout=1.0)

    assert not controller.sweep_running
    assert callback_states == [False]
    assert len(results) == 2
    assert (tmp_path / "raw-1.csv").exists()
    assert (tmp_path / "raw-2.csv").exists()


def test_test_hardware_acquires_a_voltage_batch(tmp_path):
    motor = SimulatedMotor()
    sensor = SimulatedESP32Sensor(motor)
    motor.connect()
    sensor.connect()
    controller = ApplicationController(motor=motor, sensor=sensor)
    finished_event = threading.Event()
    results: list[list] = []

    controller.start_voltage_batch(
        start_position_mm=0.0,
        end_position_mm=1.0,
        number_of_points=2,
        stabilization_time_s=0.0,
        number_of_runs=2,
        filename_factory=lambda run_number: str(tmp_path / f"sim-{run_number}.csv"),
        on_finished=lambda batch: (results.extend(batch), finished_event.set()),
    )

    assert finished_event.wait(timeout=2.0)
    assert controller._sweep_thread is not None
    controller._sweep_thread.join(timeout=1.0)
    assert len(results) == 2
    assert all(len(run) == 2 for run in results)
    assert (tmp_path / "sim-1.csv").exists()
    assert (tmp_path / "sim-2.csv").exists()


def test_voltage_batch_cancellation_keeps_completed_raw_runs(tmp_path):
    controller = ApplicationController(
        motor=RecordingMotor(),
        sensor=ConstantSensor(),
    )
    cancelled_event = threading.Event()
    partial_results: list[list] = []

    def on_run_finished(_run_number, _measurements):
        assert controller.cancel_operation()

    def on_cancelled(batch):
        partial_results.extend(batch)
        cancelled_event.set()

    controller.start_voltage_batch(
        start_position_mm=0.0,
        end_position_mm=1.0,
        number_of_points=2,
        stabilization_time_s=0.0,
        number_of_runs=3,
        filename_factory=lambda run_number: str(tmp_path / f"raw-{run_number}.csv"),
        on_run_finished=on_run_finished,
        on_cancelled=on_cancelled,
    )

    assert cancelled_event.wait(timeout=1.0)
    assert controller._sweep_thread is not None
    controller._sweep_thread.join(timeout=1.0)

    assert not controller.sweep_running
    assert len(partial_results) == 1
    assert (tmp_path / "raw-1.csv").exists()
    assert not (tmp_path / "raw-2.csv").exists()


def test_voltage_sweep_finished_callback_runs_after_state_is_cleared(tmp_path):
    controller = ApplicationController(
        motor=RecordingMotor(),
        sensor=ConstantSensor(),
    )
    finished_event = threading.Event()
    running_states: list[bool] = []

    def on_finished(_peaks):
        running_states.append(controller.sweep_running)
        finished_event.set()

    controller.start_voltage_sweep(
        start_position_mm=0.0,
        end_position_mm=1.0,
        number_of_points=2,
        stabilization_time_s=0.0,
        filename=str(tmp_path / "finished.csv"),
        on_finished=on_finished,
    )

    assert finished_event.wait(timeout=1.0)
    assert controller._sweep_thread is not None
    controller._sweep_thread.join(timeout=1.0)

    assert not controller.sweep_running
    assert running_states == [False]


def test_voltage_sweep_clears_running_when_return_to_start_fails(tmp_path):
    controller = ApplicationController(
        motor=CleanupFailingMotor(),
        sensor=FailingSensor(),
    )
    error_event = threading.Event()

    controller.start_voltage_sweep(
        start_position_mm=0.0,
        end_position_mm=1.0,
        number_of_points=2,
        stabilization_time_s=0.0,
        filename=str(tmp_path / "cleanup_failed.csv"),
        on_error=lambda _exc: error_event.set(),
    )

    assert error_event.wait(timeout=1.0)
    assert controller._sweep_thread is not None
    controller._sweep_thread.join(timeout=1.0)

    assert not controller.sweep_running


def test_calibration_notifies_error_and_clears_running():
    controller = ApplicationController(
        motor=RecordingMotor(),
        sensor=FailingSensor(),
    )
    error_event = threading.Event()
    errors: list[Exception] = []
    running_states: list[bool] = []

    def on_error(exc: Exception) -> None:
        running_states.append(controller.sweep_running)
        errors.append(exc)
        error_event.set()

    controller.start_calibration(
        start_position_mm=0.0,
        end_position_mm=1.0,
        number_of_points=2,
        stabilization_time_s=0.0,
        on_error=on_error,
    )

    assert error_event.wait(timeout=1.0)
    assert controller._sweep_thread is not None
    controller._sweep_thread.join(timeout=1.0)

    assert not controller.sweep_running
    assert running_states == [False]
    assert len(errors) == 1
    assert str(errors[0]) == "sensor failed"


def test_voltage_sweep_can_be_cancelled_and_returns_to_start(tmp_path):
    controller = ApplicationController(
        motor=RecordingMotor(),
        sensor=ConstantSensor(),
    )
    cancelled_event = threading.Event()
    finished_event = threading.Event()
    errors: list[Exception] = []
    partial_results = []

    def on_cancelled(measurements):
        partial_results.extend(measurements)
        cancelled_event.set()

    controller.start_voltage_sweep(
        start_position_mm=0.0,
        end_position_mm=10.0,
        number_of_points=100,
        stabilization_time_s=0.1,
        filename=str(tmp_path / "cancelled.csv"),
        on_finished=lambda _peaks: finished_event.set(),
        on_error=errors.append,
        on_cancelled=on_cancelled,
    )

    assert controller.operation_status is OperationStatus.RUNNING
    assert controller.cancel_operation()
    assert controller.operation_status is OperationStatus.CANCELLING
    assert controller.cancel_operation() is False
    assert cancelled_event.wait(timeout=1.0)
    assert controller._sweep_thread is not None
    controller._sweep_thread.join(timeout=1.0)

    assert controller.operation_status is OperationStatus.IDLE
    assert not controller.sweep_running
    assert not finished_event.is_set()
    assert errors == []
    assert controller.motor.positions[-1] == 0.0
    assert len(partial_results) < 100


def test_cancel_operation_returns_false_when_idle():
    controller = ApplicationController(
        motor=RecordingMotor(),
        sensor=ConstantSensor(),
    )

    assert not controller.cancel_operation()


def test_controller_rejects_overlapping_operations(tmp_path):
    controller = ApplicationController(
        motor=RecordingMotor(),
        sensor=FailingSensor(),
    )
    controller._operation_status = OperationStatus.RUNNING

    with pytest.raises(RuntimeError, match="operación en curso"):
        controller.start_voltage_sweep(
            start_position_mm=0.0,
            end_position_mm=1.0,
            number_of_points=2,
            stabilization_time_s=0.0,
            filename=str(tmp_path / "overlap.csv"),
        )
