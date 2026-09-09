from app.models import RunRecord
from experiments.voltage_sweep import MeasurementPoint
from storage.image_plot import export_run_plot_png


def test_export_run_plot_png_writes_image_next_to_csv(tmp_path):
    run = RunRecord(
        id=1,
        kind="barrido",
        label="Barrido #1",
        curve_tag="curve_1",
        filename=str(tmp_path / "run.csv"),
        measurements=[
            MeasurementPoint(position_mm=0.0, voltage_v=0.1),
            MeasurementPoint(position_mm=1.0, voltage_v=0.2),
        ],
    )

    assert export_run_plot_png(run)
    assert (tmp_path / "run.png").exists()


def test_export_run_plot_png_rejects_run_without_measurements(tmp_path):
    run = RunRecord(
        id=1,
        kind="barrido",
        label="Barrido #1",
        curve_tag="curve_1",
        filename=str(tmp_path / "run.csv"),
    )

    assert not export_run_plot_png(run)
