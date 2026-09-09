from __future__ import annotations

import pytest

from hardware.simulated_motor import SimulatedMotor
from hardware.simulated_sensor import SimulatedESP32Sensor


def test_simulated_sensor_supports_deterministic_peaks_drift_and_outliers():
    motor = SimulatedMotor(latency_per_mm_s=0)
    motor.connect()
    motor.move_absolute(2.0)
    sensor = SimulatedESP32Sensor(
        motor,
        baseline_voltage_v=1.0,
        peaks=[(2.0, 3.0, 1.0)],
        noise_amplitude_v=0,
        drift_per_read_v=0.1,
        outlier_offsets_v={2: 0.5},
    )
    sensor.connect()

    assert sensor.read_voltage() == pytest.approx(4.0)
    assert sensor.read_voltage() == pytest.approx(4.6)


def test_simulated_sensor_can_fail_on_configured_read():
    motor = SimulatedMotor(latency_per_mm_s=0)
    motor.connect()
    sensor = SimulatedESP32Sensor(
        motor,
        noise_amplitude_v=0,
        failing_read_numbers=frozenset({2}),
    )
    sensor.connect()

    sensor.read_voltage()
    with pytest.raises(RuntimeError, match="Fallo simulado del sensor"):
        sensor.read_voltage()


def test_simulated_motor_can_fail_on_configured_move():
    motor = SimulatedMotor(
        latency_per_mm_s=0,
        failing_move_numbers=frozenset({2}),
    )
    motor.connect()

    motor.move_absolute(1.0)
    with pytest.raises(RuntimeError, match="Fallo simulado del motor"):
        motor.move_absolute(2.0)
