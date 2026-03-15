"""
DHCP Server API カバレッジ拡張テスト

dhcp.py のカバレッジを 80%+ に引き上げるための追加テスト。
既存 test_dhcp_api.py と重複しない新規テストに集中する。
"""

from unittest.mock import patch

import pytest

from backend.core.sudo_wrapper import SudoWrapperError


# ==============================================================================
# /status 追加テスト
# ==============================================================================


class TestDhcpStatusExtra:
    """DHCP ステータスの追加カバレッジテスト"""

    def test_status_success_returns_data_structure(self, test_client, admin_headers):
        """正常レスポンスが success: True と data を含むこと"""
        mock_data = {
            "status": "running",
            "version": "isc-dhcpd-4.4.3",
            "service": "isc-dhcp-server",
            "uptime": "2 days",
        }
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_status",
            return_value=mock_data,
        ):
            with patch("backend.api.routes.dhcp.audit_log") as mock_audit:  # noqa: F841
                resp = test_client.get("/api/dhcp/status", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["version"] == "isc-dhcpd-4.4.3"
        assert body["data"]["uptime"] == "2 days"

    def test_status_audit_log_success(self, test_client, admin_headers):
        """正常時に audit_log.record が success で呼ばれること"""
        mock_data = {"status": "running", "version": "isc-dhcpd-4.4.3"}
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_status",
            return_value=mock_data,
        ):
            with patch("backend.api.routes.dhcp.audit_log") as mock_audit:  # noqa: F841
                resp = test_client.get("/api/dhcp/status", headers=admin_headers)
        assert resp.status_code == 200
        mock_audit.record.assert_called()
        call_args = mock_audit.record.call_args
        assert call_args[0][0] == "dhcp_status_view"
        assert call_args[0][3] == "success"

    def test_status_audit_log_failure_on_wrapper_error(
        self, test_client, admin_headers
    ):
        """SudoWrapperError 時に audit_log.record が failure で呼ばれること"""
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_status",
            side_effect=SudoWrapperError("wrapper failed"),
        ):
            with patch("backend.api.routes.dhcp.audit_log") as mock_audit:  # noqa: F841
                resp = test_client.get("/api/dhcp/status", headers=admin_headers)
        assert resp.status_code == 503
        mock_audit.record.assert_called()
        call_args = mock_audit.record.call_args
        assert call_args[0][0] == "dhcp_status_view"
        assert call_args[0][3] == "failure"

    def test_status_error_detail_contains_message(self, test_client, admin_headers):
        """SudoWrapperError のメッセージが detail に含まれること"""
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_status",
            side_effect=SudoWrapperError("connection refused"),
        ):
            resp = test_client.get("/api/dhcp/status", headers=admin_headers)
        assert resp.status_code == 503
        body = resp.json()
        msg = body.get("detail") or body.get("message") or ""
        assert "connection refused" in msg

    def test_status_unavailable_detail_message(self, test_client, admin_headers):
        """unavailable 時の detail メッセージが正しいこと"""
        mock_data = {"status": "unavailable", "message": "not installed"}
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_status",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/dhcp/status", headers=admin_headers)
        assert resp.status_code == 503
        body = resp.json()
        msg = body.get("detail") or body.get("message") or ""
        assert "インストールされていません" in msg

    def test_status_viewer_role_access(self, test_client, viewer_headers):
        """viewer ロールでもステータス取得可能"""
        mock_data = {"status": "running", "version": "4.4.3"}
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_status",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/dhcp/status", headers=viewer_headers)
        assert resp.status_code == 200


# ==============================================================================
# /leases 追加テスト
# ==============================================================================


