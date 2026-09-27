"""Pure deterministic sample generation for physiological sensors."""

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class SensorSpec:
    data_src: str
    data_type: str
    base: float
    noise: float


SENSOR_SPECS = (
    SensorSpec('mock_spo2', 'spo2', 98.0, 1.0),
    SensorSpec('mock_heart_rate', 'heart_rate', 72.0, 3.0),
    SensorSpec('mock_bp_systolic', 'systolic_mmhg', 120.0, 5.0),
    SensorSpec('mock_bp_diastolic', 'diastolic_mmhg', 80.0, 3.0),
    SensorSpec('mock_body_temp', 'body_temp_c', 36.7, 0.2),
    SensorSpec('mock_respiratory_rate', 'respiratory_rate', 16.0, 2.0),
)


def sample_value(spec: SensorSpec, scenario: str, rng: random.Random) -> float:
    """Return one reproducible sample for a supported scenario."""
    if scenario not in {'normal', 'anomaly'}:
        raise ValueError(f'unsupported scenario: {scenario}')

    if scenario == 'anomaly' and spec.data_type == 'spo2':
        value = 85.0 + rng.uniform(-1.0, 1.0)
    else:
        value = spec.base + rng.uniform(-spec.noise, spec.noise)
    return round(value, 2)
