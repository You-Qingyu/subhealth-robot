"""只读离线 AprilTag 位姿观测命令。"""

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path

import cv2

from .tag_pose import TAG_FAMILIES, TagPoseEstimator


def main() -> None:
    """读取本地图像和标定文件，打印目标 Tag 的位姿，不接触运动接口。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('images', nargs='+', type=Path, help='离线 640x480 图像路径')
    parser.add_argument('--tag-id', type=int, required=True, help='待测 AprilTag ID')
    parser.add_argument('--family', required=True, choices=sorted(TAG_FAMILIES))
    parser.add_argument(
        '--calibration', type=Path,
        default=Path(os.environ.get('TONYPI_ROOT', '/home/pi/TonyPi'))
        / 'Functions/CameraCalibration/calibration_param.npz',
        help='当前摄像头的标定文件',
    )
    args = parser.parse_args()
    estimator = TagPoseEstimator(args.calibration, args.family)
    for path in args.images:
        image = cv2.imread(str(path))
        if image is None:
            raise ValueError(f'无法读取图像: {path}')
        pose = estimator.estimate(image, args.tag_id)
        print(json.dumps(
            {'image': str(path), 'tag_id': args.tag_id, 'pose': asdict(pose) if pose else None},
            ensure_ascii=False,
        ))
