"""TonyPi 云台正前方置位。"""

import time


HEAD_VERTICAL_SERVO = 1
HEAD_HORIZONTAL_SERVO = 2
HEAD_VERTICAL_PULSE = 1500
HEAD_HORIZONTAL_PULSE = 1435
HEAD_MOVE_TIME_S = 0.5
HEAD_SETTLE_TIME_S = 0.2


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
