from __future__ import annotations

import time


class SimulatedMotor:
    """
    Motor virtual para desarrollo.

    Simula un eje Zaber sin hardware.
    """

    def __init__(self):

        self.position_mm = 0.0
        self.connected = False


    def connect(
        self,
        port: str = "SIM",
    ) -> None:

        self.connected = True


    def disconnect(self) -> None:

        self.connected = False



    def move_absolute(
        self,
        position_mm: float,
    ) -> None:

        if not self.connected:
            raise RuntimeError(
                "Motor simulado desconectado"
            )


        # Simula tiempo de movimiento
        distance = abs(
            position_mm - self.position_mm
        )

        time.sleep(
            min(
                distance * 0.05,
                0.2,
            )
        )


        self.position_mm = position_mm
