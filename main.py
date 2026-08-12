from __future__ import annotations

import argparse

from app.application import ApplicationController
from gui.interface import ControlInterface
from hardware.esp32 import ESP32Sensor
from hardware.zaber import ZaberMotor
from hardware.simulated_motor import SimulatedMotor
from hardware.simulated_sensor import SimulatedESP32Sensor


def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description="Refractómetro"
    )

    parser.add_argument(
        "--test",
        action="store_true",
        help=(
            "Usar hardware simulado en vez de conectar "
            "al ESP32 y al motor Zaber reales."
        ),
    )

    return parser.parse_args()


def main() -> None:
    """
    Punto de entrada de la aplicación.
    """

    args = parse_args()

    # Crear hardware
    if args.test:
        motor = SimulatedMotor()
        sensor = SimulatedESP32Sensor(motor)
    else:
        motor = ZaberMotor()
        sensor = ESP32Sensor()

    # Inyectar hardware al controlador
    controller = ApplicationController(
        motor=motor,
        sensor=sensor,
    )

    # Crear interfaz gráfica
    interface = ControlInterface(controller=controller,)

    # Ejecutar aplicación
    interface.build()
    interface.run()
    interface.close()


if __name__ == "__main__":
    main()
