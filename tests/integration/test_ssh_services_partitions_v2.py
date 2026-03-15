"""
SSH / Services / Partitions モジュール - カバレッジ改善テスト v2

対象:
  - backend/api/routes/ssh.py        (未カバー: 行91-99, 126-134)
  - backend/api/routes/services.py   (未カバー: 行80-106)
  - backend/api/routes/partitions.py (未カバー: 行94-96, 124-126, 157-159)

目標: 各モジュール 95% 以上

重点:
  - SudoWrapperError 例外ハンドラ分岐
  - 汎用 Exception ハンドラ分岐
  - services の result["status"]=="error" 分岐と成功分岐
  - partitions 3 エンドポイントの SudoWrapperError 分岐
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.core.sudo_wrapper import SudoWrapperError


def _errmsg(resp) -> str:
    """エラーレスポンスからメッセージを取得（detail または message）"""
    body = resp.json()
    return body.get("detail") or body.get("message", "")


# ===================================================================
# フィクスチャ
# ===================================================================


@pytest.fixture
def client():
    from backend.api.main import app
    from fastapi.testclient import TestClient

    return TestClient(app)


@pytest.fixture
def _admin_token(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin123"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def _admin_headers(_admin_token):
    return {"Authorization": f"Bearer {_admin_token}"}


@pytest.fixture
def _operator_token(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "operator@example.com", "password": "operator123"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def _operator_headers(_operator_token):
    return {"Authorization": f"Bearer {_operator_token}"}


# ===================================================================
# SSH テスト - SudoWrapperError & Exception 分岐
# ===================================================================


class TestSSHStatusErrorBranches:
    """ssh.py 行91-99: get_ssh_status の例外ハンドラ"""

    def test_sudo_wrapper_error_returns_503(self, client, _admin_headers):
        """SudoWrapperError → HTTP 503"""
        with patch(
            "backend.api.routes.ssh.sudo_wrapper.get_ssh_status",
            side_effect=SudoWrapperError("sshd not found"),
        ):
            resp = client.get("/api/ssh/status", headers=_admin_headers)
        assert resp.status_code == 503
        body = resp.json()
        msg = body.get("detail") or body.get("message", "")
        assert "SSH状態取得エラー" in msg
        assert "sshd not found" in msg

    def test_generic_exception_returns_500(self, client, _admin_headers):
        """RuntimeError → HTTP 500"""
        with patch(
            "backend.api.routes.ssh.sudo_wrapper.get_ssh_status",
            side_effect=RuntimeError("segfault"),
        ):
            resp = client.get("/api/ssh/status", headers=_admin_headers)
        assert resp.status_code == 500
        assert "内部エラー" in _errmsg(resp)

    def test_type_error_returns_500(self, client, _admin_headers):
        """TypeError → HTTP 500"""
        with patch(
            "backend.api.routes.ssh.sudo_wrapper.get_ssh_status",
            side_effect=TypeError("NoneType"),
        ):
            resp = client.get("/api/ssh/status", headers=_admin_headers)
        assert resp.status_code == 500

    def test_value_error_returns_500(self, client, _admin_headers):
        """ValueError → HTTP 500"""
        with patch(
            "backend.api.routes.ssh.sudo_wrapper.get_ssh_status",
            side_effect=ValueError("bad value"),
        ):
            resp = client.get("/api/ssh/status", headers=_admin_headers)
        assert resp.status_code == 500

    def test_key_error_returns_500(self, client, _admin_headers):
        """KeyError → HTTP 500"""
        with patch(
            "backend.api.routes.ssh.sudo_wrapper.get_ssh_status",
            side_effect=KeyError("missing_key"),
        ):
            resp = client.get("/api/ssh/status", headers=_admin_headers)
        assert resp.status_code == 500

    def test_sudo_wrapper_error_logs_error(self, client, _admin_headers):
        """SudoWrapperError 時にログ出力される"""
        with patch("backend.api.routes.ssh.logger") as mock_logger:
            with patch(
                "backend.api.routes.ssh.sudo_wrapper.get_ssh_status",
                side_effect=SudoWrapperError("connection refused"),
            ):
                resp = client.get("/api/ssh/status", headers=_admin_headers)
        assert resp.status_code == 503
        mock_logger.error.assert_called()

    def test_generic_exception_logs_error(self, client, _admin_headers):
        """汎用例外時にログ出力される"""
        with patch("backend.api.routes.ssh.logger") as mock_logger:
            with patch(
                "backend.api.routes.ssh.sudo_wrapper.get_ssh_status",
                side_effect=OSError("disk failure"),
            ):
                resp = client.get("/api/ssh/status", headers=_admin_headers)
        assert resp.status_code == 500
        mock_logger.error.assert_called()


class TestSSHConfigErrorBranches:
    """ssh.py 行126-134: get_ssh_config の例外ハンドラ"""

    def test_sudo_wrapper_error_returns_503(self, client, _admin_headers):
        """SudoWrapperError → HTTP 503"""
        with patch(
            "backend.api.routes.ssh.sudo_wrapper.get_ssh_config",
            side_effect=SudoWrapperError("permission denied"),
        ):
            resp = client.get("/api/ssh/config", headers=_admin_headers)
        assert resp.status_code == 503
        assert "SSH設定取得エラー" in _errmsg(resp)
        assert "permission denied" in _errmsg(resp)

    def test_generic_exception_returns_500(self, client, _admin_headers):
        """RuntimeError → HTTP 500"""
        with patch(
            "backend.api.routes.ssh.sudo_wrapper.get_ssh_config",
            side_effect=RuntimeError("config parse error"),
        ):
            resp = client.get("/api/ssh/config", headers=_admin_headers)
        assert resp.status_code == 500
        assert "内部エラー" in _errmsg(resp)

    def test_os_error_returns_500(self, client, _admin_headers):
        """OSError → HTTP 500"""
        with patch(
            "backend.api.routes.ssh.sudo_wrapper.get_ssh_config",
            side_effect=OSError("file not found"),
        ):
            resp = client.get("/api/ssh/config", headers=_admin_headers)
        assert resp.status_code == 500

    def test_json_decode_error_returns_500(self, client, _admin_headers):
        """parse_wrapper_result 内で JSONDecodeError → Exception ハンドラ"""
        with patch(
            "backend.api.routes.ssh.sudo_wrapper.get_ssh_config",
            return_value={"output": "not-valid-json{{{"},
        ):
            # parse_wrapper_result は JSONDecodeError を飲み込んで result をそのまま返す
            # しかし返されたdictにtimestamp等がないとValidationError→500
            resp = client.get("/api/ssh/config", headers=_admin_headers)
        # ValidationError は Exception にキャッチされるか FastAPI が 422 を返す
        assert resp.status_code in (422, 500)

    def test_sudo_wrapper_error_logs_error(self, client, _admin_headers):
        """SudoWrapperError 時にログ出力される"""
        with patch("backend.api.routes.ssh.logger") as mock_logger:
            with patch(
                "backend.api.routes.ssh.sudo_wrapper.get_ssh_config",
                side_effect=SudoWrapperError("timeout"),
            ):
                resp = client.get("/api/ssh/config", headers=_admin_headers)
        assert resp.status_code == 503
        mock_logger.error.assert_called()

    def test_generic_exception_logs_error(self, client, _admin_headers):
        """汎用例外時にログ出力される"""
        with patch("backend.api.routes.ssh.logger") as mock_logger:
            with patch(
                "backend.api.routes.ssh.sudo_wrapper.get_ssh_config",
                side_effect=ValueError("unexpected"),
            ):
                resp = client.get("/api/ssh/config", headers=_admin_headers)
        assert resp.status_code == 500
        mock_logger.error.assert_called()


class TestSSHStatusSuccess:
    """ssh.py 正常系: parse_wrapper_result 経由での成功レスポンス"""

    def test_status_with_json_output_field(self, client, _admin_headers):
        """output フィールドが JSON 文字列の場合パースされる"""
        json_output = json.dumps({
            "status": "success",
            "service": "sshd",
            "active_state": "active",
            "enabled_state": "enabled",
            "pid": "999",
            "port": "2222",
            "timestamp": "2026-01-01T00:00:00Z",
        })
        with patch(
            "backend.api.routes.ssh.sudo_wrapper.get_ssh_status",
            return_value={"status": "success", "output": json_output},
        ):
            resp = client.get("/api/ssh/status", headers=_admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["port"] == "2222"
        assert data["pid"] == "999"

    def test_config_with_json_output_field(self, client, _admin_headers):
        """output フィールドが JSON 文字列の場合パースされる (config)"""
        json_output = json.dumps({
            "status": "success",
            "config_path": "/etc/ssh/sshd_config",
            "settings": {"Port": "22"},
            "warnings": [],
            "warning_count": 0,
            "critical_count": 0,
            "timestamp": "2026-01-01T00:00:00Z",
        })
        with patch(
            "backend.api.routes.ssh.sudo_wrapper.get_ssh_config",
            return_value={"status": "success", "output": json_output},
        ):
            resp = client.get("/api/ssh/config", headers=_admin_headers)
        assert resp.status_code == 200
        assert resp.json()["warning_count"] == 0

    def test_status_audit_log_recorded(self, client, _admin_headers):
        """成功時に audit_log.record が呼ばれる"""
        with patch("backend.api.routes.ssh.audit_log") as mock_audit:
            with patch(
                "backend.api.routes.ssh.sudo_wrapper.get_ssh_status",
                return_value={
                    "status": "success",
                    "service": "sshd",
                    "active_state": "active",
                    "enabled_state": "enabled",
                    "pid": "1",
                    "port": "22",
                    "timestamp": "2026-01-01T00:00:00Z",
                },
            ):
                resp = client.get("/api/ssh/status", headers=_admin_headers)
        assert resp.status_code == 200
        mock_audit.record.assert_called_once()
        call_kwargs = mock_audit.record.call_args
        assert call_kwargs[1]["operation"] == "ssh_status_read" or \
               call_kwargs.kwargs.get("operation") == "ssh_status_read"

    def test_config_audit_log_recorded(self, client, _admin_headers):
        """config 成功時に audit_log.record が呼ばれる"""
        with patch("backend.api.routes.ssh.audit_log") as mock_audit:
            with patch(
                "backend.api.routes.ssh.sudo_wrapper.get_ssh_config",
                return_value={
                    "status": "success",
                    "config_path": "/etc/ssh/sshd_config",
                    "settings": {},
                    "warnings": [],
                    "warning_count": 0,
                    "critical_count": 0,
                    "timestamp": "2026-01-01T00:00:00Z",
                },
            ):
                resp = client.get("/api/ssh/config", headers=_admin_headers)
        assert resp.status_code == 200
        mock_audit.record.assert_called_once()


# ===================================================================
# Services テスト - result["status"]=="error" と成功分岐
# ===================================================================


class TestServicesErrorStatusBranch:
    """services.py 行80-93: result.get("status") == "error" 分岐"""

    def test_error_status_returns_403(self, client, _operator_headers):
        """wrapper が status=error を返す → HTTP 403"""
        with patch(
            "backend.api.routes.services.sudo_wrapper.restart_service",
            return_value={
                "status": "error",
                "message": "Service 'badservice' is not in the allowed list",
            },
        ):
            resp = client.post(
                "/api/services/restart",
                json={"service_name": "badservice"},
                headers=_operator_headers,
            )
        assert resp.status_code == 403
        assert "not in the allowed list" in _errmsg(resp)

    def test_error_status_without_message(self, client, _operator_headers):
        """wrapper が status=error で message なし → デフォルトメッセージ"""
        with patch(
            "backend.api.routes.services.sudo_wrapper.restart_service",
            return_value={"status": "error"},
        ):
            resp = client.post(
                "/api/services/restart",
                json={"service_name": "badservice"},
                headers=_operator_headers,
            )
        assert resp.status_code == 403
        assert "Service restart denied" in _errmsg(resp)

    def test_error_status_audit_log_denied(self, client, _operator_headers):
        """status=error 時に audit_log に denied が記録される"""
        with patch("backend.api.routes.services.audit_log") as mock_audit:
            with patch(
                "backend.api.routes.services.sudo_wrapper.restart_service",
                return_value={
                    "status": "error",
                    "message": "not allowed",
                },
            ):
                resp = client.post(
                    "/api/services/restart",
                    json={"service_name": "blocked"},
                    headers=_operator_headers,
                )
        assert resp.status_code == 403
        # attempt + denied = 2 回
        assert mock_audit.record.call_count >= 2
        # denied ステータスが含まれることを確認
        denied_calls = [
            c for c in mock_audit.record.call_args_list
            if "denied" in str(c)
        ]
        assert len(denied_calls) >= 1


class TestServicesSuccessBranch:
    """services.py 行95-106: 成功パス"""

    def test_success_returns_before_after(self, client, _operator_headers):
        """成功時に before/after フィールドが返される"""
        with patch(
            "backend.api.routes.services.sudo_wrapper.restart_service",
            return_value={
                "status": "success",
                "service": "nginx",
                "before": "inactive",
                "after": "active",
            },
        ):
            resp = client.post(
                "/api/services/restart",
                json={"service_name": "nginx"},
                headers=_operator_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["before"] == "inactive"
        assert data["after"] == "active"
        assert data["service"] == "nginx"

    def test_success_audit_log_records_attempt_and_success(self, client, _operator_headers):
        """成功時に attempt + success の 2 回 audit_log.record が呼ばれる"""
        with patch("backend.api.routes.services.audit_log") as mock_audit:
            with patch(
                "backend.api.routes.services.sudo_wrapper.restart_service",
                return_value={
                    "status": "success",
                    "service": "apache2",
                    "before": "active",
                    "after": "active",
                },
            ):
                resp = client.post(
                    "/api/services/restart",
                    json={"service_name": "apache2"},
                    headers=_operator_headers,
                )
        assert resp.status_code == 200
        assert mock_audit.record.call_count >= 2
        # success ステータスが含まれることを確認
        success_calls = [
            c for c in mock_audit.record.call_args_list
            if "success" in str(c)
        ]
        assert len(success_calls) >= 1

    def test_success_audit_log_contains_details(self, client, _operator_headers):
        """成功時の audit_log に before/after の details が含まれる"""
        with patch("backend.api.routes.services.audit_log") as mock_audit:
            with patch(
                "backend.api.routes.services.sudo_wrapper.restart_service",
                return_value={
                    "status": "success",
                    "service": "redis",
                    "before": "active",
                    "after": "active",
                },
            ):
                resp = client.post(
                    "/api/services/restart",
                    json={"service_name": "redis"},
                    headers=_operator_headers,
                )
        assert resp.status_code == 200
        # details に before/after が含まれるか確認
        calls_with_details = [
            c for c in mock_audit.record.call_args_list
            if c.kwargs.get("details") and "before" in str(c.kwargs.get("details", {}))
        ]
        assert len(calls_with_details) >= 1


class TestServicesSudoWrapperError:
    """services.py 行108-123: SudoWrapperError 分岐"""

    def test_sudo_wrapper_error_returns_500(self, client, _operator_headers):
        """SudoWrapperError → HTTP 500"""
        with patch(
            "backend.api.routes.services.sudo_wrapper.restart_service",
            side_effect=SudoWrapperError("systemctl not found"),
        ):
            resp = client.post(
                "/api/services/restart",
                json={"service_name": "nginx"},
                headers=_operator_headers,
            )
        assert resp.status_code == 500
        assert "Service restart failed" in _errmsg(resp)

    def test_sudo_wrapper_error_audit_log_failure(self, client, _operator_headers):
        """SudoWrapperError 時に audit_log に failure が記録される"""
        with patch("backend.api.routes.services.audit_log") as mock_audit:
            with patch(
                "backend.api.routes.services.sudo_wrapper.restart_service",
                side_effect=SudoWrapperError("exec error"),
            ):
                resp = client.post(
                    "/api/services/restart",
                    json={"service_name": "nginx"},
                    headers=_operator_headers,
                )
        assert resp.status_code == 500
        # attempt + failure = 2 回
        assert mock_audit.record.call_count >= 2
        failure_calls = [
            c for c in mock_audit.record.call_args_list
            if "failure" in str(c)
        ]
        assert len(failure_calls) >= 1

    def test_sudo_wrapper_error_logs_error(self, client, _operator_headers):
        """SudoWrapperError 時にログ出力される"""
        with patch("backend.api.routes.services.logger") as mock_logger:
            with patch(
                "backend.api.routes.services.sudo_wrapper.restart_service",
                side_effect=SudoWrapperError("timeout"),
            ):
                resp = client.post(
                    "/api/services/restart",
                    json={"service_name": "nginx"},
                    headers=_operator_headers,
                )
        assert resp.status_code == 500
        mock_logger.error.assert_called()


# ===================================================================
# Partitions テスト - SudoWrapperError 分岐
# ===================================================================


class TestPartitionsListErrorBranch:
    """partitions.py 行94-96: get_partitions_list の SudoWrapperError"""

    def test_sudo_wrapper_error_returns_503(self, client, _admin_headers):
        """SudoWrapperError → HTTP 503"""
        with patch(
            "backend.api.routes.partitions.sudo_wrapper.get_partitions_list",
            side_effect=SudoWrapperError("lsblk failed"),
        ):
            resp = client.get("/api/partitions/list", headers=_admin_headers)
        assert resp.status_code == 503
        assert "Partitions list unavailable" in _errmsg(resp)

    def test_sudo_wrapper_error_detail_contains_message(self, client, _admin_headers):
        """503 の detail にエラーメッセージが含まれる"""
        with patch(
            "backend.api.routes.partitions.sudo_wrapper.get_partitions_list",
            side_effect=SudoWrapperError("exec permission denied"),
        ):
            resp = client.get("/api/partitions/list", headers=_admin_headers)
        assert resp.status_code == 503
        assert "exec permission denied" in _errmsg(resp)

    def test_sudo_wrapper_error_logs_error(self, client, _admin_headers):
        """SudoWrapperError 時にログ出力される"""
        with patch("backend.api.routes.partitions.logger") as mock_logger:
            with patch(
                "backend.api.routes.partitions.sudo_wrapper.get_partitions_list",
                side_effect=SudoWrapperError("lsblk error"),
            ):
                resp = client.get("/api/partitions/list", headers=_admin_headers)
        assert resp.status_code == 503
        mock_logger.error.assert_called()


class TestPartitionsUsageErrorBranch:
    """partitions.py 行124-126: get_partitions_usage の SudoWrapperError"""

    def test_sudo_wrapper_error_returns_503(self, client, _admin_headers):
        """SudoWrapperError → HTTP 503"""
        with patch(
            "backend.api.routes.partitions.sudo_wrapper.get_partitions_usage",
            side_effect=SudoWrapperError("df failed"),
        ):
            resp = client.get("/api/partitions/usage", headers=_admin_headers)
        assert resp.status_code == 503
        assert "Partitions usage unavailable" in _errmsg(resp)

    def test_sudo_wrapper_error_detail_contains_message(self, client, _admin_headers):
        """503 の detail にエラーメッセージが含まれる"""
        with patch(
            "backend.api.routes.partitions.sudo_wrapper.get_partitions_usage",
            side_effect=SudoWrapperError("disk IO error"),
        ):
            resp = client.get("/api/partitions/usage", headers=_admin_headers)
        assert resp.status_code == 503
        assert "disk IO error" in _errmsg(resp)

    def test_sudo_wrapper_error_logs_error(self, client, _admin_headers):
        """SudoWrapperError 時にログ出力される"""
        with patch("backend.api.routes.partitions.logger") as mock_logger:
            with patch(
                "backend.api.routes.partitions.sudo_wrapper.get_partitions_usage",
                side_effect=SudoWrapperError("df error"),
            ):
                resp = client.get("/api/partitions/usage", headers=_admin_headers)
        assert resp.status_code == 503
        mock_logger.error.assert_called()


class TestPartitionsDetailErrorBranch:
    """partitions.py 行157-159: get_partitions_detail の SudoWrapperError"""

    def test_sudo_wrapper_error_returns_503(self, client, _admin_headers):
        """SudoWrapperError → HTTP 503"""
        with patch(
            "backend.api.routes.partitions.sudo_wrapper.get_partitions_detail",
            side_effect=SudoWrapperError("blkid failed"),
        ):
            resp = client.get("/api/partitions/detail", headers=_admin_headers)
        assert resp.status_code == 503
        assert "Partitions detail unavailable" in _errmsg(resp)

    def test_sudo_wrapper_error_detail_contains_message(self, client, _admin_headers):
        """503 の detail にエラーメッセージが含まれる"""
        with patch(
            "backend.api.routes.partitions.sudo_wrapper.get_partitions_detail",
            side_effect=SudoWrapperError("blkid not installed"),
        ):
            resp = client.get("/api/partitions/detail", headers=_admin_headers)
        assert resp.status_code == 503
        assert "blkid not installed" in _errmsg(resp)

    def test_sudo_wrapper_error_logs_error(self, client, _admin_headers):
        """SudoWrapperError 時にログ出力される"""
        with patch("backend.api.routes.partitions.logger") as mock_logger:
            with patch(
                "backend.api.routes.partitions.sudo_wrapper.get_partitions_detail",
                side_effect=SudoWrapperError("blkid error"),
            ):
                resp = client.get("/api/partitions/detail", headers=_admin_headers)
        assert resp.status_code == 503
        mock_logger.error.assert_called()


class TestPartitionsSuccessPaths:
    """partitions.py 正常系: audit_log 記録の確認"""

    def test_list_success_audit_log(self, client, _admin_headers):
        """list 成功時に audit_log.record が呼ばれる"""
        with patch("backend.api.routes.partitions.audit_log") as mock_audit:
            with patch(
                "backend.api.routes.partitions.sudo_wrapper.get_partitions_list",
                return_value={
                    "status": "success",
                    "partitions": [],
                    "timestamp": "2026-01-01T00:00:00Z",
                },
            ):
                resp = client.get("/api/partitions/list", headers=_admin_headers)
        assert resp.status_code == 200
        mock_audit.record.assert_called_once()

    def test_usage_success_audit_log(self, client, _admin_headers):
        """usage 成功時に audit_log.record が呼ばれる"""
        with patch("backend.api.routes.partitions.audit_log") as mock_audit:
            with patch(
                "backend.api.routes.partitions.sudo_wrapper.get_partitions_usage",
                return_value={
                    "status": "success",
                    "usage_raw": "/dev/sda1 100G",
                    "timestamp": "2026-01-01T00:00:00Z",
                },
            ):
                resp = client.get("/api/partitions/usage", headers=_admin_headers)
        assert resp.status_code == 200
        mock_audit.record.assert_called_once()

    def test_detail_success_audit_log(self, client, _admin_headers):
        """detail 成功時に audit_log.record が呼ばれる"""
        with patch("backend.api.routes.partitions.audit_log") as mock_audit:
            with patch(
                "backend.api.routes.partitions.sudo_wrapper.get_partitions_detail",
                return_value={
                    "status": "success",
                    "blkid_raw": '/dev/sda1: UUID="abc"',
                    "timestamp": "2026-01-01T00:00:00Z",
                },
            ):
                resp = client.get("/api/partitions/detail", headers=_admin_headers)
        assert resp.status_code == 200
        mock_audit.record.assert_called_once()

    def test_list_with_json_output(self, client, _admin_headers):
        """output フィールドが JSON 文字列でもパースされる"""
        json_output = json.dumps({
            "status": "success",
            "partitions": {"blockdevices": []},
            "timestamp": "2026-01-01T00:00:00Z",
        })
        with patch(
            "backend.api.routes.partitions.sudo_wrapper.get_partitions_list",
            return_value={"status": "success", "output": json_output},
        ):
            resp = client.get("/api/partitions/list", headers=_admin_headers)
        assert resp.status_code == 200

    def test_usage_with_json_output(self, client, _admin_headers):
        """usage: output フィールドが JSON 文字列でもパースされる"""
        json_output = json.dumps({
            "status": "success",
            "usage_raw": "/dev/sda1 50G 10G 40G 20% /",
            "timestamp": "2026-01-01T00:00:00Z",
        })
        with patch(
            "backend.api.routes.partitions.sudo_wrapper.get_partitions_usage",
            return_value={"status": "success", "output": json_output},
        ):
            resp = client.get("/api/partitions/usage", headers=_admin_headers)
        assert resp.status_code == 200

    def test_detail_with_json_output(self, client, _admin_headers):
        """detail: output フィールドが JSON 文字列でもパースされる"""
        json_output = json.dumps({
            "status": "success",
            "blkid_raw": '/dev/sda1: UUID="test-uuid" TYPE="ext4"',
            "timestamp": "2026-01-01T00:00:00Z",
        })
        with patch(
            "backend.api.routes.partitions.sudo_wrapper.get_partitions_detail",
            return_value={"status": "success", "output": json_output},
        ):
            resp = client.get("/api/partitions/detail", headers=_admin_headers)
        assert resp.status_code == 200
