from __future__ import annotations

from app.application import ApplicationController
from gui.interface import ControlInterface
from hardware.esp32 import ESP32Sensor
from hardware.zaber import ZaberMotor
from hardware.simulated_motor import SimulatedMotor
from hardware.simulated_sensor import SimulatedESP32Sensor


SIMULATION = True

def main() -> None:
    """
    Punto de entrada de la aplicación.
    """

    # Crear hardware
    if SIMULATION:
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
    interface.construir()
    interface.ejecutar()
    interface.cerrar()



if __name__ == "__main__":
    main()
