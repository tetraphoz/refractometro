from __future__ import annotations

from zaber_motion import Library, Units
from zaber_motion.ascii import Connection
from zaber_motion.movement import DefaultMotionUnits, Moveable


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
        self.mm_moveable = Moveable.from_axis(
            device.get_axis(1), DefaultMotionUnits(position=Units.LENGTH_MILLIMETRES)
        )

    def disconnect(self) -> None:
        if self._connection:
            self._connection.close()

        self._connection = None
        self._axis = None
        self.mm_moveable = None

    def move_absolute(
        self,
        position_mm: float,
    ) -> None:
        if not self.connected:
            raise RuntimeError("Motor Zaber no conectado")

        self.mm_moveable.move_absolute(position_mm)

    def stop(self) -> None:
        if self.connected:
            self.mm_moveable.stop()
