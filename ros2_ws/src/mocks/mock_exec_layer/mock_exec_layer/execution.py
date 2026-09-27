"""Pure deterministic execution behavior for GoToTag routes."""

from dataclasses import dataclass

from .contract import UnsupportedPrimitive


@dataclass(frozen=True)
class ExecutionStep:
    progress: float
    phase: str
    details: dict


def execution_steps(primitive: str, payload: dict) -> tuple[ExecutionStep, ...]:
    """Build deterministic feedback steps for one validated task payload."""
    if primitive == 'go_to_tag':
        target_tags = payload['target_tags']
        route_length = len(target_tags)
        return tuple(
            ExecutionStep(
                progress=(index + 1) / route_length,
                phase='moving_to_tag',
                details={
                    'current_tag': target_tags[index],
                    'next_tag': (
                        target_tags[index + 1]
                        if index + 1 < route_length
                        else -1
                    ),
                },
            )
            for index in range(route_length)
        )

    raise UnsupportedPrimitive(primitive)


def validate_step_delay(value: float) -> float:
    """Validate and return the configured deterministic step delay."""
    if value < 0.0:
        raise ValueError(f'step_delay_s must be non-negative, got {value}')
    return value