class TestDhcpLeasesExtra:
    """DHCP リースの追加カバレッジテスト"""

    def test_leases_audit_log_success(self, test_client, admin_headers):
        """正常時に audit_log が dhcp_leases_view/success で記録されること"""
        mock_data = {"leases": [], "total": 0}
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_leases",
            return_value=mock_data,
        ):
            with patch("backend.api.routes.dhcp.audit_log") as mock_audit:  # noqa: F841
                resp = test_client.get("/api/dhcp/leases", headers=admin_headers)
        assert resp.status_code == 200
        mock_audit.record.assert_called()
        assert mock_audit.record.call_args[0][0] == "dhcp_leases_view"
        assert mock_audit.record.call_args[0][3] == "success"

    def test_leases_audit_log_failure(self, test_client, admin_headers):
        """SudoWrapperError 時に audit_log が failure で記録されること"""
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_leases",
            side_effect=SudoWrapperError("leases read failed"),
        ):
            with patch("backend.api.routes.dhcp.audit_log") as mock_audit:  # noqa: F841
                resp = test_client.get("/api/dhcp/leases", headers=admin_headers)
        assert resp.status_code == 503
        assert mock_audit.record.call_args[0][3] == "failure"

    def test_leases_error_detail(self, test_client, admin_headers):
        """SudoWrapperError のメッセージが detail に含まれること"""
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_leases",
            side_effect=SudoWrapperError("timeout"),
        ):
            resp = test_client.get("/api/dhcp/leases", headers=admin_headers)
        assert resp.status_code == 503
        body = resp.json()
        msg = body.get("detail") or body.get("message") or ""
        assert "timeout" in msg

    def test_leases_empty_list(self, test_client, admin_headers):
        """リースが空でも正常にレスポンスが返ること"""
        mock_data = {"leases": [], "total": 0}
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_leases",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/dhcp/leases", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["leases"] == []
        assert body["data"]["total"] == 0

    def test_leases_multiple_entries(self, test_client, admin_headers):
        """複数のリースエントリが返ること"""
        mock_data = {
            "leases": [
                {"ip": "192.168.1.100", "mac": "aa:bb:cc:dd:ee:01", "hostname": "h1"},
                {"ip": "192.168.1.101", "mac": "aa:bb:cc:dd:ee:02", "hostname": "h2"},
                {"ip": "192.168.1.102", "mac": "aa:bb:cc:dd:ee:03", "hostname": "h3"},
            ],
            "total": 3,
        }
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_leases",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/dhcp/leases", headers=admin_headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]["leases"]) == 3

    def test_leases_viewer_role(self, test_client, viewer_headers):
        """viewer ロールでもリース取得可能"""
        mock_data = {"leases": [], "total": 0}
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_leases",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/dhcp/leases", headers=viewer_headers)
        assert resp.status_code == 200


# ==============================================================================
# /config 追加テスト
# ==============================================================================


class TestDhcpConfigExtra:
    """DHCP 設定の追加カバレッジテスト"""

    def test_config_audit_log_success(self, test_client, admin_headers):
        """正常時に audit_log が dhcp_config_view/success で記録されること"""
        mock_data = {"subnets": [], "total": 0}
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_config",
            return_value=mock_data,
        ):
            with patch("backend.api.routes.dhcp.audit_log") as mock_audit:  # noqa: F841
                resp = test_client.get("/api/dhcp/config", headers=admin_headers)
        assert resp.status_code == 200
        assert mock_audit.record.call_args[0][0] == "dhcp_config_view"
        assert mock_audit.record.call_args[0][3] == "success"

    def test_config_audit_log_failure(self, test_client, admin_headers):
        """SudoWrapperError 時に audit_log が failure で記録されること"""
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_config",
            side_effect=SudoWrapperError("config read failed"),
        ):
            with patch("backend.api.routes.dhcp.audit_log") as mock_audit:  # noqa: F841
                resp = test_client.get("/api/dhcp/config", headers=admin_headers)
        assert resp.status_code == 503
        assert mock_audit.record.call_args[0][3] == "failure"

    def test_config_error_detail(self, test_client, admin_headers):
        """SudoWrapperError のメッセージが detail に含まれること"""
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_config",
            side_effect=SudoWrapperError("permission denied"),
        ):
            resp = test_client.get("/api/dhcp/config", headers=admin_headers)
        assert resp.status_code == 503
        body = resp.json()
        msg = body.get("detail") or body.get("message") or ""
        assert "permission denied" in msg

    def test_config_complex_data(self, test_client, admin_headers):
        """複雑な設定データが正常に返ること"""
        mock_data = {
            "subnets": [
                {
                    "subnet": "192.168.1.0",
                    "netmask": "255.255.255.0",
                    "ranges": [
                        {"start": "192.168.1.100", "end": "192.168.1.200"},
                        {"start": "192.168.1.210", "end": "192.168.1.250"},
                    ],
                    "options": {"routers": "192.168.1.1", "dns": "8.8.8.8"},
                },
                {
                    "subnet": "10.0.0.0",
                    "netmask": "255.255.255.0",
                    "ranges": [{"start": "10.0.0.100", "end": "10.0.0.200"}],
                },
            ],
            "total": 2,
        }
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_config",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/dhcp/config", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["subnets"]) == 2
        assert data["total"] == 2

    def test_config_viewer_role(self, test_client, viewer_headers):
        """viewer ロールでも設定取得可能"""
        mock_data = {"subnets": [], "total": 0}
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_config",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/dhcp/config", headers=viewer_headers)
        assert resp.status_code == 200


