from unittest.mock import Mock

import pytest

from hardware.esp32 import ESP32Sensor


@pytest.fixture
def serial_sensor(monkeypatch):
    port = Mock(is_open=True)
    monkeypatch.setattr("hardware.esp32.serial.Serial", lambda **kwargs: port)
    sensor = ESP32Sensor()
    sensor.connect("simulated")
    return sensor, port


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (b"", TimeoutError),
        (b"abc", ValueError),
        (b"1\xff2", ValueError),
        (b"NaN\n", ValueError),
        (b"inf", ValueError),
    ],
)
def test_invalid_reading_is_not_recorded_as_voltage(serial_sensor, response, error):
    sensor, port = serial_sensor
    port.readline.return_value = response
    with pytest.raises(error):
        sensor.read_voltage()


@pytest.mark.parametrize(("response", "value"), [(b"0\r\n", 0.0), (b"1.25\n", 1.25)])
def test_valid_voltage_including_zero_is_preserved(serial_sensor, response, value):
    sensor, port = serial_sensor
    port.readline.return_value = response
    assert sensor.read_voltage() == value
    port.write.assert_called_once_with(b"R")
