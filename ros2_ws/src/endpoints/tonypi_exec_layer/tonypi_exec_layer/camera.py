"""TonyPi 导航使用的实时相机观测。"""

from dataclasses import dataclass
from pathlib import Path
import threading
import time
from typing import Callable

import cv2
import numpy as np

from .tag_pose import CALIBRATED_IMAGE_SIZE, TagPose, TagPoseEstimator


class CameraObservationError(RuntimeError):
    """相机无法提供符合标定约束的图像时抛出。"""


@dataclass(frozen=True)
class FrameObservation:
    """单帧中所有 Tag 的位姿；时间均为主机读取时间，不是相机曝光时间。"""

    poses: dict[int, TagPose]
    read_finished_at_monotonic: float
    image: np.ndarray
    read_started_at_monotonic: float
    capture_sequence: int
    skipped_frames: int


@dataclass(frozen=True)
class _CapturedFrame:
    sequence: int
    read_started_at_monotonic: float
    read_finished_at_monotonic: float
    image: np.ndarray


FRAME_WAIT_TIMEOUT_S = 3.0
FRAME_WAIT_POLL_S = 0.05
CAPTURE_STOP_TIMEOUT_S = 2.0


class TagCamera:
    """持续消费 V4L2 帧，导航只读取云台回正后的最新帧。"""

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
        self._condition = threading.Condition()
        self._stop = threading.Event()
        self._reader: threading.Thread | None = None
        self._latest: _CapturedFrame | None = None
        self._read_error: Exception | None = None
        self._last_observed_sequence = 0

    def __enter__(self) -> 'TagCamera':
        self._latest = None
        self._read_error = None
        self._last_observed_sequence = 0
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
        self._stop.clear()
        self._reader = threading.Thread(
            target=self._capture_frames,
            name='tonypi-camera-capture',
            daemon=True,
        )
        self._reader.start()
        return self

    def __exit__(self, _exception_type, _exception, _traceback) -> None:
        self.close()

    def close(self) -> None:
        self._stop.set()
        with self._condition:
            self._condition.notify_all()
        if self._reader is not None:
            self._reader.join(CAPTURE_STOP_TIMEOUT_S)
            if self._reader.is_alive():
                raise CameraObservationError('摄像头采集线程未能停止')
            self._reader = None
        if self._camera is not None:
            self._camera.release()
            self._camera = None

    def observe_tags(
        self,
        after_monotonic: float,
        check_interruption: Callable[[], None],
    ) -> FrameObservation:
        """等待云台回正后新开始读取的帧，并估计其中所有 Tag。"""
        if self._camera is None:
            raise CameraObservationError('相机尚未打开')
        frame = self._wait_for_frame(after_monotonic, check_interruption)
        image = frame.image.copy()
        if (image.shape[1], image.shape[0]) != CALIBRATED_IMAGE_SIZE:
            raise CameraObservationError(
                '摄像头输出尺寸与 640x480 相机标定不一致'
            )
        skipped = frame.sequence - self._last_observed_sequence - 1
        poses = self._estimator.estimate_all(image)
        self._last_observed_sequence = frame.sequence
        return FrameObservation(
            poses,
            frame.read_finished_at_monotonic,
            image,
            frame.read_started_at_monotonic,
            frame.sequence,
            skipped,
        )

    def _wait_for_frame(
        self,
        after_monotonic: float,
        check_interruption: Callable[[], None],
    ) -> _CapturedFrame:
        deadline = time.monotonic() + FRAME_WAIT_TIMEOUT_S
        while True:
            check_interruption()
            with self._condition:
                if self._read_error is not None:
                    raise CameraObservationError(
                        f'无法从摄像头读取图像: {self._device}'
                    ) from self._read_error
                frame = self._latest
                if (
                    frame is not None
                    and frame.sequence > self._last_observed_sequence
                    and frame.read_started_at_monotonic > after_monotonic
                ):
                    return frame
                if self._stop.is_set():
                    raise CameraObservationError('摄像头已关闭')
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise CameraObservationError('等待云台回正后的新画面超时')
                self._condition.wait(min(FRAME_WAIT_POLL_S, remaining))

    def _capture_frames(self) -> None:
        sequence = 0
        try:
            while not self._stop.is_set():
                read_started_at = time.monotonic()
                success, image = self._camera.read()
                read_finished_at = time.monotonic()
                if not success or image is None:
                    raise CameraObservationError(f'无法从摄像头读取图像: {self._device}')
                sequence += 1
                with self._condition:
                    self._latest = _CapturedFrame(
                        sequence, read_started_at, read_finished_at, image,
                    )
                    self._condition.notify_all()
                if read_finished_at - read_started_at < 0.01:
                    self._stop.wait(0.01)
        except Exception as error:
            with self._condition:
                self._read_error = error
                self._condition.notify_all()

    def _discard_warmup_frames(self) -> None:
        for _ in range(self._warmup_frames):
            success, _image = self._camera.read()
            if not success:
                raise CameraObservationError(
                    f'无法从摄像头读取预热图像: {self._device}'
                )
