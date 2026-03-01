"""
Firewall API エンドポイントのユニットテスト

backend/api/routes/firewall.py のカバレッジ向上
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.core.sudo_wrapper import SudoWrapperError


def _mock_output(**kwargs):
    """テスト用モックデータ生成ヘルパー"""
    defaults = {"status": "ok", "timestamp": "2026-03-01T00:00:00Z"}
    defaults.update(kwargs)
    return {"status": "success", "output": json.dumps(defaults)}


class TestGetFirewallRules:
    """GET /api/firewall/rules テスト"""

    def test_rules_success(self, test_client, auth_headers):
        """正常系: ルール一覧取得"""
        with patch("backend.api.routes.firewall.sudo_wrapper") as mock_sw:
            mock_sw.get_firewall_rules.return_value = _mock_output(
                backend="iptables", raw="some rules", raw_lines=["line1"]
            )
            response = test_client.get("/api/firewall/rules", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_rules_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時は503"""
        with patch("backend.api.routes.firewall.sudo_wrapper") as mock_sw:
            mock_sw.get_firewall_rules.side_effect = SudoWrapperError("Failed")
            response = test_client.get("/api/firewall/rules", headers=auth_headers)
        assert response.status_code == 503

    def test_rules_unexpected_error(self, test_client, auth_headers):
        """予期しないエラー時は500"""
        with patch("backend.api.routes.firewall.sudo_wrapper") as mock_sw:
            mock_sw.get_firewall_rules.side_effect = RuntimeError("Boom")
            response = test_client.get("/api/firewall/rules", headers=auth_headers)
        assert response.status_code == 500

    def test_rules_unauthorized(self, test_client):
        """未認証アクセス"""
        response = test_client.get("/api/firewall/rules")
        assert response.status_code == 403


