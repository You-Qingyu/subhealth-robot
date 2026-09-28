"""从离线图像计算指定 AprilTag 相对相机的位姿。"""

from dataclasses import dataclass
import math
from pathlib import Path

import cv2
import numpy as np


TAG_SIZE_M = 0.10
CALIBRATED_IMAGE_SIZE = (640, 480)
TAG_FAMILIES = {
    '16h5': cv2.aruco.DICT_APRILTAG_16h5,
    '25h9': cv2.aruco.DICT_APRILTAG_25h9,
    '36h10': cv2.aruco.DICT_APRILTAG_36h10,
    '36h11': cv2.aruco.DICT_APRILTAG_36h11,
}


@dataclass(frozen=True)
class TagTransform:
    """Tag 到相机的刚体变换，矩阵方向为 ``camera <- tag``。"""

    rotation_c_tag: tuple[tuple[float, float, float], ...]
    translation_c_tag: tuple[float, float, float]


@dataclass(frozen=True)
class TagPose:
    """指定 Tag 在相机坐标系中的一次位姿观测，距离单位为米。"""

    tag_id: int
    distance_m: float
    forward_m: float
    lateral_m: float
    vertical_m: float
    bearing_deg: float
    normal_bearing_deg: float
    facing_error_deg: float
    reprojection_error_px: float
    image_margin_px: float
    transform: TagTransform


class TagPoseEstimator:
    """使用既有相机标定和真实 Tag 边长估计位姿。"""

    def __init__(self, calibration_path: Path, tag_family: str) -> None:
        if tag_family not in TAG_FAMILIES:
            raise ValueError(f'不支持的 AprilTag family: {tag_family}')
        with np.load(calibration_path, allow_pickle=False) as calibration:
            self._camera_matrix = calibration['mtx_array']
            self._distortion = calibration['dist_array']
        if self._camera_matrix.shape != (3, 3) or self._distortion.size < 4:
            raise ValueError('相机标定文件缺少有效的内参或畸变参数')
        self._dictionary = cv2.aruco.getPredefinedDictionary(TAG_FAMILIES[tag_family])
        half_size = TAG_SIZE_M / 2
        self._tag_corners = np.array(
            [
                [-half_size, half_size, 0],
                [half_size, half_size, 0],
                [half_size, -half_size, 0],
                [-half_size, -half_size, 0],
            ],
            dtype=np.float32,
        )

    def estimate(self, image: np.ndarray, target_id: int) -> TagPose | None:
        """估计目标 Tag 位姿；不在画面中时返回 `None`。

        只接受与现有 640×480 标定一致的原始图像；不对图像缩放或二次去畸变。
        """
        corners = self._detect_corners(image)
        if target_id not in corners:
            return None
        return self._estimate_pose(target_id, corners[target_id])

    def estimate_all(self, image: np.ndarray) -> dict[int, TagPose]:
        """在同一原图中估计所有检出的 Tag，按 ID 返回。"""
        return {
            tag_id: self._estimate_pose(tag_id, corners)
            for tag_id, corners in self._detect_corners(image).items()
        }

    def _detect_corners(self, image: np.ndarray) -> dict[int, np.ndarray]:
        if (image.shape[1], image.shape[0]) != CALIBRATED_IMAGE_SIZE:
            raise ValueError('图像尺寸与 640x480 相机标定不一致')
        grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = cv2.aruco.detectMarkers(grayscale, self._dictionary)
        if ids is None:
            return {}
        found = {}
        for detected_id, image_corners in zip(ids.flatten(), corners):
            tag_id = int(detected_id)
            if tag_id in found:
                raise ValueError(f'同一画面中出现多个 Tag {tag_id}，无法确定目标')
            found[tag_id] = image_corners.reshape(4, 2)
        return found

    def _estimate_pose(self, tag_id: int, image_corners: np.ndarray) -> TagPose:
        success, rotation, translation = cv2.solvePnP(
            self._tag_corners,
            image_corners,
            self._camera_matrix,
            self._distortion,
            flags=cv2.SOLVEPNP_IPPE_SQUARE,
        )
        if not success:
            raise ValueError(f'无法估计 Tag {tag_id} 的位姿')
        x, y, z = translation.flatten()
        distance = float(np.linalg.norm(translation))
        if not np.isfinite(distance) or z <= 0:
            raise ValueError(f'Tag {tag_id} 的位姿无效')
        matrix, _ = cv2.Rodrigues(rotation)
        normal = matrix[:, 2]
        translation_vector = translation.flatten()
        normal_toward_tag = normal.copy()
        if float(np.dot(normal_toward_tag, translation_vector)) < 0:
            normal_toward_tag = -normal_toward_tag
        facing_cosine = abs(float(np.dot(normal, translation_vector) / distance))
        projected, _ = cv2.projectPoints(
            self._tag_corners, rotation, translation,
            self._camera_matrix, self._distortion,
        )
        projected_corners = projected.reshape(4, 2)
        error = np.linalg.norm(projected_corners - image_corners, axis=1)
        image_width, image_height = CALIBRATED_IMAGE_SIZE
        image_margin = min(
            float(projected_corners[:, 0].min()),
            float(image_width - projected_corners[:, 0].max()),
            float(projected_corners[:, 1].min()),
            float(image_height - projected_corners[:, 1].max()),
        )
        return TagPose(
            tag_id=tag_id,
            distance_m=distance,
            forward_m=float(z),
            lateral_m=float(x),
            vertical_m=float(y),
            bearing_deg=math.degrees(math.atan2(x, z)),
            normal_bearing_deg=math.degrees(
                math.atan2(normal_toward_tag[0], normal_toward_tag[2])
            ),
            facing_error_deg=math.degrees(math.acos(max(-1.0, min(1.0, facing_cosine)))),
            reprojection_error_px=float(np.mean(error)),
            image_margin_px=image_margin,
            transform=TagTransform(
                rotation_c_tag=tuple(
                    tuple(float(value) for value in row)
                    for row in matrix
                ),
                translation_c_tag=tuple(float(value) for value in translation_vector),
            ),
        )
