"""Exercise the real history widgets without a viewport or hardware."""

import dearpygui.dearpygui as dpg
import pytest

from app.application import ApplicationController
from app.models import RunStatus, SessionKind, SessionStatus
from app.run_repository import RunRepository
from experiments.voltage_sweep import BatchRunFailure, MeasurementPoint
from gui.interface import ControlInterface
from hardware.simulated_motor import SimulatedMotor
from hardware.simulated_sensor import SimulatedESP32Sensor


@pytest.fixture
def batch_ui(monkeypatch, tmp_path):
    motor = SimulatedMotor()
    controller = ApplicationController(motor, SimulatedESP32Sensor(motor))
    repository = RunRepository(":memory:")
    ui = ControlInterface(controller, repository)
    monkeypatch.setattr(dpg, "setup_dearpygui", lambda: None)
    monkeypatch.setattr(dpg, "show_viewport", lambda: None)
    monkeypatch.setattr(ui, "update_ports", lambda: None)
    monkeypatch.setattr(ui, "RUNS_DIR", str(tmp_path))
    # Drive worker callbacks explicitly so the test can interact mid-batch.
    monkeypatch.setattr(controller, "start_voltage_batch", lambda **kwargs: None)
    try:
        ui.build()
        dpg.set_value("cantidad_barridos", 2)
        ui.start_batch(SessionKind.SAMPLE)
        yield ui, repository
    finally:
        dpg.destroy_context()
        repository.close()


def test_live_batch_rows_keep_membership_and_exclusions(batch_ui):
    ui, repository = batch_ui
    (session,) = repository.list_sessions()
    first, second = repository.list_runs_for_session(session.uid)
    assert (
        dpg.get_item_parent(f"historial_fila_{first.id}")
        == f"hist_session_runs_{session.uid}"
    )

    ui.clear_history()
    ui.on_click_delete_run(None, None, second.id)
    assert repository.get_session(session.uid).run_uids == [first.uid, second.uid]

    points = [MeasurementPoint(0.0, 0.1), MeasurementPoint(1.0, 0.3)]
    ui.batch_run_finished(1, points)
    action = f"hist_excluir_{first.id}_1"
    dpg.get_item_callback(action)(action, None, dpg.get_item_user_data(action))
    dpg.set_value("razon_exclusion", "Ruido")
    ui.confirm_run_exclusion()
    ui.batch_cancelled([points])

    restored = repository.get_session(session.uid)
    assert restored.excluded_runs == {first.uid: "Ruido"}
    assert restored.status is SessionStatus.CANCELLED
    assert repository.get(first.id).measurements == points
    assert repository.get(second.id).status is RunStatus.CANCELLED


def test_batch_with_no_successful_sweep_is_not_completed(batch_ui):
    ui, repository = batch_ui
    for number in (1, 2):
        ui.batch_run_failed(BatchRunFailure(number, 1, ValueError("sensor")))
    ui.batch_finished([])
    (session,) = repository.list_sessions()
    assert session.status is SessionStatus.FAILED
    for run in repository.list_runs():
        assert run.failure_reason == "sensor"
        for suffix in ["", "_1", "_2", "_3", "_4"]:
            assert dpg.is_item_enabled(f"hist_eliminar_{run.id}{suffix}")
            assert not dpg.is_item_enabled(f"hist_guardar_{run.id}{suffix}")
