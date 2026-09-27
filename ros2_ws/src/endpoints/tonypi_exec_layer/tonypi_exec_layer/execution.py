"""构造第一版确定性的 TonyPi 动作计划。"""

from dataclasses import dataclass

from .contract import ACTION_GROUPS


@dataclass(frozen=True)
class ExecutionStep:
    """一个目标 Tag 及其对应的 TonyPi 动作组。"""

    progress: float
    tag_id: int
    next_tag: int
    action_group: str


def execution_steps(target_tags: list[int]) -> tuple[ExecutionStep, ...]:
    """为已经校验过的目标 Tag 构造有序动作步骤。"""
    step_count = len(target_tags)
    return tuple(
        ExecutionStep(
            progress=(index + 1) / step_count,
            tag_id=tag_id,
            next_tag=target_tags[index + 1] if index + 1 < step_count else -1,
            action_group=ACTION_GROUPS[tag_id],
        )
        for index, tag_id in enumerate(target_tags)
    )
