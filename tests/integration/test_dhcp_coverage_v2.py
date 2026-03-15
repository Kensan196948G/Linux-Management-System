"""
DHCP Server API カバレッジ改善テスト v2

対象: backend/api/routes/dhcp.py
目標: 90%以上のカバレッジ
既存テスト (test_dhcp_api.py, test_dhcp_coverage.py) で不足しているパスを網羅する。
"""

from unittest.mock import patch

import pytest

from backend.core.sudo_wrapper import SudoWrapperError


def _get_error_message(resp):
    """レスポンスからエラーメッセージを取得 (detail or message)"""
    body = resp.json()
    return body.get("detail") or body.get("message") or ""


# =====================================================================
# /status - 全分岐カバー (lines 18-34)
# =====================================================================


class TestDhcpStatusV2:
    """DHCP ステータスの追加分岐テスト"""

    def test_status_success_data_passthrough(self, test_client, admin_headers):
        """sudo_wrapper の返却データがそのまま data に入ること"""
        mock_data = {
            "status": "running",
            "version": "isc-dhcpd-4.4.3",
            "service": "isc-dhcp-server",
            "uptime": "5 days",
            "extra_field": "custom_value",
        }
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_status",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/dhcp/status", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["extra_field"] == "custom_value"
        assert body["data"]["uptime"] == "5 days"

    def test_status_audit_log_called_with_user_id(self, test_client, admin_headers):
        """audit_log.record に user_id が渡されること"""
        mock_data = {"status": "running", "version": "4.4.3"}
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_status",
            return_value=mock_data,
        ):
            with patch("backend.api.routes.dhcp.audit_log") as mock_audit:
                resp = test_client.get("/api/dhcp/status", headers=admin_headers)
        assert resp.status_code == 200
        call_args = mock_audit.record.call_args[0]
        assert call_args[0] == "dhcp_status_view"
        # user_id is the second argument
        assert call_args[1] is not None
        assert call_args[2] == "dhcp"
        assert call_args[3] == "success"

    def test_status_unavailable_triggers_http_exception(self, test_client, admin_headers):
        """status=unavailable のとき 503 + audit_log は success で呼ばれてから HTTPException"""
        mock_data = {"status": "unavailable"}
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_status",
            return_value=mock_data,
        ):
            with patch("backend.api.routes.dhcp.audit_log") as mock_audit:
                resp = test_client.get("/api/dhcp/status", headers=admin_headers)
        assert resp.status_code == 503
        # audit_log.record は unavailable チェック前に呼ばれる
        mock_audit.record.assert_called_once()

    def test_status_wrapper_error_audit_failure(self, test_client, admin_headers):
        """SudoWrapperError 時に audit_log が failure で記録"""
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_status",
            side_effect=SudoWrapperError("connection error"),
        ):
            with patch("backend.api.routes.dhcp.audit_log") as mock_audit:
                resp = test_client.get("/api/dhcp/status", headers=admin_headers)
        assert resp.status_code == 503
        call_args = mock_audit.record.call_args[0]
        assert call_args[0] == "dhcp_status_view"
        assert call_args[3] == "failure"

    def test_status_operator_access(self, test_client, operator_headers):
        """operator ロールでもステータス取得可能"""
        mock_data = {"status": "running", "version": "4.4.3"}
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_status",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/dhcp/status", headers=operator_headers)
        assert resp.status_code == 200


# =====================================================================
# /leases - 全分岐カバー (lines 37-53)
# =====================================================================


class TestDhcpLeasesV2:
    """DHCP リースの追加分岐テスト"""

    def test_leases_audit_log_user_id(self, test_client, admin_headers):
        """audit_log に正しいアクション名と dhcp ターゲットが渡されること"""
        mock_data = {"leases": [], "total": 0}
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_leases",
            return_value=mock_data,
        ):
            with patch("backend.api.routes.dhcp.audit_log") as mock_audit:
                resp = test_client.get("/api/dhcp/leases", headers=admin_headers)
        assert resp.status_code == 200
        call_args = mock_audit.record.call_args[0]
        assert call_args[0] == "dhcp_leases_view"
        assert call_args[2] == "dhcp"

    def test_leases_unavailable_503(self, test_client, admin_headers):
        """status=unavailable -> 503"""
        mock_data = {"status": "unavailable"}
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_leases",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/dhcp/leases", headers=admin_headers)
        assert resp.status_code == 503
        assert "インストールされていません" in _get_error_message(resp)

    def test_leases_wrapper_error_detail(self, test_client, admin_headers):
        """SudoWrapperError のメッセージが detail に含まれること"""
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_leases",
            side_effect=SudoWrapperError("permission denied"),
        ):
            with patch("backend.api.routes.dhcp.audit_log") as mock_audit:
                resp = test_client.get("/api/dhcp/leases", headers=admin_headers)
        assert resp.status_code == 503
        assert "permission denied" in _get_error_message(resp)
        assert mock_audit.record.call_args[0][3] == "failure"

    def test_leases_operator_access(self, test_client, operator_headers):
        """operator ロールでもリース取得可能"""
        mock_data = {"leases": [{"ip": "10.0.0.1"}], "total": 1}
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_leases",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/dhcp/leases", headers=operator_headers)
        assert resp.status_code == 200