# ==============================================================================
# /pools 追加テスト
# ==============================================================================


class TestDhcpPoolsExtra:
    """DHCP プールの追加カバレッジテスト"""

    def test_pools_audit_log_success(self, test_client, admin_headers):
        """正常時に audit_log が dhcp_pools_view/success で記録されること"""
        mock_data = {"pools": [], "total": 0}
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_pools",
            return_value=mock_data,
        ):
            with patch("backend.api.routes.dhcp.audit_log") as mock_audit:  # noqa: F841
                resp = test_client.get("/api/dhcp/pools", headers=admin_headers)
        assert resp.status_code == 200
        assert mock_audit.record.call_args[0][0] == "dhcp_pools_view"
        assert mock_audit.record.call_args[0][3] == "success"

    def test_pools_audit_log_failure(self, test_client, admin_headers):
        """SudoWrapperError 時に audit_log が failure で記録されること"""
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_pools",
            side_effect=SudoWrapperError("pools read failed"),
        ):
            with patch("backend.api.routes.dhcp.audit_log") as mock_audit:  # noqa: F841
                resp = test_client.get("/api/dhcp/pools", headers=admin_headers)
        assert resp.status_code == 503
        assert mock_audit.record.call_args[0][3] == "failure"

    def test_pools_error_detail(self, test_client, admin_headers):
        """SudoWrapperError のメッセージが detail に含まれること"""
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_pools",
            side_effect=SudoWrapperError("service not found"),
        ):
            resp = test_client.get("/api/dhcp/pools", headers=admin_headers)
        assert resp.status_code == 503
        body = resp.json()
        msg = body.get("detail") or body.get("message") or ""
        assert "service not found" in msg

    def test_pools_empty_result(self, test_client, admin_headers):
        """プールが空でも正常にレスポンスが返ること"""
        mock_data = {"pools": [], "total": 0}
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_pools",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/dhcp/pools", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["pools"] == []

    def test_pools_multiple_entries(self, test_client, admin_headers):
        """複数のプールが返ること"""
        mock_data = {
            "pools": [
                {
                    "subnet": "192.168.1.0/24",
                    "ranges": [{"start": "192.168.1.100", "end": "192.168.1.200"}],
                    "allow": ["known-clients"],
                    "deny": [],
                },
                {
                    "subnet": "10.0.0.0/24",
                    "ranges": [{"start": "10.0.0.50", "end": "10.0.0.150"}],
                    "allow": [],
                    "deny": ["unknown-clients"],
                },
            ],
            "total": 2,
        }
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_pools",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/dhcp/pools", headers=admin_headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]["pools"]) == 2

    def test_pools_viewer_role(self, test_client, viewer_headers):
        """viewer ロールでもプール取得可能"""
        mock_data = {"pools": [], "total": 0}
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_pools",
            return_value=mock_data,
        ):
            resp = test_client.get("/api/dhcp/pools", headers=viewer_headers)
        assert resp.status_code == 200


# ==============================================================================
# /logs 追加テスト
# ==============================================================================


