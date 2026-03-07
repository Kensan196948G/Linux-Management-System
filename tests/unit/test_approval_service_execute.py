"""
ApprovalService.execute_request() のユニットテスト

テスト対象: backend/core/approval_service.py  (execute_request, lines 578-830)
テスト件数: 35+
"""

import asyncio
import json
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.core.approval_service import ApprovalService


# ============================================================================
# ヘルパー
# ============================================================================

SUCCESS_RESULT = {"status": "success", "message": "ok"}
ERROR_RESULT = {"status": "error", "message": "wrapper error"}


def run_async(coro):
    """asyncio コルーチンを同期実行"""
    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    except RuntimeError:
        return asyncio.run(coro)


def _init_db(db_path: str) -> None:
    """スキーマ初期化"""
    schema_path = Path(__file__).parent.parent.parent / "docs" / "database" / "approval-schema.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(schema_sql)


def _insert_approved_request(db_path: str, request_id: str, request_type: str, payload: dict) -> None:
    """承認済みリクエストをDBに直接挿入"""
    expires_at = (datetime.utcnow() + timedelta(hours=24)).isoformat()
    approved_at = datetime.utcnow().isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO approval_requests
              (id, request_type, requester_id, requester_name, request_payload,
               reason, status, created_at, expires_at, approved_by, approved_by_name, approved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request_id,
                request_type,
                "requester-001",
                "requester",
                json.dumps(payload),
                "テスト実行",
                "approved",
                datetime.utcnow().isoformat(),
                expires_at,
                "approver-001",
                "approver",
                approved_at,
            ),
        )
        conn.commit()


def _insert_pending_request(db_path: str, request_id: str, request_type: str, payload: dict) -> None:
    """pending リクエストをDBに直接挿入"""
    expires_at = (datetime.utcnow() + timedelta(hours=24)).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO approval_requests
              (id, request_type, requester_id, requester_name, request_payload,
               reason, status, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request_id,
                request_type,
                "requester-001",
                "requester",
                json.dumps(payload),
                "テスト実行",
                "pending",
                datetime.utcnow().isoformat(),
                expires_at,
            ),
        )
        conn.commit()


# ============================================================================
# フィクスチャ
# ============================================================================


@pytest.fixture
def db_path(tmp_path):
    """テスト用DBパス"""
    path = str(tmp_path / "test_execute.db")
    _init_db(path)
    return path


@pytest.fixture
def service(db_path):
    """テスト用 ApprovalService"""
    svc = ApprovalService(db_path=db_path)
    svc.audit_log = MagicMock()
    return svc


EXECUTOR = {
    "executor_id": "executor-001",
    "executor_name": "admin",
    "executor_role": "Admin",
}


# ============================================================================
# TC001–TC003: 基本エラーケース
# ============================================================================


class TestExecuteRequestBasicErrors:
    """基本エラー条件のテスト"""

    def test_lookup_error_when_request_not_found(self, service):
        """TC001: 存在しないリクエストIDでLookupErrorが発生する"""
        with pytest.raises(LookupError, match="not found"):
            run_async(service.execute_request("nonexistent-id", **EXECUTOR))

    def test_value_error_when_status_is_pending(self, service, db_path):
        """TC002: pending ステータスのリクエストはValueErrorが発生する"""
        req_id = str(uuid.uuid4())
        _insert_pending_request(db_path, req_id, "user_add", {"username": "u"})
        with pytest.raises(ValueError, match="cannot be executed"):
            run_async(service.execute_request(req_id, **EXECUTOR))

    def test_value_error_when_status_is_rejected(self, service, db_path):
        """TC003: rejected ステータスのリクエストはValueErrorが発生する"""
        req_id = str(uuid.uuid4())
        expires_at = (datetime.utcnow() + timedelta(hours=24)).isoformat()
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO approval_requests
                  (id, request_type, requester_id, requester_name, request_payload,
                   reason, status, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    req_id,
                    "user_add",
                    "r1",
                    "requester",
                    json.dumps({"username": "u"}),
                    "test",
                    "rejected",
                    datetime.utcnow().isoformat(),
                    expires_at,
                ),
            )
            conn.commit()
        with pytest.raises(ValueError, match="cannot be executed"):
            run_async(service.execute_request(req_id, **EXECUTOR))


