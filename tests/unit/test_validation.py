"""
backend/core/validation.py のユニットテスト
"""

import pytest

from backend.core.validation import (
    FORBIDDEN_CHARS_LIST,
    FORBIDDEN_CHARS_PATTERN,
    ValidationError,
    validate_gid_range,
    validate_groupname,
    validate_no_forbidden_chars,
    validate_pattern,
    validate_uid_range,
    validate_username,
)


class TestForbiddenCharsConstants:
    """FORBIDDEN_CHARS定数のテスト"""

    def test_forbidden_chars_list_length(self):
        """禁止文字リストが21文字であること"""
        assert len(FORBIDDEN_CHARS_LIST) == 23  # 21 unique + space + NULL

    def test_forbidden_chars_pattern_exists(self):
        """禁止文字パターンが定義されていること"""
        assert FORBIDDEN_CHARS_PATTERN is not None
        assert len(FORBIDDEN_CHARS_PATTERN) > 0

    def test_forbidden_chars_includes_claude_md_baseline(self):
        """CLAUDE.md基準の15文字を含むこと"""
        claude_md_chars = [';', '|', '&', '$', '(', ')', '`', '>', '<', '*', '?', '{', '}', '[', ']']
        for char in claude_md_chars:
            assert char in FORBIDDEN_CHARS_LIST, f"CLAUDE.md baseline char '{char}' missing"


class TestValidateNoForbiddenChars:
    """validate_no_forbidden_chars のテスト"""

    def test_valid_string_alphanumeric(self):
        """英数字のみの文字列は許可"""
        validate_no_forbidden_chars("test123", "test_field")
        validate_no_forbidden_chars("abcdefg", "test_field")
        validate_no_forbidden_chars("12345", "test_field")

    def test_valid_string_with_dash_underscore(self):
        """ハイフン・アンダースコアは許可"""
        validate_no_forbidden_chars("test-name_123", "test_field")
        validate_no_forbidden_chars("user_name-test", "test_field")

    def test_reject_semicolon(self):
        """セミコロンを拒否"""
        with pytest.raises(ValidationError, match="forbidden character.*';'"):
            validate_no_forbidden_chars("test;rm -rf", "test_field")

    def test_reject_pipe(self):
        """パイプを拒否"""
        with pytest.raises(ValidationError, match="forbidden character.*'\\|'"):
            validate_no_forbidden_chars("cat | grep", "test_field")

    def test_reject_ampersand(self):
        """アンパサンドを拒否"""
        with pytest.raises(ValidationError, match="forbidden character.*'&'"):
            validate_no_forbidden_chars("test & background", "test_field")

    def test_reject_dollar(self):
        """ドル記号を拒否"""
        with pytest.raises(ValidationError, match="forbidden character.*'\\$'"):
            validate_no_forbidden_chars("test$var", "test_field")

    def test_reject_parentheses(self):
        """括弧を拒否"""
        with pytest.raises(ValidationError, match="forbidden character"):
            validate_no_forbidden_chars("test(subshell)", "test_field")

    def test_reject_backtick(self):
        """バッククォートを拒否"""
        with pytest.raises(ValidationError, match="forbidden character"):
            validate_no_forbidden_chars("test`command`", "test_field")

    def test_reject_redirect_gt(self):
        """>を拒否"""
        # スペースが先に検出されるため、スペースなしで検証
        with pytest.raises(ValidationError, match="forbidden character.*'>'"):
            validate_no_forbidden_chars("test>file", "test_field")

    def test_reject_redirect_lt(self):
        """<を拒否"""
        # スペースが先に検出されるため、スペースなしで検証
        with pytest.raises(ValidationError, match="forbidden character.*'<'"):
            validate_no_forbidden_chars("test<file", "test_field")

    def test_reject_asterisk(self):
        """アスタリスクを拒否"""
        with pytest.raises(ValidationError, match="forbidden character.*'\\*'"):
            validate_no_forbidden_chars("test*", "test_field")

    def test_reject_question_mark(self):
        """クエスチョンマークを拒否"""
        with pytest.raises(ValidationError, match="forbidden character.*'\\?'"):
            validate_no_forbidden_chars("test?", "test_field")

    def test_reject_braces(self):
        """ブレースを拒否"""
        with pytest.raises(ValidationError, match="forbidden character"):
            validate_no_forbidden_chars("test{}", "test_field")

    def test_reject_brackets(self):
        """ブラケットを拒否"""
        with pytest.raises(ValidationError, match="forbidden character"):
            validate_no_forbidden_chars("test[]", "test_field")

    def test_reject_backslash(self):
        """バックスラッシュを拒否（users-planner拡張）"""
        with pytest.raises(ValidationError, match="forbidden character.*'\\\\\\\\'"):
            validate_no_forbidden_chars("test\\escape", "test_field")

    def test_reject_single_quote(self):
        """シングルクォートを拒否（users-planner拡張）"""
        with pytest.raises(ValidationError, match="forbidden character.*\"'\""):
            validate_no_forbidden_chars("test'quote", "test_field")

    def test_reject_double_quote(self):
        """ダブルクォートを拒否（users-planner拡張）"""
        with pytest.raises(ValidationError, match='forbidden character.*\'"\''):
            validate_no_forbidden_chars('test"quote', "test_field")

    def test_reject_newline(self):
        """改行を拒否（users-planner拡張）"""
        with pytest.raises(ValidationError, match="forbidden character.*'\\\\n'"):
            validate_no_forbidden_chars("test\nline", "test_field")

    def test_reject_tab(self):
        """タブを拒否（users-planner拡張）"""
        with pytest.raises(ValidationError, match="forbidden character.*'\\\\t'"):
            validate_no_forbidden_chars("test\ttab", "test_field")

    def test_custom_field_name_in_error(self):
        """カスタムフィールド名がエラーメッセージに含まれること"""
        with pytest.raises(ValidationError, match="custom_field contains forbidden character"):
            validate_no_forbidden_chars("test;injection", "custom_field")