# =====================================================================
# /config - 全分岐カバー (lines 56-72)
# =====================================================================


class TestDhcpConfigV2:
    """DHCP 設定の追加分岐テスト"""

    def test_config_audit_log_user_id(self, test_client, admin_headers):
        """audit_log に正しいアクション名と dhcp ターゲットが渡されること"""
        mock_data = {"subnets": [], "total": 0}
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_config",
            return_value=mock_data,
        ):
            with patch("backend.api.routes.dhcp.audit_log") as mock_audit:
                resp = test_client.get("/api/dhcp/config", headers=admin_headers)
        assert resp.status_code == 200
        call_args = mock_audit.record.call_args[0]
        assert call_args[0] == "dhcp_config_view"
        assert call_args[2] == "dhcp"

    def test_config_unavailable_503(self, test_client, admin_headers):
        """status=unavailable -> 503"""
        mock_data = {"status": "unavailable"}
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_config",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/dhcp/config", headers=admin_headers)
        assert resp.status_code == 503

    def test_config_wrapper_error_detail(self, test_client, admin_headers):
        """SudoWrapperError のメッセージが detail に含まれる"""
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_config",
            side_effect=SudoWrapperError("timeout reading config"),
        ):
            with patch("backend.api.routes.dhcp.audit_log") as mock_audit:
                resp = test_client.get("/api/dhcp/config", headers=admin_headers)
        assert resp.status_code == 503
        assert "timeout reading config" in _get_error_message(resp)
        assert mock_audit.record.call_args[0][3] == "failure"

    def test_config_operator_access(self, test_client, operator_headers):
        """operator ロールでも設定取得可能"""
        mock_data = {"subnets": [], "total": 0}
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_config",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/dhcp/config", headers=operator_headers)
        assert resp.status_code == 200


# =====================================================================
# /pools - 全分岐カバー (lines 75-91)
# =====================================================================


class TestDhcpPoolsV2:
    """DHCP プールの追加分岐テスト"""

    def test_pools_audit_log_user_id(self, test_client, admin_headers):
        """audit_log に正しいアクション名と dhcp ターゲットが渡されること"""
        mock_data = {"pools": [], "total": 0}
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_pools",
            return_value=mock_data,
        ):
            with patch("backend.api.routes.dhcp.audit_log") as mock_audit:
                resp = test_client.get("/api/dhcp/pools", headers=admin_headers)
        assert resp.status_code == 200
        call_args = mock_audit.record.call_args[0]
        assert call_args[0] == "dhcp_pools_view"
        assert call_args[2] == "dhcp"

    def test_pools_unavailable_503(self, test_client, admin_headers):
        """status=unavailable -> 503"""
        mock_data = {"status": "unavailable"}
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_pools",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/dhcp/pools", headers=admin_headers)
        assert resp.status_code == 503

    def test_pools_wrapper_error_detail(self, test_client, admin_headers):
        """SudoWrapperError のメッセージが detail に含まれる"""
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_pools",
            side_effect=SudoWrapperError("no dhcpd process"),
        ):
            with patch("backend.api.routes.dhcp.audit_log") as mock_audit:
                resp = test_client.get("/api/dhcp/pools", headers=admin_headers)
        assert resp.status_code == 503
        assert "no dhcpd process" in _get_error_message(resp)
        assert mock_audit.record.call_args[0][3] == "failure"

    def test_pools_operator_access(self, test_client, operator_headers):
        """operator ロールでもプール取得可能"""
        mock_data = {"pools": [], "total": 0}
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_pools",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/dhcp/pools", headers=operator_headers)
        assert resp.status_code == 200


# =====================================================================
# /logs - 全分岐カバー (lines 94-111)
# =====================================================================


