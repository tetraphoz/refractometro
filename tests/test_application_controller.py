from __future__ import annotations

import threading

import pytest

from app.application import ApplicationController
from app.operation_state import OperationStatus


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
