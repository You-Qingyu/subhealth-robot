"""校验 TonyPi 视觉导航 endpoint 的执行 contract。"""

import json


class InvalidPayload(ValueError):
    """`go_to_tag` payload 格式无效时抛出的错误。"""


class UnsupportedPrimitive(ValueError):
    """endpoint 收到不支持的 primitive 时抛出的错误。"""


def parse_payload(primitive: str, payload_json: str) -> dict:
    """解析并校验当前支持的动作 payload。

    当前只接受 `go_to_tag`，且 payload 必须只包含非空的 `target_tags`。
    Tag ID 由视觉导航在运行时检测，不再映射到固定动作组。

    :raises InvalidPayload: payload 不是规定的 JSON 结构时抛出。
    :raises UnsupportedPrimitive: primitive 不是 `go_to_tag` 时抛出。
    """
    if primitive != 'go_to_tag':
        raise UnsupportedPrimitive(primitive)

    try:
        payload = json.loads(payload_json)
    except (TypeError, json.JSONDecodeError) as error:
        raise InvalidPayload('payload_json must contain valid JSON') from error

    if not isinstance(payload, dict) or set(payload) != {'target_tags'}:
        raise InvalidPayload('go_to_tag payload requires only target_tags')

    target_tags = payload['target_tags']
    if not isinstance(target_tags, list) or not target_tags:
        raise InvalidPayload('target_tags must be a non-empty array')

    for target_tag in target_tags:
        if isinstance(target_tag, bool) or not isinstance(target_tag, int):
            raise InvalidPayload('target_tags must contain only integers')
        if target_tag < 0 or target_tag > 2**31 - 1:
            raise InvalidPayload(
                'target_tags must contain non-negative signed 32-bit integers'
            )

    return payload