class TestDhcpLogsV2:
    """DHCP ログの追加分岐テスト"""

    def test_logs_audit_log_user_id(self, test_client, admin_headers):
        """audit_log に正しいアクション名と dhcp ターゲットが渡されること"""
        mock_data = {"logs": "log line\n", "lines": 50}
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_logs",
            return_value=mock_data,
        ):
            with patch("backend.api.routes.dhcp.audit_log") as mock_audit:
                resp = test_client.get("/api/dhcp/logs", headers=admin_headers)
        assert resp.status_code == 200
        call_args = mock_audit.record.call_args[0]
        assert call_args[0] == "dhcp_logs_view"
        assert call_args[2] == "dhcp"

    def test_logs_unavailable_503(self, test_client, admin_headers):
        """status=unavailable -> 503"""
        mock_data = {"status": "unavailable"}
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_logs",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/dhcp/logs", headers=admin_headers)
        assert resp.status_code == 503
        assert "インストールされていません" in _get_error_message(resp)

    def test_logs_wrapper_error_detail(self, test_client, admin_headers):
        """SudoWrapperError のメッセージが detail に含まれる"""
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_logs",
            side_effect=SudoWrapperError("log file locked"),
        ):
            with patch("backend.api.routes.dhcp.audit_log") as mock_audit:
                resp = test_client.get("/api/dhcp/logs", headers=admin_headers)
        assert resp.status_code == 503
        assert "log file locked" in _get_error_message(resp)
        assert mock_audit.record.call_args[0][3] == "failure"

    def test_logs_operator_access(self, test_client, operator_headers):
        """operator ロールでもログ取得可能"""
        mock_data = {"logs": "", "lines": 50}
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_logs",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/dhcp/logs", headers=operator_headers)
        assert resp.status_code == 200

    @pytest.mark.parametrize("lines_val", [1, 50, 100, 200])
    def test_logs_various_lines(self, lines_val, test_client, admin_headers):
        """異なる lines 値で正常動作"""
        mock_data = {"logs": "", "lines": lines_val}
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_logs",
            return_value=mock_data,
        ) as mock_fn:
            resp = test_client.get(
                f"/api/dhcp/logs?lines={lines_val}", headers=admin_headers
            )
        assert resp.status_code == 200
        mock_fn.assert_called_once_with(lines=lines_val)

    @pytest.mark.parametrize("bad_lines", [0, -1, 201, 1000])
    def test_logs_invalid_lines_422(self, bad_lines, test_client, admin_headers):
        """不正な lines 値 -> 422"""
        resp = test_client.get(
            f"/api/dhcp/logs?lines={bad_lines}", headers=admin_headers
        )
        assert resp.status_code == 422


# =====================================================================
# HTTPException 再送出パス (全エンドポイント)
# =====================================================================


class TestDhcpHTTPExceptionReraiseV2:
    """HTTPException が再送出されることの網羅テスト"""

    @pytest.mark.parametrize(
        "endpoint,wrapper_method,status_code",
        [
            ("/api/dhcp/status", "get_dhcp_status", 429),
            ("/api/dhcp/leases", "get_dhcp_leases", 502),
            ("/api/dhcp/config", "get_dhcp_config", 503),
            ("/api/dhcp/pools", "get_dhcp_pools", 500),
            ("/api/dhcp/logs", "get_dhcp_logs", 504),
        ],
    )
    def test_http_exception_reraise(
        self, endpoint, wrapper_method, status_code, test_client, admin_headers
    ):
        """各エンドポイントで HTTPException が再送出されること"""
        from fastapi import HTTPException

        with patch(
            f"backend.api.routes.dhcp.sudo_wrapper.{wrapper_method}",
            side_effect=HTTPException(status_code=status_code, detail="test error"),
        ):
            resp = test_client.get(endpoint, headers=admin_headers)
        assert resp.status_code == status_code


# =====================================================================
# 認証テスト (全エンドポイント)
# =====================================================================


class TestDhcpAuthV2:
    """認証の追加テスト"""

    @pytest.mark.parametrize(
        "endpoint",
        [
            "/api/dhcp/status",
            "/api/dhcp/leases",
            "/api/dhcp/config",
            "/api/dhcp/pools",
            "/api/dhcp/logs",
        ],
    )
    def test_no_auth_header_rejected(self, endpoint, test_client):
        """Authorization ヘッダーなしは拒否"""
        resp = test_client.get(endpoint)
        assert resp.status_code in (401, 403)

    @pytest.mark.parametrize(
        "endpoint",
        [
            "/api/dhcp/status",
            "/api/dhcp/leases",
            "/api/dhcp/config",
            "/api/dhcp/pools",
            "/api/dhcp/logs",
        ],
    )
    def test_empty_bearer_rejected(self, endpoint, test_client):
        """空の Bearer トークンは拒否"""
        resp = test_client.get(
            endpoint, headers={"Authorization": "Bearer "}
        )
        assert resp.status_code in (401, 403)


