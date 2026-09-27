"""校验第一版 TonyPi 执行 contract。"""

import json


ACTION_GROUPS = {
    1: 'turn_left',
    2: 'go_forward_one_step',
    3: 'turn_right',
}


class InvalidPayload(ValueError):
    """`go_to_tag` payload 格式无效时抛出的错误。"""


class UnsupportedPrimitive(ValueError):
    """endpoint 收到不支持的 primitive 时抛出的错误。"""


class UnsupportedTag(ValueError):
    """目标 Tag 没有第一版动作映射时抛出的错误。"""


def parse_payload(primitive: str, payload_json: str) -> dict:
    """解析并校验当前支持的动作 payload。

    当前只接受 `go_to_tag`，且 payload 必须只包含非空的 `target_tags`。
    第一版只支持有动作映射的 Tag `1`、`2` 和 `3`。

    :raises InvalidPayload: payload 不是规定的 JSON 结构时抛出。
    :raises UnsupportedPrimitive: primitive 不是 `go_to_tag` 时抛出。
    :raises UnsupportedTag: Tag 没有第一版动作映射时抛出。
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
        if target_tag not in ACTION_GROUPS:
            raise UnsupportedTag(str(target_tag))

    return payload