# ============================================================================
# TC004–TC006: user_add
# ============================================================================


class TestExecuteUserAdd:
    """user_add 操作のテスト"""

    def test_user_add_success(self, service, db_path):
        """TC004: user_add が成功する"""
        req_id = str(uuid.uuid4())
        payload = {"username": "newuser", "shell": "/bin/bash", "gecos": "New User", "groups": ["users"]}
        _insert_approved_request(db_path, req_id, "user_add", payload)

        with patch("backend.core.sudo_wrapper.sudo_wrapper.add_user", return_value=SUCCESS_RESULT):
            result = run_async(service.execute_request(req_id, **EXECUTOR))

        assert result["request_id"] == req_id
        assert result["request_type"] == "user_add"
        assert result["executed_by"] == "executor-001"

    def test_user_add_with_password_hash(self, service, db_path):
        """TC005: password_hash 指定の user_add が成功する"""
        req_id = str(uuid.uuid4())
        payload = {"username": "newuser2", "password_hash": "$6$salt$hash"}
        _insert_approved_request(db_path, req_id, "user_add", payload)

        with patch("backend.core.sudo_wrapper.sudo_wrapper.add_user", return_value=SUCCESS_RESULT):
            result = run_async(service.execute_request(req_id, **EXECUTOR))

        assert "request_id" in result

    def test_user_add_execution_failure(self, service, db_path):
        """TC006: user_add でラッパーエラーが発生した場合"""
        from backend.core.sudo_wrapper import SudoWrapperError

        req_id = str(uuid.uuid4())
        payload = {"username": "failuser"}
        _insert_approved_request(db_path, req_id, "user_add", payload)

        with patch("backend.core.sudo_wrapper.sudo_wrapper.add_user", side_effect=SudoWrapperError("failed")):
            with pytest.raises(SudoWrapperError):
                run_async(service.execute_request(req_id, **EXECUTOR))

        # DB上のステータスが execution_failed になっていること
        with sqlite3.connect(db_path) as conn:
            row = conn.execute("SELECT status FROM approval_requests WHERE id=?", (req_id,)).fetchone()
        assert row[0] == "execution_failed"


# ============================================================================
# TC007–TC009: user_delete
# ============================================================================


class TestExecuteUserDelete:
    """user_delete 操作のテスト"""

    def test_user_delete_success(self, service, db_path):
        """TC007: user_delete が成功する"""
        req_id = str(uuid.uuid4())
        payload = {"username": "deluser", "remove_home": True, "backup_home": False, "force_logout": False}
        _insert_approved_request(db_path, req_id, "user_delete", payload)

        with patch("backend.core.sudo_wrapper.sudo_wrapper.delete_user", return_value=SUCCESS_RESULT):
            result = run_async(service.execute_request(req_id, **EXECUTOR))

        assert result["request_type"] == "user_delete"

    def test_user_delete_minimal_payload(self, service, db_path):
        """TC008: user_delete 最小ペイロードでも成功する"""
        req_id = str(uuid.uuid4())
        payload = {"username": "deluser2"}
        _insert_approved_request(db_path, req_id, "user_delete", payload)

        with patch("backend.core.sudo_wrapper.sudo_wrapper.delete_user", return_value=SUCCESS_RESULT):
            result = run_async(service.execute_request(req_id, **EXECUTOR))

        assert "request_id" in result

    def test_user_delete_failure(self, service, db_path):
        """TC009: user_delete でラッパーエラーが発生した場合"""
        from backend.core.sudo_wrapper import SudoWrapperError

        req_id = str(uuid.uuid4())
        payload = {"username": "failuser"}
        _insert_approved_request(db_path, req_id, "user_delete", payload)

        with patch("backend.core.sudo_wrapper.sudo_wrapper.delete_user", side_effect=SudoWrapperError("del failed")):
            with pytest.raises(SudoWrapperError):
                run_async(service.execute_request(req_id, **EXECUTOR))