class TestGetFirewallPolicy:
    """GET /api/firewall/policy テスト"""

    def test_policy_success(self, test_client, auth_headers):
        """正常系: ポリシー取得"""
        with patch("backend.api.routes.firewall.sudo_wrapper") as mock_sw:
            mock_sw.get_firewall_policy.return_value = _mock_output(
                backend="iptables", chains=[{"name": "INPUT", "policy": "ACCEPT"}]
            )
            response = test_client.get("/api/firewall/policy", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_policy_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時は503"""
        with patch("backend.api.routes.firewall.sudo_wrapper") as mock_sw:
            mock_sw.get_firewall_policy.side_effect = SudoWrapperError("Failed")
            response = test_client.get("/api/firewall/policy", headers=auth_headers)
        assert response.status_code == 503

    def test_policy_unexpected_error(self, test_client, auth_headers):
        """予期しないエラー時は500"""
        with patch("backend.api.routes.firewall.sudo_wrapper") as mock_sw:
            mock_sw.get_firewall_policy.side_effect = RuntimeError("Boom")
            response = test_client.get("/api/firewall/policy", headers=auth_headers)
        assert response.status_code == 500


class TestGetFirewallStatus:
    """GET /api/firewall/status テスト"""

    def test_status_success(self, test_client, auth_headers):
        """正常系: ファイアウォール状態取得"""
        with patch("backend.api.routes.firewall.sudo_wrapper") as mock_sw:
            mock_sw.get_firewall_status.return_value = _mock_output(
                ufw_active=True,
                firewalld_active=False,
                iptables_available=True,
                nftables_available=False,
                available_backends=["ufw", "iptables"],
            )
            response = test_client.get("/api/firewall/status", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["ufw_active"] is True

    def test_status_wrapper_error(self, test_client, auth_headers):
        """SudoWrapperError 発生時は503"""
        with patch("backend.api.routes.firewall.sudo_wrapper") as mock_sw:
            mock_sw.get_firewall_status.side_effect = SudoWrapperError("Failed")
            response = test_client.get("/api/firewall/status", headers=auth_headers)
        assert response.status_code == 503

    def test_status_unexpected_error(self, test_client, auth_headers):
        """予期しないエラー時は500"""
        with patch("backend.api.routes.firewall.sudo_wrapper") as mock_sw:
            mock_sw.get_firewall_status.side_effect = RuntimeError("Boom")
            response = test_client.get("/api/firewall/status", headers=auth_headers)
        assert response.status_code == 500


class TestCreateFirewallRule:
    """POST /api/firewall/rules テスト"""

    def test_create_rule_success(self, test_client, admin_headers):
        """正常系: ルール追加（承認フロー）"""
        mock_result = {"request_id": "test-req-123"}
        with patch("backend.api.routes.firewall.approval_service") as mock_as:
            mock_as.create_request = AsyncMock(return_value=mock_result)
            response = test_client.post(
                "/api/firewall/rules",
                json={"port": 443, "protocol": "tcp", "action": "allow", "reason": "HTTPS access"},
                headers=admin_headers,
            )
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "pending_approval"
        assert data["request_id"] == "test-req-123"

    def test_create_rule_invalid_port(self, test_client, admin_headers):
        """不正なポート番号"""
        response = test_client.post(
            "/api/firewall/rules",
            json={"port": 0, "protocol": "tcp", "action": "allow", "reason": "Test"},
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_create_rule_invalid_protocol(self, test_client, admin_headers):
        """不正なプロトコル"""
        response = test_client.post(
            "/api/firewall/rules",
            json={"port": 80, "protocol": "icmp", "action": "allow", "reason": "Test"},
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_create_rule_invalid_action(self, test_client, admin_headers):
        """不正なアクション"""
        response = test_client.post(
            "/api/firewall/rules",
            json={"port": 80, "protocol": "tcp", "action": "reject", "reason": "Test"},
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_create_rule_value_error(self, test_client, admin_headers):
        """ValueError 発生時は400"""
        with patch("backend.api.routes.firewall.approval_service") as mock_as:
            mock_as.create_request = AsyncMock(side_effect=ValueError("Bad request"))
            response = test_client.post(
                "/api/firewall/rules",
                json={"port": 80, "protocol": "tcp", "action": "allow", "reason": "Test"},
                headers=admin_headers,
            )
        assert response.status_code == 400

    def test_create_rule_unexpected_error(self, test_client, admin_headers):
        """予期しないエラー時は500"""
        with patch("backend.api.routes.firewall.approval_service") as mock_as:
            mock_as.create_request = AsyncMock(side_effect=RuntimeError("Boom"))
            response = test_client.post(
                "/api/firewall/rules",
                json={"port": 80, "protocol": "tcp", "action": "allow", "reason": "Test"},
                headers=admin_headers,
            )
        assert response.status_code == 500

    def test_create_rule_operator_forbidden(self, test_client, auth_headers):
        """Operator権限不足"""
        response = test_client.post(
            "/api/firewall/rules",
            json={"port": 80, "protocol": "tcp", "action": "allow", "reason": "Test"},
            headers=auth_headers,
        )
        assert response.status_code == 403


class TestDeleteFirewallRule:
    """DELETE /api/firewall/rules/{rule_num} テスト"""

    def test_delete_rule_success(self, test_client, admin_headers):
        """正常系: ルール削除（承認フロー）"""
        mock_result = {"request_id": "del-req-456"}
        with patch("backend.api.routes.firewall.approval_service") as mock_as:
            mock_as.create_request = AsyncMock(return_value=mock_result)
            response = test_client.delete(
                "/api/firewall/rules/5", headers=admin_headers
            )
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "pending_approval"

    def test_delete_rule_invalid_num_zero(self, test_client, admin_headers):
        """不正なルール番号（0）"""
        response = test_client.delete(
            "/api/firewall/rules/0", headers=admin_headers
        )
        assert response.status_code == 422

    def test_delete_rule_invalid_num_large(self, test_client, admin_headers):
        """不正なルール番号（1000超）"""
        response = test_client.delete(
            "/api/firewall/rules/1000", headers=admin_headers
        )
        assert response.status_code == 422

    def test_delete_rule_value_error(self, test_client, admin_headers):
        """ValueError 発生時は400"""
        with patch("backend.api.routes.firewall.approval_service") as mock_as:
            mock_as.create_request = AsyncMock(side_effect=ValueError("Bad"))
            response = test_client.delete(
                "/api/firewall/rules/1", headers=admin_headers
            )
        assert response.status_code == 400

    def test_delete_rule_unexpected_error(self, test_client, admin_headers):
        """予期しないエラー時は500"""
        with patch("backend.api.routes.firewall.approval_service") as mock_as:
            mock_as.create_request = AsyncMock(side_effect=RuntimeError("Boom"))
            response = test_client.delete(
                "/api/firewall/rules/1", headers=admin_headers
            )
        assert response.status_code == 500

    def test_delete_rule_operator_forbidden(self, test_client, auth_headers):
        """Operator権限不足"""
        response = test_client.delete(
            "/api/firewall/rules/1", headers=auth_headers
        )
        assert response.status_code == 403
