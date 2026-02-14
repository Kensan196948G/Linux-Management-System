"""
共通入力検証モジュール

v0.3設計統合: 全モジュール共通のFORBIDDEN_CHARSと検証ロジック
"""

import re
from typing import Optional


# ===================================================================
# 禁止文字定義（全モジュール共通）
# ===================================================================
# CLAUDE.md 基準（15文字）+ users-planner拡張（+6文字）= 21文字
FORBIDDEN_CHARS_PATTERN = r'[;|&$()` ><*?{}\[\]\\\'\"\\n\\r\\t\\0]'

FORBIDDEN_CHARS_LIST = [
    ';',   # コマンド区切り
    '|',   # パイプ
    '&',   # バックグラウンド実行
    '$',   # 変数展開
    '(',   # サブシェル
    ')',   # サブシェル
    '`',   # コマンド置換
    ' ',   # スペース（意図しない引数分割）
    '>',   # リダイレクト
    '<',   # リダイレクト
    '*',   # ワイルドカード
    '?',   # ワイルドカード
    '{',   # ブレース展開
    '}',   # ブレース展開
    '[',   # グロブ
    ']',   # グロブ
    '\\',  # エスケープ
    "'",   # シングルクォート
    '"',   # ダブルクォート
    '\n',  # 改行
    '\r',  # キャリッジリターン
    '\t',  # タブ
    '\0',  # NULL文字
]


class ValidationError(ValueError):
    """入力検証エラー"""

    pass


def validate_no_forbidden_chars(value: str, field_name: str = "input") -> None:
    """
    禁止文字チェック

    Args:
        value: 検証する文字列
        field_name: フィールド名（エラーメッセージ用）

    Raises:
        ValidationError: 禁止文字が含まれる場合
    """
    for char in FORBIDDEN_CHARS_LIST:
        if char in value:
            raise ValidationError(
                f"{field_name} contains forbidden character: {repr(char)}"
            )


def validate_pattern(
    value: str, pattern: str, field_name: str = "input", max_length: Optional[int] = None
) -> None:
    """
    正規表現パターン検証

    Args:
        value: 検証する文字列
        pattern: 正規表現パターン
        field_name: フィールド名（エラーメッセージ用）
        max_length: 最大長（オプション）

    Raises:
        ValidationError: パターンに一致しない場合
    """
    if max_length and len(value) > max_length:
        raise ValidationError(
            f"{field_name} exceeds maximum length {max_length} (got {len(value)})"
        )

    if not re.match(pattern, value):
        raise ValidationError(f"{field_name} does not match required pattern")


def validate_username(username: str) -> None:
    """
    ユーザー名検証（共通ルール）

    Args:
        username: ユーザー名

    Raises:
        ValidationError: 検証失敗時
    """
    validate_pattern(
        username,
        r"^[a-z_][a-z0-9_-]{0,31}$",
        field_name="username",
        max_length=32,
    )
    validate_no_forbidden_chars(username, "username")


def validate_groupname(groupname: str) -> None:
    """
    グループ名検証（共通ルール）

    Args:
        groupname: グループ名

    Raises:
        ValidationError: 検証失敗時
    """
    validate_pattern(
        groupname,
        r"^[a-z_][a-z0-9_-]{0,31}$",
        field_name="groupname",
        max_length=32,
    )
    validate_no_forbidden_chars(groupname, "groupname")


def validate_uid_range(uid: int) -> None:
    """
    UID範囲検証

    Args:
        uid: UID

    Raises:
        ValidationError: 範囲外の場合
    """
    if uid < 1000 or uid > 59999:
        raise ValidationError(f"UID must be in range 1000-59999 (got {uid})")


def validate_gid_range(gid: int) -> None:
    """
    GID範囲検証

    Args:
        gid: GID

    Raises:
        ValidationError: 範囲外の場合
    """
    if gid < 1000 or gid > 59999:
        raise ValidationError(f"GID must be in range 1000-59999 (got {gid})")