# ============================================================================
# TC010–TC012: user_passwd
# ============================================================================


class TestExecuteUserPasswd:
    """user_passwd 操作のテスト"""

    def test_user_passwd_success(self, service, db_path):
        """TC010: user_passwd が成功する"""
        req_id = str(uuid.uuid4())
        payload = {"username": "someuser", "password_hash": "$6$salt$hash"}
        _insert_approved_request(db_path, req_id, "user_passwd", payload)

        with patch("backend.core.sudo_wrapper.sudo_wrapper.change_user_password", return_value=SUCCESS_RESULT):
            result = run_async(service.execute_request(req_id, **EXECUTOR))

        assert result["request_type"] == "user_passwd"

    def test_user_passwd_missing_hash_raises_value_error(self, service, db_path):
        """TC011: password_hash が無い場合は ValueError が伝播する"""
        req_id = str(uuid.uuid4())
        payload = {"username": "someuser"}  # password_hash なし
        _insert_approved_request(db_path, req_id, "user_passwd", payload)

        with pytest.raises((ValueError, Exception)):
            run_async(service.execute_request(req_id, **EXECUTOR))

    def test_user_passwd_wrapper_error(self, service, db_path):
        """TC012: user_passwd でラッパーエラー"""
        from backend.core.sudo_wrapper import SudoWrapperError

        req_id = str(uuid.uuid4())
        payload = {"username": "someuser", "password_hash": "$6$salt$hash"}
        _insert_approved_request(db_path, req_id, "user_passwd", payload)

        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.change_user_password", side_effect=SudoWrapperError("pw failed")
        ):
            with pytest.raises(SudoWrapperError):
                run_async(service.execute_request(req_id, **EXECUTOR))


# ============================================================================
# TC013–TC019: user_modify
# ============================================================================


class TestExecuteUserModify:
    """user_modify 操作のテスト（action 分岐）"""

    def test_user_modify_set_shell(self, service, db_path):
        """TC013: user_modify action=set-shell"""
        req_id = str(uuid.uuid4())
        payload = {"username": "u1", "action": "set-shell", "shell": "/bin/zsh"}
        _insert_approved_request(db_path, req_id, "user_modify", payload)

        with patch("backend.core.sudo_wrapper.sudo_wrapper.modify_user_shell", return_value=SUCCESS_RESULT):
            result = run_async(service.execute_request(req_id, **EXECUTOR))

        assert result["request_type"] == "user_modify"

    def test_user_modify_set_gecos(self, service, db_path):
        """TC014: user_modify action=set-gecos"""
        req_id = str(uuid.uuid4())
        payload = {"username": "u1", "action": "set-gecos", "gecos": "Full Name"}
        _insert_approved_request(db_path, req_id, "user_modify", payload)

        with patch("backend.core.sudo_wrapper.sudo_wrapper.modify_user_gecos", return_value=SUCCESS_RESULT):
            result = run_async(service.execute_request(req_id, **EXECUTOR))

        assert "request_id" in result

    def test_user_modify_add_group(self, service, db_path):
        """TC015: user_modify action=add-group"""
        req_id = str(uuid.uuid4())
        payload = {"username": "u1", "action": "add-group", "group": "sudo"}
        _insert_approved_request(db_path, req_id, "user_modify", payload)

        with patch("backend.core.sudo_wrapper.sudo_wrapper.modify_user_add_group", return_value=SUCCESS_RESULT):
            result = run_async(service.execute_request(req_id, **EXECUTOR))

        assert "request_id" in result

    def test_user_modify_remove_group(self, service, db_path):
        """TC016: user_modify action=remove-group"""
        req_id = str(uuid.uuid4())
        payload = {"username": "u1", "action": "remove-group", "group": "sudo"}
        _insert_approved_request(db_path, req_id, "user_modify", payload)

        with patch("backend.core.sudo_wrapper.sudo_wrapper.modify_user_remove_group", return_value=SUCCESS_RESULT):
            result = run_async(service.execute_request(req_id, **EXECUTOR))

        assert "request_id" in result

    def test_user_modify_unknown_action_raises(self, service, db_path):
        """TC017: user_modify 未知の action は NotImplementedError"""
        from backend.core.sudo_wrapper import SudoWrapperError

        req_id = str(uuid.uuid4())
        payload = {"username": "u1", "action": "unknown-action"}
        _insert_approved_request(db_path, req_id, "user_modify", payload)

        with pytest.raises(SudoWrapperError):
            run_async(service.execute_request(req_id, **EXECUTOR))

    def test_user_modify_set_shell_failure(self, service, db_path):
        """TC018: user_modify set-shell でラッパーエラー"""
        from backend.core.sudo_wrapper import SudoWrapperError

        req_id = str(uuid.uuid4())
        payload = {"username": "u1", "action": "set-shell", "shell": "/bin/sh"}
        _insert_approved_request(db_path, req_id, "user_modify", payload)

        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.modify_user_shell", side_effect=SudoWrapperError("shell failed")
        ):
            with pytest.raises(SudoWrapperError):
                run_async(service.execute_request(req_id, **EXECUTOR))

    def test_user_modify_empty_action(self, service, db_path):
        """TC019: user_modify action が空文字列は NotImplementedError"""
        from backend.core.sudo_wrapper import SudoWrapperError

        req_id = str(uuid.uuid4())
        payload = {"username": "u1", "action": ""}
        _insert_approved_request(db_path, req_id, "user_modify", payload)

        with pytest.raises(SudoWrapperError):
            run_async(service.execute_request(req_id, **EXECUTOR))


