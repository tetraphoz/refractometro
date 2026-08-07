from __future__ import annotations

import random
import math


class SimulatedESP32Sensor:
    """
    Simula una lectura de voltaje.

    Genera una curva tipo:
        voltaje vs posición

    útil para probar barridos.
    """


    def __init__(
        self,
        motor,
    ):

        self.motor = motor
        self.connected = False



    def connect(
        self,
        port="SIM",
        baud_rate=115200,
    ):

        self.connected = True



    def disconnect(self):

        self.connected = False



    def read_voltage(self) -> float:

        if not self.connected:
            raise RuntimeError(
                "Sensor simulado desconectado"
            )


        x = self.motor.position_mm


        # Pico alrededor de 6 mm

        signal = (
            2.5
            *
            math.exp(
                -(
                    (x - 6.0) ** 2
                )
                /
                2
            )
        )


        noise = random.uniform(
            -0.03,
            0.03,
        )


        offset = 0.2


        return (
            offset
            +
            signal
            +
            noise
        )
