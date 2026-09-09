from pathlib import Path

import matplotlib.pyplot as plt

from app.models import RunRecord


def export_run_plot_png(run: RunRecord) -> bool:
    """
    Export a run plot as a PNG file next to the run's CSV file.

    Returns:
        True if the image was exported successfully, False otherwise.
    """
    if not run.measurements or not run.filename:
        return False

    csv_path = Path(run.filename)
    png_path = csv_path.with_suffix(".png")

    x = [p.position_mm for p in run.measurements]
    y = [p.voltage_v for p in run.measurements]

    fig, ax = plt.subplots(figsize=(10, 6))

    ax.plot(x, y, linewidth=1)

    if run.peaks:
        primary_peak = run.peaks[0]
        ax.plot(
            primary_peak.position_mm,
            primary_peak.voltage_v,
            "ro",
            markersize=8,
        )

        x_min, x_max = min(x), max(x)
        peak_fraction = (
            (primary_peak.position_mm - x_min) / (x_max - x_min)
            if x_max > x_min
            else 0.5
        )
        annotation_x = 0.08 if peak_fraction > 0.55 else 0.72

        ax.annotate(
            (
                f"Máximo\n"
                f"{primary_peak.voltage_v:.4f} V\n"
                f"{primary_peak.position_mm:.4f} mm"
            ),
            xy=(primary_peak.position_mm, primary_peak.voltage_v),
            xycoords="data",
            xytext=(annotation_x, 0.86),
            textcoords="axes fraction",
            ha="left",
            va="top",
            bbox={
                "boxstyle": "round,pad=0.3",
                "facecolor": "white",
                "edgecolor": "0.7",
                "alpha": 0.9,
            },
            arrowprops={"arrowstyle": "->"},
        )

    ax.set_xlabel("Posición del actuador (mm)")
    ax.set_ylabel("Voltaje (V)")
    ax.set_title("Voltaje vs Posición")
    ax.grid(True)

    fig.tight_layout()

    try:
        png_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(png_path, dpi=300, format="png")
        return True
    finally:
        plt.close(fig)