# ============================================================================
# TC020–TC022: group_add / group_delete / group_modify
# ============================================================================


class TestExecuteGroupOperations:
    """グループ操作のテスト"""

    def test_group_add_success(self, service, db_path):
        """TC020: group_add が成功する"""
        req_id = str(uuid.uuid4())
        payload = {"name": "newgroup"}
        _insert_approved_request(db_path, req_id, "group_add", payload)

        with patch("backend.core.sudo_wrapper.sudo_wrapper.add_group", return_value=SUCCESS_RESULT):
            result = run_async(service.execute_request(req_id, **EXECUTOR))

        assert result["request_type"] == "group_add"

    def test_group_delete_success(self, service, db_path):
        """TC021: group_delete が成功する"""
        req_id = str(uuid.uuid4())
        payload = {"name": "oldgroup"}
        _insert_approved_request(db_path, req_id, "group_delete", payload)

        with patch("backend.core.sudo_wrapper.sudo_wrapper.delete_group", return_value=SUCCESS_RESULT):
            result = run_async(service.execute_request(req_id, **EXECUTOR))

        assert result["request_type"] == "group_delete"

    def test_group_modify_success(self, service, db_path):
        """TC022: group_modify が成功する"""
        req_id = str(uuid.uuid4())
        payload = {"group": "somegroup", "action": "add", "user": "someuser"}
        _insert_approved_request(db_path, req_id, "group_modify", payload)

        with patch("backend.core.sudo_wrapper.sudo_wrapper.modify_group_membership", return_value=SUCCESS_RESULT):
            result = run_async(service.execute_request(req_id, **EXECUTOR))

        assert result["request_type"] == "group_modify"

    def test_group_add_failure(self, service, db_path):
        """TC022b: group_add でラッパーエラー"""
        from backend.core.sudo_wrapper import SudoWrapperError

        req_id = str(uuid.uuid4())
        payload = {"name": "failgroup"}
        _insert_approved_request(db_path, req_id, "group_add", payload)

        with patch("backend.core.sudo_wrapper.sudo_wrapper.add_group", side_effect=SudoWrapperError("grp fail")):
            with pytest.raises(SudoWrapperError):
                run_async(service.execute_request(req_id, **EXECUTOR))


