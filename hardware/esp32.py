from __future__ import annotations

import serial


class ESP32Sensor:
    """
    Interface directa con un ESP32 usando pyserial.

    El ESP32 debe responder a:
        PC -> ESP32:  R

    Y devolver:
        ESP32 -> PC:  3.141
    """

    def __init__(self):
        self._serial: serial.Serial | None = None


    @property
    def connected(self) -> bool:
        return self._serial is not None and self._serial.is_open


    def connect(
        self,
        port: str,
        baud_rate: int = 115200,
    ) -> None:

        self._serial = serial.Serial(
            port=port,
            baudrate=baud_rate,
            timeout=1,
        )

        self._serial.reset_input_buffer()


    def disconnect(self) -> None:

        if self._serial:

            self._serial.close()

        self._serial = None


    def read_voltage(self) -> float:

        if not self.connected:
            raise RuntimeError(
                "ESP32 no conectado"
            )


        self._serial.write(b"R")


        response = (
            self._serial
            .readline()
            .decode(
                errors="ignore"
            )
            .strip()
        )


        return float(response)