# =====================================================================
# 全エンドポイント成功パス parametrize テスト
# =====================================================================


class TestDhcpAllEndpointsSuccess:
    """全エンドポイントの正常系を parametrize でテスト"""

    @pytest.mark.parametrize(
        "endpoint,wrapper_method,mock_data",
        [
            (
                "/api/dhcp/status",
                "get_dhcp_status",
                {"status": "running", "version": "4.4.3"},
            ),
            (
                "/api/dhcp/leases",
                "get_dhcp_leases",
                {"leases": [{"ip": "10.0.0.1"}], "total": 1},
            ),
            (
                "/api/dhcp/config",
                "get_dhcp_config",
                {"subnets": [{"subnet": "10.0.0.0"}], "total": 1},
            ),
            (
                "/api/dhcp/pools",
                "get_dhcp_pools",
                {"pools": [{"subnet": "10.0.0.0/24"}], "total": 1},
            ),
            (
                "/api/dhcp/logs",
                "get_dhcp_logs",
                {"logs": "line1\n", "lines": 50},
            ),
        ],
    )
    def test_success_returns_200_with_data(
        self, endpoint, wrapper_method, mock_data, test_client, admin_headers
    ):
        """全エンドポイントで success: True と data が返ること"""
        with patch(
            f"backend.api.routes.dhcp.sudo_wrapper.{wrapper_method}",
            return_value=mock_data,
        ):
            resp = test_client.get(endpoint, headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "data" in body

    @pytest.mark.parametrize(
        "endpoint,wrapper_method",
        [
            ("/api/dhcp/status", "get_dhcp_status"),
            ("/api/dhcp/leases", "get_dhcp_leases"),
            ("/api/dhcp/config", "get_dhcp_config"),
            ("/api/dhcp/pools", "get_dhcp_pools"),
            ("/api/dhcp/logs", "get_dhcp_logs"),
        ],
    )
    def test_unavailable_returns_503(
        self, endpoint, wrapper_method, test_client, admin_headers
    ):
        """全エンドポイントで status=unavailable -> 503"""
        mock_data = {"status": "unavailable"}
        with patch(
            f"backend.api.routes.dhcp.sudo_wrapper.{wrapper_method}",
            return_value=mock_data,
        ):
            resp = test_client.get(endpoint, headers=admin_headers)
        assert resp.status_code == 503

    @pytest.mark.parametrize(
        "endpoint,wrapper_method",
        [
            ("/api/dhcp/status", "get_dhcp_status"),
            ("/api/dhcp/leases", "get_dhcp_leases"),
            ("/api/dhcp/config", "get_dhcp_config"),
            ("/api/dhcp/pools", "get_dhcp_pools"),
            ("/api/dhcp/logs", "get_dhcp_logs"),
        ],
    )
    def test_wrapper_error_returns_503(
        self, endpoint, wrapper_method, test_client, admin_headers
    ):
        """全エンドポイントで SudoWrapperError -> 503"""
        with patch(
            f"backend.api.routes.dhcp.sudo_wrapper.{wrapper_method}",
            side_effect=SudoWrapperError("test error"),
        ):
            resp = test_client.get(endpoint, headers=admin_headers)
        assert resp.status_code == 503


# =====================================================================
# logger テスト
# =====================================================================


class TestDhcpLogger:
    """logger.error が呼ばれることのテスト"""

    @pytest.mark.parametrize(
        "endpoint,wrapper_method",
        [
            ("/api/dhcp/status", "get_dhcp_status"),
            ("/api/dhcp/leases", "get_dhcp_leases"),
            ("/api/dhcp/config", "get_dhcp_config"),
            ("/api/dhcp/pools", "get_dhcp_pools"),
            ("/api/dhcp/logs", "get_dhcp_logs"),
        ],
    )
    def test_logger_error_called_on_wrapper_error(
        self, endpoint, wrapper_method, test_client, admin_headers
    ):
        """SudoWrapperError 時に logger.error が呼ばれること"""
        with patch(
            f"backend.api.routes.dhcp.sudo_wrapper.{wrapper_method}",
            side_effect=SudoWrapperError("test"),
        ):
            with patch("backend.api.routes.dhcp.logger") as mock_logger:
                resp = test_client.get(endpoint, headers=admin_headers)
        assert resp.status_code == 503
        mock_logger.error.assert_called_once()
