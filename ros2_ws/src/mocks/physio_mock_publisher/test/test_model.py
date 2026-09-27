import random
from dataclasses import FrozenInstanceError

import pytest

from physio_mock_publisher.model import SENSOR_SPECS, SensorSpec, sample_value


def test_all_rfc_sensor_types_are_present():
    assert {spec.data_type for spec in SENSOR_SPECS} == {
        'spo2',
        'heart_rate',
        'systolic_mmhg',
        'diastolic_mmhg',
        'body_temp_c',
        'respiratory_rate',
    }


def test_anomaly_only_forces_spo2_low():
    rng = random.Random(0)
    spo2 = next(spec for spec in SENSOR_SPECS if spec.data_type == 'spo2')
    assert sample_value(spo2, 'anomaly', rng) < 90.0


def test_unknown_scenario_is_rejected():
    with pytest.raises(ValueError):
        sample_value(SENSOR_SPECS[0], 'invalid', random.Random(0))


def test_normal_value_uses_base_noise_and_rounds_to_two_decimals():
    spec = SensorSpec('mock_test', 'heart_rate', 70.0, 2.0)
    assert sample_value(spec, 'normal', random.Random(0)) == 71.38


def test_anomaly_keeps_non_spo2_sensor_on_normal_model():
    spec = SensorSpec('mock_test', 'heart_rate', 70.0, 2.0)
    assert sample_value(spec, 'anomaly', random.Random(0)) == 71.38


def test_sensor_spec_is_immutable():
    spec = SensorSpec('mock_test', 'heart_rate', 70.0, 2.0)
    with pytest.raises(FrozenInstanceError):
        spec.base = 80.0
