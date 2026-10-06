"""TonyPi 云台正前方置位和有限水平扫描。"""

import time


HEAD_VERTICAL_SERVO = 1
HEAD_HORIZONTAL_SERVO = 2
HEAD_VERTICAL_PULSE = 1500
HEAD_HORIZONTAL_PULSE = 1500
HEAD_MOVE_TIME_S = 0.5
HEAD_SETTLE_TIME_S = 0.2
HEAD_SCAN_MOVE_TIME_S = 0.25
HEAD_SCAN_PULSES = (
    *range(1450, 499, -50),
    *range(550, 2501, 50),
)


class HeadAligner:
    """每次机身动作前把相机光轴置于已标定的正前方。"""

    def __init__(self, action_group_control) -> None:
        try:
            self._board = action_group_control.board
        except AttributeError as error:
            raise RuntimeError('TonyPi SDK 缺少云台控制 board') from error

    def align(self) -> None:
        """同时置位两个云台舵机，并等待相机稳定。"""
        self._board.pwm_servo_set_position(
            HEAD_MOVE_TIME_S,
            [
                [HEAD_VERTICAL_SERVO, HEAD_VERTICAL_PULSE],
                [HEAD_HORIZONTAL_SERVO, HEAD_HORIZONTAL_PULSE],
            ],
        )
        time.sleep(HEAD_MOVE_TIME_S + HEAD_SETTLE_TIME_S)

    def turn_to(self, pulse: int) -> None:
        """将水平舵机移至扫描范围内的指定位置，调用方负责等待稳定。"""
        if pulse < 500 or pulse > 2500:
            raise ValueError('云台扫描位置超出安全范围')
        self._board.pwm_servo_set_position(
            HEAD_SCAN_MOVE_TIME_S,
            [[HEAD_HORIZONTAL_SERVO, pulse]],
        )
