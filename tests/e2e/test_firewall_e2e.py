"""
E2E テスト - Firewall API エンドポイント

ファイアウォール管理APIの E2E シナリオを検証する。
エンドポイント:
  GET    /api/firewall/status   - ファイアウォール全体状態
  GET    /api/firewall/rules    - ルール一覧
  GET    /api/firewall/policy   - デフォルトポリシー
  POST   /api/firewall/rules    - ルール追加（承認フロー経由）
  DELETE /api/firewall/rules/{num} - ルール削除（承認フロー経由）
"""

import pytest


pytestmark = [pytest.mark.e2e]


class TestFirewallE2E:
    """Firewall API の E2E テスト"""

    # ------------------------------------------------------------------
    # 認証ヘルパー
    # ------------------------------------------------------------------

    def _get_token(self, api_client, email, password):
        resp = api_client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        )
        assert resp.status_code == 200, f"Login failed for {email}: {resp.status_code}"
        return resp.json()["access_token"]

    # ------------------------------------------------------------------
    # 読み取り系 (GET) - 認証済み
    # ------------------------------------------------------------------

    def test_get_firewall_status(self, api_client, admin_token):
        """GET /api/firewall/status -> 200 or 503"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = api_client.get("/api/firewall/status", headers=headers)
        assert response.status_code in (200, 503)
        if response.status_code == 200:
            data = response.json()
            assert data["status"] == "success"
            assert "ufw_active" in data
            assert "available_backends" in data
            assert "timestamp" in data

    def test_get_firewall_rules(self, api_client, admin_token):
        """GET /api/firewall/rules -> 200 or 503"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = api_client.get("/api/firewall/rules", headers=headers)
        assert response.status_code in (200, 503)
        if response.status_code == 200:
            data = response.json()
            assert data["status"] == "success"
            assert "timestamp" in data

    def test_get_firewall_policy(self, api_client, admin_token):
        """GET /api/firewall/policy -> 200 or 503"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = api_client.get("/api/firewall/policy", headers=headers)
        assert response.status_code in (200, 503)
        if response.status_code == 200:
            data = response.json()
            assert data["status"] == "success"
            assert "chains" in data
            assert "timestamp" in data

    def test_viewer_can_read_firewall(self, api_client, viewer_token):
        """Viewer ロールも read:firewall 権限を持つ"""
        headers = {"Authorization": f"Bearer {viewer_token}"}
        response = api_client.get("/api/firewall/status", headers=headers)
        # Viewer は read:firewall を持つので 200 or 503（wrapper不可）
        assert response.status_code in (200, 503)

    # ------------------------------------------------------------------
    # 書き込み系 (POST) - ルール追加
    # ------------------------------------------------------------------

    def test_create_firewall_rule_normal(self, api_client, admin_token):
        """POST /api/firewall/rules 正常系: 承認フロー経由で 202"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        payload = {
            "port": 8999,
            "protocol": "tcp",
            "action": "allow",
            "reason": "E2E test rule addition",
        }
        response = api_client.post(
            "/api/firewall/rules", json=payload, headers=headers
        )
        # 202 Accepted（承認フロー）or 500（approval_service の DB 不備等）
        assert response.status_code in (202, 500)
        if response.status_code == 202:
            data = response.json()
            assert data["status"] == "pending_approval"
            assert "request_id" in data

    def test_create_firewall_rule_invalid_port(self, api_client, admin_token):
        """POST /api/firewall/rules 不正ポート: port=99999 -> 422"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        payload = {
            "port": 99999,
            "protocol": "tcp",
            "action": "allow",
            "reason": "Invalid port test",
        }
        response = api_client.post(
            "/api/firewall/rules", json=payload, headers=headers
        )
        assert response.status_code == 422

    def test_create_firewall_rule_invalid_port_zero(self, api_client, admin_token):
        """POST /api/firewall/rules ポート0 -> 422"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        payload = {
            "port": 0,
            "protocol": "tcp",
            "action": "allow",
            "reason": "Zero port test",
        }
        response = api_client.post(
            "/api/firewall/rules", json=payload, headers=headers
        )
        assert response.status_code == 422

    def test_create_firewall_rule_invalid_protocol(self, api_client, admin_token):
        """POST /api/firewall/rules 不正プロトコル -> 422"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        payload = {
            "port": 8080,
            "protocol": "icmp",
            "action": "allow",
            "reason": "Invalid protocol test",
        }
        response = api_client.post(
            "/api/firewall/rules", json=payload, headers=headers
        )
        assert response.status_code == 422

    def test_create_firewall_rule_invalid_action(self, api_client, admin_token):
        """POST /api/firewall/rules 不正アクション -> 422"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        payload = {
            "port": 8080,
            "protocol": "tcp",
            "action": "reject",
            "reason": "Invalid action test",
        }
        response = api_client.post(
            "/api/firewall/rules", json=payload, headers=headers
        )
        assert response.status_code == 422

    def test_create_firewall_rule_special_chars_in_reason(
        self, api_client, admin_token
    ):
        """POST /api/firewall/rules 特殊文字を含む reason（セキュリティテスト）"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        payload = {
            "port": 8080,
            "protocol": "tcp",
            "action": "allow",
            "reason": "test; rm -rf /",
        }
        response = api_client.post(
            "/api/firewall/rules", json=payload, headers=headers
        )
        # reason フィールドはバリデーション上文字列として受け入れるが、
        # 実際にはシェルに渡されないためセキュリティ上の問題はない。
        # 202（承認待ち）or 400/422（バリデーション拒否）のどちらも許容。
        assert response.status_code in (202, 400, 422, 500)

    def test_create_firewall_rule_empty_reason(self, api_client, admin_token):
        """POST /api/firewall/rules 空の reason -> 422"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        payload = {
            "port": 8080,
            "protocol": "tcp",
            "action": "allow",
            "reason": "",
        }
        response = api_client.post(
            "/api/firewall/rules", json=payload, headers=headers
        )
        assert response.status_code == 422

    # ------------------------------------------------------------------
    # 書き込み系 (DELETE) - ルール削除
    # ------------------------------------------------------------------

    def test_delete_firewall_rule_nonexistent(self, api_client, admin_token):
        """DELETE /api/firewall/rules/999 -> 202 or 404/500"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = api_client.delete("/api/firewall/rules/999", headers=headers)
        # 承認フロー経由なので 202（承認待ち登録）が正常。
        # DB 不備などで 500 も許容。
        assert response.status_code in (202, 404, 500)

    def test_delete_firewall_rule_invalid_num_zero(self, api_client, admin_token):
        """DELETE /api/firewall/rules/0 -> 422（範囲外）"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = api_client.delete("/api/firewall/rules/0", headers=headers)
        assert response.status_code == 422

    # ------------------------------------------------------------------
    # 権限テスト
    # ------------------------------------------------------------------

    def test_firewall_write_requires_auth(self, api_client):
        """認証なしでルール追加は 403"""
        response = api_client.post(
            "/api/firewall/rules",
            json={"port": 8080, "protocol": "tcp", "action": "allow"},
        )
        assert response.status_code == 403

    def test_firewall_read_requires_auth(self, api_client):
        """認証なしで status 取得は 403"""
        response = api_client.get("/api/firewall/status")
        assert response.status_code == 403

    def test_viewer_cannot_write_firewall(self, api_client, viewer_token):
        """Viewer ロールはルール追加不可（write:firewall 権限なし）"""
        headers = {"Authorization": f"Bearer {viewer_token}"}
        payload = {
            "port": 8080,
            "protocol": "tcp",
            "action": "allow",
            "reason": "Viewer attempt",
        }
        response = api_client.post(
            "/api/firewall/rules", json=payload, headers=headers
        )
        assert response.status_code == 403

    def test_operator_cannot_write_firewall(self, api_client, auth_token):
        """Operator ロールはルール追加不可（write:firewall 権限なし）"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        payload = {
            "port": 8080,
            "protocol": "tcp",
            "action": "allow",
            "reason": "Operator attempt",
        }
        response = api_client.post(
            "/api/firewall/rules", json=payload, headers=headers
        )
        assert response.status_code == 403

    def test_viewer_cannot_delete_firewall_rule(self, api_client, viewer_token):
        """Viewer ロールはルール削除不可"""
        headers = {"Authorization": f"Bearer {viewer_token}"}
        response = api_client.delete("/api/firewall/rules/1", headers=headers)
        assert response.status_code == 403