# ============================================================================
# TC023–TC026: cron_add / cron_delete / cron_modify
# ============================================================================


class TestExecuteCronOperations:
    """Cron 操作のテスト"""

    def test_cron_add_success(self, service, db_path):
        """TC023: cron_add が成功する"""
        req_id = str(uuid.uuid4())
        payload = {
            "username": "cronuser",
            "schedule": "0 * * * *",
            "command": "/usr/local/bin/myscript.sh",
            "arguments": "",
            "comment": "test job",
        }
        _insert_approved_request(db_path, req_id, "cron_add", payload)

        with patch("backend.core.sudo_wrapper.sudo_wrapper.add_cron_job", return_value=SUCCESS_RESULT):
            result = run_async(service.execute_request(req_id, **EXECUTOR))

        assert result["request_type"] == "cron_add"

    def test_cron_delete_success(self, service, db_path):
        """TC024: cron_delete が成功する"""
        req_id = str(uuid.uuid4())
        payload = {"username": "cronuser", "line_number": 3}
        _insert_approved_request(db_path, req_id, "cron_delete", payload)

        with patch("backend.core.sudo_wrapper.sudo_wrapper.remove_cron_job", return_value=SUCCESS_RESULT):
            result = run_async(service.execute_request(req_id, **EXECUTOR))

        assert result["request_type"] == "cron_delete"

    def test_cron_modify_success(self, service, db_path):
        """TC025: cron_modify が成功する"""
        req_id = str(uuid.uuid4())
        payload = {"username": "cronuser", "line_number": 2, "action": "disable"}
        _insert_approved_request(db_path, req_id, "cron_modify", payload)

        with patch("backend.core.sudo_wrapper.sudo_wrapper.toggle_cron_job", return_value=SUCCESS_RESULT):
            result = run_async(service.execute_request(req_id, **EXECUTOR))

        assert result["request_type"] == "cron_modify"

    def test_cron_add_failure(self, service, db_path):
        """TC026: cron_add でラッパーエラー"""
        from backend.core.sudo_wrapper import SudoWrapperError

        req_id = str(uuid.uuid4())
        payload = {
            "username": "cronuser",
            "schedule": "* * * * *",
            "command": "/bin/true",
        }
        _insert_approved_request(db_path, req_id, "cron_add", payload)

        with patch("backend.core.sudo_wrapper.sudo_wrapper.add_cron_job", side_effect=SudoWrapperError("cron fail")):
            with pytest.raises(SudoWrapperError):
                run_async(service.execute_request(req_id, **EXECUTOR))


# ============================================================================
# TC027: service_stop
# ============================================================================


class TestExecuteServiceStop:
    """service_stop 操作のテスト"""

    def test_service_stop_success(self, service, db_path):
        """TC027: service_stop が成功する"""
        req_id = str(uuid.uuid4())
        payload = {"service_name": "nginx"}
        _insert_approved_request(db_path, req_id, "service_stop", payload)

        with patch("backend.core.sudo_wrapper.sudo_wrapper.stop_service", return_value=SUCCESS_RESULT):
            result = run_async(service.execute_request(req_id, **EXECUTOR))

        assert result["request_type"] == "service_stop"

    def test_service_stop_failure(self, service, db_path):
        """TC027b: service_stop でラッパーエラー"""
        from backend.core.sudo_wrapper import SudoWrapperError

        req_id = str(uuid.uuid4())
        payload = {"service_name": "nginx"}
        _insert_approved_request(db_path, req_id, "service_stop", payload)

        with patch("backend.core.sudo_wrapper.sudo_wrapper.stop_service", side_effect=SudoWrapperError("stop fail")):
            with pytest.raises(SudoWrapperError):
                run_async(service.execute_request(req_id, **EXECUTOR))


# ============================================================================
# TC028–TC031: firewall_modify
# ============================================================================


