"""从指定 V4L2 摄像头采集一张未处理的标定尺寸原图。"""

import argparse
from pathlib import Path

import cv2

from .tag_pose import CALIBRATED_IMAGE_SIZE


def main() -> None:
    """采集有限帧并保存原图，不导入或调用 TonyPi 运动接口。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='输出图像路径，不覆盖现有文件')
    parser.add_argument('--device', default='/dev/video0', help='V4L2 相机设备路径')
    parser.add_argument('--warmup-frames', type=int, default=10)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f'输出文件已存在: {args.output}')
    if args.warmup_frames < 0:
        parser.error('--warmup-frames 必须是非负整数')

    camera = cv2.VideoCapture(args.device, cv2.CAP_V4L2)
    if not camera.isOpened():
        raise RuntimeError(f'无法打开摄像头: {args.device}')
    try:
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, CALIBRATED_IMAGE_SIZE[0])
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, CALIBRATED_IMAGE_SIZE[1])
        image = None
        for _ in range(args.warmup_frames + 1):
            success, image = camera.read()
            if not success:
                raise RuntimeError(f'无法从摄像头读取图像: {args.device}')
    finally:
        camera.release()

    if (image.shape[1], image.shape[0]) != CALIBRATED_IMAGE_SIZE:
        raise ValueError('摄像头输出尺寸与 640x480 标定不一致，图像未保存')
    if not cv2.imwrite(str(args.output), image):
        raise RuntimeError(f'无法写入图像: {args.output}')
    print(f'已保存未经缩放、翻转或去畸变的原图: {args.output}')