class TestDhcpLogsExtra:
    """DHCP ログの追加カバレッジテスト"""

    def test_logs_audit_log_success(self, test_client, admin_headers):
        """正常時に audit_log が dhcp_logs_view/success で記録されること"""
        mock_data = {"logs": "line1\n", "lines": 50}
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_logs", return_value=mock_data
        ):
            with patch("backend.api.routes.dhcp.audit_log") as mock_audit:  # noqa: F841
                resp = test_client.get("/api/dhcp/logs", headers=admin_headers)
        assert resp.status_code == 200
        assert mock_audit.record.call_args[0][0] == "dhcp_logs_view"
        assert mock_audit.record.call_args[0][3] == "success"

    def test_logs_audit_log_failure(self, test_client, admin_headers):
        """SudoWrapperError 時に audit_log が failure で記録されること"""
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_logs",
            side_effect=SudoWrapperError("logs read failed"),
        ):
            with patch("backend.api.routes.dhcp.audit_log") as mock_audit:  # noqa: F841
                resp = test_client.get("/api/dhcp/logs", headers=admin_headers)
        assert resp.status_code == 503
        assert mock_audit.record.call_args[0][3] == "failure"

    def test_logs_error_detail(self, test_client, admin_headers):
        """SudoWrapperError のメッセージが detail に含まれること"""
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_logs",
            side_effect=SudoWrapperError("file not found"),
        ):
            resp = test_client.get("/api/dhcp/logs", headers=admin_headers)
        assert resp.status_code == 503
        body = resp.json()
        msg = body.get("detail") or body.get("message") or ""
        assert "file not found" in msg

    def test_logs_default_lines(self, test_client, admin_headers):
        """デフォルト lines=50 で呼ばれること"""
        mock_data = {"logs": "", "lines": 50}
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_logs", return_value=mock_data
        ) as mock_fn:
            resp = test_client.get("/api/dhcp/logs", headers=admin_headers)
        assert resp.status_code == 200
        mock_fn.assert_called_once_with(lines=50)

    def test_logs_custom_lines_10(self, test_client, admin_headers):
        """lines=10 で正常に動作"""
        mock_data = {"logs": "line\n", "lines": 10}
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_logs", return_value=mock_data
        ) as mock_fn:
            resp = test_client.get("/api/dhcp/logs?lines=10", headers=admin_headers)
        assert resp.status_code == 200
        mock_fn.assert_called_once_with(lines=10)

    def test_logs_custom_lines_150(self, test_client, admin_headers):
        """lines=150 で正常に動作"""
        mock_data = {"logs": "", "lines": 150}
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_logs", return_value=mock_data
        ) as mock_fn:
            resp = test_client.get("/api/dhcp/logs?lines=150", headers=admin_headers)
        assert resp.status_code == 200
        mock_fn.assert_called_once_with(lines=150)

    def test_logs_viewer_role(self, test_client, viewer_headers):
        """viewer ロールでもログ取得可能"""
        mock_data = {"logs": "", "lines": 50}
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_logs", return_value=mock_data
        ):
            resp = test_client.get("/api/dhcp/logs", headers=viewer_headers)
        assert resp.status_code == 200

    def test_logs_large_output(self, test_client, admin_headers):
        """大量のログ出力でも正常に返ること"""
        large_logs = "".join(
            [f"Jan  1 00:00:{i:02d} host dhcpd: DHCPACK\n" for i in range(60)]
        )
        mock_data = {"logs": large_logs, "lines": 200}
        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_logs", return_value=mock_data
        ):
            resp = test_client.get("/api/dhcp/logs?lines=200", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["success"] is True


# ==============================================================================
# バリデーション境界値テスト
# ==============================================================================


class TestDhcpLogsValidationExtra:
    """logs lines パラメータの境界値テスト"""

    def test_logs_lines_negative(self, test_client, admin_headers):
        """lines=-1 は 422"""
        resp = test_client.get("/api/dhcp/logs?lines=-1", headers=admin_headers)
        assert resp.status_code == 422

    def test_logs_lines_string(self, test_client, admin_headers):
        """lines=abc は 422"""
        resp = test_client.get("/api/dhcp/logs?lines=abc", headers=admin_headers)
        assert resp.status_code == 422

    def test_logs_lines_float(self, test_client, admin_headers):
        """lines=50.5 は 422"""
        resp = test_client.get("/api/dhcp/logs?lines=50.5", headers=admin_headers)
        assert resp.status_code == 422

    def test_logs_lines_very_large(self, test_client, admin_headers):
        """lines=10000 は 422"""
        resp = test_client.get("/api/dhcp/logs?lines=10000", headers=admin_headers)
        assert resp.status_code == 422


# ==============================================================================
# HTTPException 再送出パステスト
# ==============================================================================


class TestDhcpHTTPExceptionReraise:
    """各エンドポイントの except HTTPException: raise パスをカバー"""

    def test_status_reraises_http_exception(self, test_client, admin_headers):
        """get_dhcp_status: HTTPException が再送出されること"""
        from fastapi import HTTPException

        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_status",
            side_effect=HTTPException(status_code=429, detail="rate limited"),
        ):
            resp = test_client.get("/api/dhcp/status", headers=admin_headers)
        assert resp.status_code == 429

    def test_leases_reraises_http_exception(self, test_client, admin_headers):
        """get_dhcp_leases: HTTPException が再送出されること"""
        from fastapi import HTTPException

        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_leases",
            side_effect=HTTPException(status_code=502, detail="bad gateway"),
        ):
            resp = test_client.get("/api/dhcp/leases", headers=admin_headers)
        assert resp.status_code == 502

    def test_config_reraises_http_exception(self, test_client, admin_headers):
        """get_dhcp_config: HTTPException が再送出されること"""
        from fastapi import HTTPException

        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_config",
            side_effect=HTTPException(status_code=503, detail="service unavailable"),
        ):
            resp = test_client.get("/api/dhcp/config", headers=admin_headers)
        assert resp.status_code == 503

    def test_pools_reraises_http_exception(self, test_client, admin_headers):
        """get_dhcp_pools: HTTPException が再送出されること"""
        from fastapi import HTTPException

        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_pools",
            side_effect=HTTPException(status_code=500, detail="internal error"),
        ):
            resp = test_client.get("/api/dhcp/pools", headers=admin_headers)
        assert resp.status_code == 500

    def test_logs_reraises_http_exception(self, test_client, admin_headers):
        """get_dhcp_logs: HTTPException が再送出されること"""
        from fastapi import HTTPException

        with patch(
            "backend.api.routes.dhcp.sudo_wrapper.get_dhcp_logs",
            side_effect=HTTPException(status_code=504, detail="gateway timeout"),
        ):
            resp = test_client.get("/api/dhcp/logs", headers=admin_headers)
        assert resp.status_code == 504