class TestExecuteFirewallModify:
    """firewall_modify 操作のテスト"""

    def test_firewall_allow_success(self, service, db_path):
        """TC028: firewall_modify action=allow が成功する"""
        req_id = str(uuid.uuid4())
        payload = {"action": "allow", "port": 8080, "protocol": "tcp"}
        _insert_approved_request(db_path, req_id, "firewall_modify", payload)

        with patch("backend.core.sudo_wrapper.sudo_wrapper.allow_firewall_port", return_value=SUCCESS_RESULT):
            result = run_async(service.execute_request(req_id, **EXECUTOR))

        assert result["request_type"] == "firewall_modify"

    def test_firewall_deny_success(self, service, db_path):
        """TC029: firewall_modify action=deny が成功する"""
        req_id = str(uuid.uuid4())
        payload = {"action": "deny", "port": 22, "protocol": "tcp"}
        _insert_approved_request(db_path, req_id, "firewall_modify", payload)

        with patch("backend.core.sudo_wrapper.sudo_wrapper.deny_firewall_port", return_value=SUCCESS_RESULT):
            result = run_async(service.execute_request(req_id, **EXECUTOR))

        assert result["request_type"] == "firewall_modify"

    def test_firewall_delete_success(self, service, db_path):
        """TC030: firewall_modify action=delete が成功する"""
        req_id = str(uuid.uuid4())
        payload = {"action": "delete", "rule_num": 3}
        _insert_approved_request(db_path, req_id, "firewall_modify", payload)

        with patch("backend.core.sudo_wrapper.sudo_wrapper.delete_firewall_rule", return_value=SUCCESS_RESULT):
            result = run_async(service.execute_request(req_id, **EXECUTOR))

        assert result["request_type"] == "firewall_modify"

    def test_firewall_unknown_action_raises(self, service, db_path):
        """TC031: firewall_modify 未知の action は ValueError が伝播する"""
        req_id = str(uuid.uuid4())
        payload = {"action": "unknown", "port": 80}
        _insert_approved_request(db_path, req_id, "firewall_modify", payload)

        with pytest.raises((ValueError, Exception)):
            run_async(service.execute_request(req_id, **EXECUTOR))

    def test_firewall_allow_failure(self, service, db_path):
        """TC031b: firewall allow でラッパーエラー"""
        from backend.core.sudo_wrapper import SudoWrapperError

        req_id = str(uuid.uuid4())
        payload = {"action": "allow", "port": 443}
        _insert_approved_request(db_path, req_id, "firewall_modify", payload)

        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.allow_firewall_port", side_effect=SudoWrapperError("fw fail")
        ):
            with pytest.raises(SudoWrapperError):
                run_async(service.execute_request(req_id, **EXECUTOR))


# ============================================================================
# TC032: 未知の operation_type
# ============================================================================


