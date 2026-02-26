"""ルートハンドラー共通ユーティリティ"""

import json


def parse_wrapper_result(result: dict) -> dict:
    """
    ラッパー実行結果の output フィールドを JSON パースして返す。

    sudo_wrapper の各メソッドは {'status': 'success', 'output': '<json str>'}
    形式を返すため、Pydantic モデルに渡す前にパースが必要。

    Args:
        result: sudo_wrapper からの返値

    Returns:
        output を JSON パースした辞書（パース失敗時は result をそのまま返す）
    """
    output = result.get("output")
    if output and isinstance(output, str):
        try:
            return json.loads(output)
        except (json.JSONDecodeError, TypeError):
            pass
    return result