class TestValidatePattern:
    """validate_pattern のテスト"""

    def test_valid_pattern_match(self):
        """パターンに一致する文字列は許可"""
        validate_pattern("test123", r"^[a-z0-9]+$", "test_field")

    def test_invalid_pattern_nomatch(self):
        """パターンに一致しない文字列は拒否"""
        with pytest.raises(ValidationError, match="does not match required pattern"):
            validate_pattern("TEST", r"^[a-z]+$", "test_field")

    def test_max_length_enforcement(self):
        """最大長を超える文字列は拒否"""
        with pytest.raises(ValidationError, match="exceeds maximum length"):
            validate_pattern("a" * 100, r"^[a-z]+$", "test_field", max_length=10)

    def test_max_length_exact_boundary(self):
        """最大長ちょうどの文字列は許可"""
        validate_pattern("a" * 10, r"^[a-z]+$", "test_field", max_length=10)


class TestValidateUsername:
    """validate_username のテスト"""

    def test_valid_username_lowercase_start(self):
        """小文字で始まるユーザー名は許可"""
        validate_username("testuser")
        validate_username("user123")

    def test_valid_username_underscore_start(self):
        """アンダースコアで始まるユーザー名は許可"""
        validate_username("_test")

    def test_valid_username_with_dash(self):
        """ハイフンを含むユーザー名は許可"""
        validate_username("test-user")

    def test_invalid_username_uppercase_start(self):
        """大文字で始まるユーザー名は拒否"""
        with pytest.raises(ValidationError, match="does not match required pattern"):
            validate_username("TestUser")

    def test_invalid_username_digit_start(self):
        """数字で始まるユーザー名は拒否"""
        with pytest.raises(ValidationError, match="does not match required pattern"):
            validate_username("123user")

    def test_invalid_username_too_long(self):
        """33文字以上のユーザー名は拒否"""
        with pytest.raises(ValidationError, match="exceeds maximum length"):
            validate_username("a" * 33)

    def test_invalid_username_forbidden_chars(self):
        """禁止文字を含むユーザー名は拒否"""
        with pytest.raises(ValidationError, match="forbidden character"):
            validate_username("user;injection")


class TestValidateGroupname:
    """validate_groupname のテスト"""

    def test_valid_groupname(self):
        """有効なグループ名は許可"""
        validate_groupname("developers")
        validate_groupname("test_group")

    def test_invalid_groupname_forbidden_chars(self):
        """禁止文字を含むグループ名は拒否"""
        with pytest.raises(ValidationError, match="forbidden character"):
            validate_groupname("group|name")


class TestValidateUIDRange:
    """validate_uid_range のテスト"""

    def test_valid_uid_minimum(self):
        """最小UID（1000）は許可"""
        validate_uid_range(1000)

    def test_valid_uid_maximum(self):
        """最大UID（59999）は許可"""
        validate_uid_range(59999)

    def test_valid_uid_middle(self):
        """範囲内のUIDは許可"""
        validate_uid_range(5000)

    def test_invalid_uid_too_low(self):
        """999以下のUIDは拒否"""
        with pytest.raises(ValidationError, match="UID must be in range"):
            validate_uid_range(999)

    def test_invalid_uid_system_user(self):
        """システムユーザー範囲（0-999）は拒否"""
        with pytest.raises(ValidationError, match="UID must be in range"):
            validate_uid_range(0)
        with pytest.raises(ValidationError, match="UID must be in range"):
            validate_uid_range(500)

    def test_invalid_uid_too_high(self):
        """60000以上のUIDは拒否"""
        with pytest.raises(ValidationError, match="UID must be in range"):
            validate_uid_range(60000)


class TestValidateGIDRange:
    """validate_gid_range のテスト"""

    def test_valid_gid_minimum(self):
        """最小GID（1000）は許可"""
        validate_gid_range(1000)

    def test_valid_gid_maximum(self):
        """最大GID（59999）は許可"""
        validate_gid_range(59999)

    def test_invalid_gid_too_low(self):
        """999以下のGIDは拒否"""
        with pytest.raises(ValidationError, match="GID must be in range"):
            validate_gid_range(999)

    def test_invalid_gid_too_high(self):
        """60000以上のGIDは拒否"""
        with pytest.raises(ValidationError, match="GID must be in range"):
            validate_gid_range(60000)
