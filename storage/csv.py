from __future__ import annotations

import csv

from experiments.voltage_sweep import MeasurementPoint

def save_measurements_csv(
        filename: str,
        measurements: list[MeasurementPoint],
) -> None:

    with open(
        filename,
        "w",
        newline="",
        encoding="utf-8",
    ) as file:

        writer = csv.writer(file)

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
        measurements: list[MeasurementPoint],
) -> None:

    # TODO: Write import csv and implement in gui
    pass