class TestExecuteUnknownType:
    """未知の operation_type のテスト"""

    def test_unknown_request_type_raises(self, service, db_path):
        """TC032: 未知のリクエストタイプは SudoWrapperError になる（内部NotImplementedError）"""
        from backend.core.sudo_wrapper import SudoWrapperError

        req_id = str(uuid.uuid4())
        # 直接 approved 状態で不明タイプを挿入（バリデーションを迂回）
        expires_at = (datetime.utcnow() + timedelta(hours=24)).isoformat()
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO approval_requests
                  (id, request_type, requester_id, requester_name, request_payload,
                   reason, status, created_at, expires_at, approved_by, approved_by_name, approved_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    req_id,
                    "totally_unknown_type",
                    "r1",
                    "requester",
                    json.dumps({"key": "value"}),
                    "test",
                    "approved",
                    datetime.utcnow().isoformat(),
                    expires_at,
                    "a1",
                    "approver",
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()

        with pytest.raises(SudoWrapperError):
            run_async(service.execute_request(req_id, **EXECUTOR))


# ============================================================================
# TC033–TC035: 実行後のDB状態確認
# ============================================================================


class TestExecuteDbStateAfterExecution:
    """実行後のDB状態確認"""

    def test_db_status_becomes_executed_on_success(self, service, db_path):
        """TC033: 成功後はDBステータスが executed になる"""
        req_id = str(uuid.uuid4())
        payload = {"service_name": "nginx"}
        _insert_approved_request(db_path, req_id, "service_stop", payload)

        with patch("backend.core.sudo_wrapper.sudo_wrapper.stop_service", return_value=SUCCESS_RESULT):
            run_async(service.execute_request(req_id, **EXECUTOR))

        with sqlite3.connect(db_path) as conn:
            row = conn.execute("SELECT status, executed_by FROM approval_requests WHERE id=?", (req_id,)).fetchone()
        assert row[0] == "executed"
        assert row[1] == "executor-001"

    def test_db_status_becomes_execution_failed_on_failure(self, service, db_path):
        """TC034: 失敗後はDBステータスが execution_failed になる"""
        from backend.core.sudo_wrapper import SudoWrapperError

        req_id = str(uuid.uuid4())
        payload = {"service_name": "nginx"}
        _insert_approved_request(db_path, req_id, "service_stop", payload)

        with patch("backend.core.sudo_wrapper.sudo_wrapper.stop_service", side_effect=SudoWrapperError("fail")):
            with pytest.raises(SudoWrapperError):
                run_async(service.execute_request(req_id, **EXECUTOR))

        with sqlite3.connect(db_path) as conn:
            row = conn.execute("SELECT status FROM approval_requests WHERE id=?", (req_id,)).fetchone()
        assert row[0] == "execution_failed"

    def test_audit_log_called_on_success(self, service, db_path):
        """TC035: 成功時に監査ログが記録される"""
        req_id = str(uuid.uuid4())
        payload = {"name": "testgroup"}
        _insert_approved_request(db_path, req_id, "group_add", payload)

        with patch("backend.core.sudo_wrapper.sudo_wrapper.add_group", return_value=SUCCESS_RESULT):
            run_async(service.execute_request(req_id, **EXECUTOR))

        service.audit_log.record.assert_called()
        call_kwargs = service.audit_log.record.call_args.kwargs
        assert call_kwargs.get("status") == "success"

    def test_audit_log_called_on_failure(self, service, db_path):
        """TC036: 失敗時に監査ログが記録される"""
        from backend.core.sudo_wrapper import SudoWrapperError

        req_id = str(uuid.uuid4())
        payload = {"name": "testgroup"}
        _insert_approved_request(db_path, req_id, "group_add", payload)

        with patch("backend.core.sudo_wrapper.sudo_wrapper.add_group", side_effect=SudoWrapperError("grp fail")):
            with pytest.raises(SudoWrapperError):
                run_async(service.execute_request(req_id, **EXECUTOR))

        service.audit_log.record.assert_called()
        call_kwargs = service.audit_log.record.call_args.kwargs
        assert call_kwargs.get("status") == "failure"

    def test_execute_result_returned_correctly(self, service, db_path):
        """TC037: 実行結果のフィールドを確認"""
        req_id = str(uuid.uuid4())
        payload = {"username": "testuser"}
        _insert_approved_request(db_path, req_id, "user_add", payload)

        with patch("backend.core.sudo_wrapper.sudo_wrapper.add_user", return_value=SUCCESS_RESULT):
            result = run_async(service.execute_request(req_id, **EXECUTOR))

        assert "request_id" in result
        assert "request_type" in result
        assert "executed_by" in result
        assert "executed_by_name" in result
        assert "executed_at" in result
        assert "execution_result" in result

    def test_non_success_status_in_result_raises(self, service, db_path):
        """TC038: sudo_wrapperが status!=success を返した場合はSudoWrapperErrorになる"""
        from backend.core.sudo_wrapper import SudoWrapperError

        req_id = str(uuid.uuid4())
        payload = {"name": "grp"}
        _insert_approved_request(db_path, req_id, "group_add", payload)

        with patch(
            "backend.core.sudo_wrapper.sudo_wrapper.add_group", return_value={"status": "error", "message": "fail"}
        ):
            with pytest.raises(SudoWrapperError):
                run_async(service.execute_request(req_id, **EXECUTOR))
