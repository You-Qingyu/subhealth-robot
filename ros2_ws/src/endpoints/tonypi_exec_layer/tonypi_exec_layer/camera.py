"""TonyPi 导航使用的实时相机观测。"""

from dataclasses import dataclass
from pathlib import Path
import time

import cv2
import numpy as np

from .tag_pose import CALIBRATED_IMAGE_SIZE, TagPose, TagPoseEstimator


class CameraObservationError(RuntimeError):
    """相机无法提供符合标定约束的图像时抛出。"""


@dataclass(frozen=True)
class FrameObservation:
    """单帧中所有 Tag 的位姿和该帧采集时间。"""

    poses: dict[int, TagPose]
    captured_at_monotonic: float
    image: np.ndarray


class TagCamera:
    """持有一次导航任务的 V4L2 相机，每次读取一帧新图像。"""

    def __init__(
        self,
        device: str,
        calibration_path: Path,
        tag_family: str,
        warmup_frames: int = 10,
    ) -> None:
        if warmup_frames < 0:
            raise ValueError('warmup_frames must not be negative')
        self._device = device
        self._warmup_frames = warmup_frames
        self._estimator = TagPoseEstimator(calibration_path, tag_family)
        self._camera = None

    def __enter__(self) -> 'TagCamera':
        camera = cv2.VideoCapture(self._device, cv2.CAP_V4L2)
        if not camera.isOpened():
            camera.release()
            raise CameraObservationError(f'无法打开摄像头: {self._device}')
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, CALIBRATED_IMAGE_SIZE[0])
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, CALIBRATED_IMAGE_SIZE[1])
        self._camera = camera
        try:
            self._discard_warmup_frames()
        except Exception:
            self.close()
            raise
        return self

    def __exit__(self, _exception_type, _exception, _traceback) -> None:
        self.close()

    def close(self) -> None:
        if self._camera is not None:
            self._camera.release()
            self._camera = None

    def observe_tags(self) -> FrameObservation:
        """读取一帧新图像并估计其中所有 Tag。"""
        if self._camera is None:
            raise CameraObservationError('相机尚未打开')
        success, image = self._camera.read()
        if not success or image is None:
            raise CameraObservationError(f'无法从摄像头读取图像: {self._device}')
        if (image.shape[1], image.shape[0]) != CALIBRATED_IMAGE_SIZE:
            raise CameraObservationError(
                '摄像头输出尺寸与 640x480 相机标定不一致'
            )
        captured_at = time.monotonic()
        return FrameObservation(self._estimator.estimate_all(image), captured_at, image)

    def _discard_warmup_frames(self) -> None:
        for _ in range(self._warmup_frames):
            success, _image = self._camera.read()
            if not success:
                raise CameraObservationError(
                    f'无法从摄像头读取预热图像: {self._device}'
                )
