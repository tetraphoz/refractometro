from __future__ import annotations

import csv
import os

from experiments.voltage_sweep import MeasurementPoint

def save_measurements_csv(
        filename: str,
        measurements: list[MeasurementPoint],
        metadata: dict | None = None,
) -> None:

    # Writes optional metadata as commented lines at top,
    # then a header and measurement rows.
    with open(
        filename,
        "w",
        newline="",
        encoding="utf-8",
    ) as file:

        writer = csv.writer(file)

        if metadata:
            for key, value in metadata.items():
                writer.writerow([f"# {key}: {value}"])

        writer.writerow(
            [
                "position_mm",
                "voltage_v",
            ]
        )

        for measurement in measurements:
            writer.writerow(
                [
                    measurement.position_mm,
                    measurement.voltage_v,
                ]
            )


def import_measurements_csv(
        filename: str,
) -> tuple[list[MeasurementPoint], dict]:
    """
    Reads a CSV possibly containing commented metadata lines at top
    (format: "# key: value"). Returns (measurements, metadata).
    """

    measurements: list[MeasurementPoint] = []
    metadata: dict = {}

    with open(
        filename,
        "r",
        newline="",
        encoding="utf-8",
    ) as file:

        reader = csv.reader(file)

        # First read possible metadata comment lines
        # (they start with '# ' in our writer).
        rows = list(reader)

    # Separate metadata lines (starting with '# ') from data.
    data_rows = []
    for row in rows:
        if not row:
            continue
        first = row[0]
        if isinstance(first, str) and first.startswith("#"):
            # row like ["# key: value"] or ["# key:"," value"]
            joined = ",".join(row)
            # remove leading '#'
            stripped = joined.lstrip("# ").strip()
            if ":" in stripped:
                key, val = stripped.split(":", 1)
                metadata[key.strip()] = val.strip()
            continue
        data_rows.append(row)

    if not data_rows:
        # empty or only-comment file; provide sensible defaults derived from filename
        basename = (
            os.path.splitext(os.path.basename(filename))[0]
            if filename
            else ""
        )
        if not metadata.get("label"):
            metadata["label"] = basename
        metadata.setdefault("kind", "imported")
        metadata.setdefault("number_of_points", "0")
        metadata.setdefault("start_position_mm", "")
        metadata.setdefault("end_position_mm", "")
        metadata.setdefault("stabilization_time_s", "")
        return measurements, metadata

    # First non-metadata row is expected to be header; find it
    header = data_rows[0]
    # Expect header contains "position_mm" and "voltage_v"
    # Remaining rows are numeric data
    for row in data_rows[1:]:
        if len(row) < 2:
            continue
        try:
            pos = float(row[0])
            volt = float(row[1])
        except Exception:
            continue
        measurements.append(MeasurementPoint(position_mm=pos, voltage_v=volt))

    # Provide sensible metadata defaults if missing so callers (GUI) can
    # display a friendly label and useful fields without re-computing them.
    basename = (
        os.path.splitext(os.path.basename(filename))[0]
        if filename
        else ""
    )
    if not metadata.get("label"):
        metadata["label"] = basename
    metadata.setdefault("kind", "imported")
    metadata.setdefault("number_of_points", str(len(measurements)))

    if measurements:
        positions = [m.position_mm for m in measurements]
        metadata.setdefault("start_position_mm", str(min(positions)))
        metadata.setdefault("end_position_mm", str(max(positions)))
    else:
        metadata.setdefault("start_position_mm", "")
        metadata.setdefault("end_position_mm", "")

    metadata.setdefault("stabilization_time_s", "")

    return measurements, metadata
