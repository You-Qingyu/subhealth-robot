"""从两次 AprilTag 位姿观测计算相机的米制相对运动。"""

from dataclasses import dataclass
import math

import numpy as np

from .tag_pose import TagPose


@dataclass(frozen=True)
class TagMotion:
    """相机从 ``before`` 到 ``after`` 的相对运动。

    位移先在 Tag 坐标系中计算，再转换到动作前相机坐标系；因此它是
    相对于静止 Tag 的米制运动，而不是带世界原点的全局位移。
    """

    camera_origin_delta_in_tag_m: tuple[float, float, float]
    camera_displacement_in_before_camera_m: tuple[float, float, float]
    lateral_m: float
    vertical_m: float
    forward_m: float
    yaw_deg: float


def relative_tag_motion(before: TagPose, after: TagPose) -> TagMotion:
    """由两次同一 Tag 观测计算相机位移和水平旋转。"""
    if before.tag_id != after.tag_id:
        raise ValueError('before and after must observe the same Tag')

    before_rotation = _rotation(before)
    after_rotation = _rotation(after)
    before_translation = _translation(before)
    after_translation = _translation(after)

    before_camera_in_tag = -before_rotation.T @ before_translation
    after_camera_in_tag = -after_rotation.T @ after_translation
    camera_origin_delta_in_tag = after_camera_in_tag - before_camera_in_tag
    displacement_in_before_camera = before_rotation @ camera_origin_delta_in_tag

    after_camera_in_before_camera = before_rotation @ after_rotation.T
    yaw = math.degrees(
        math.atan2(
            float(after_camera_in_before_camera[0, 2]),
            float(after_camera_in_before_camera[2, 2]),
        )
    )
    _require_finite(
        camera_origin_delta_in_tag,
        displacement_in_before_camera,
        yaw,
    )

    lateral, vertical, forward = displacement_in_before_camera
    return TagMotion(
        camera_origin_delta_in_tag_m=_as_tuple(camera_origin_delta_in_tag),
        camera_displacement_in_before_camera_m=_as_tuple(
            displacement_in_before_camera
        ),
        lateral_m=float(lateral),
        vertical_m=float(vertical),
        forward_m=float(forward),
        yaw_deg=yaw,
    )


def _rotation(pose: TagPose) -> np.ndarray:
    return np.asarray(pose.transform.rotation_c_tag, dtype=float)


def _translation(pose: TagPose) -> np.ndarray:
    return np.asarray(pose.transform.translation_c_tag, dtype=float)


def _as_tuple(vector: np.ndarray) -> tuple[float, float, float]:
    return tuple(float(value) for value in vector)


def _require_finite(*values: np.ndarray | float) -> None:
    if not all(np.all(np.isfinite(value)) for value in values):
        raise ValueError('Tag motion contains non-finite values')
