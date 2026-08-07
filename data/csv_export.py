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
            ["Posicion_mm", "Voltaje_V",]
        )


        for measurement in measurements:

            writer.writerow(
                [measurement.position_mm, measurement.voltage_v,]
            )
