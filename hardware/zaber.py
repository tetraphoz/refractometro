from __future__ import annotations

from zaber_motion import Library, Units
from zaber_motion.ascii import Connection


class ZaberMotor:
    """
    Control directo de un motor Zaber
    usando zaber_motion ASCII.
    """

    def __init__(self):
        self._connection = None
        self._axis = None

    @property
    def connected(self) -> bool:
        return self._axis is not None

    def connect(
        self,
        port: str,
    ) -> None:
        Library.enable_device_db_store()

        self._connection = Connection.open_serial_port(port)

        device = self._connection.detect_devices()[0]

        self._axis = device.get_axis(1)

    def disconnect(self) -> None:
        if self._connection:
            self._connection.close()

        self._connection = None
        self._axis = None

    def move_absolute(
        self,
        position_mm: float,
    ) -> None:
        if not self.connected:
            raise RuntimeError("Motor Zaber no conectado")

        self._axis.move_absolute(
            position_mm,
            Units.LENGTH_MILLIMETRES,
        )