# ==============================================================================
# unavailable ステータスの各エンドポイント詳細テスト
# ==============================================================================


class TestDhcpUnavailableExtra:
    """unavailable ステータスの追加テスト"""

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
    def test_unavailable_returns_503_with_message(
        self, test_client, admin_headers, endpoint, wrapper_method
    ):
        """全エンドポイントで unavailable → 503 + メッセージ"""
        mock_data = {
            "status": "unavailable",
            "message": "isc-dhcp-server is not installed",
        }
        with patch(
            f"backend.api.routes.dhcp.sudo_wrapper.{wrapper_method}",
            return_value=mock_data,
        ):
            resp = test_client.get(endpoint, headers=admin_headers)
        assert resp.status_code == 503
        body = resp.json()
        msg = body.get("detail") or body.get("message") or ""
        assert "インストールされていません" in msg

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
    def test_wrapper_error_returns_503_all_endpoints(
        self, test_client, admin_headers, endpoint, wrapper_method
    ):
        """全エンドポイントで SudoWrapperError → 503"""
        with patch(
            f"backend.api.routes.dhcp.sudo_wrapper.{wrapper_method}",
            side_effect=SudoWrapperError("test error"),
        ):
            resp = test_client.get(endpoint, headers=admin_headers)
        assert resp.status_code == 503
        body = resp.json()
        msg = body.get("detail") or body.get("message") or ""
        assert "test error" in msg


# ==============================================================================
# 認証テスト追加
# ==============================================================================


class TestDhcpAuthExtra:
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
    def test_expired_token_rejected(self, test_client, endpoint):
        """期限切れトークンは拒否されること"""
        resp = test_client.get(
            endpoint,
            headers={"Authorization": "Bearer expired.token.here"},
        )
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
    def test_missing_bearer_prefix(self, test_client, endpoint):
        """Bearer プレフィックスなしは拒否されること"""
        resp = test_client.get(
            endpoint,
            headers={"Authorization": "some_token_here"},
        )
        assert resp.status_code in (401, 403)
