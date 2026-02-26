"""
E2E テスト - API エンドポイント シナリオテスト

実際のHTTPサーバーに対してAPIを呼び出すE2Eシナリオを検証する。
Playwright の request API を使用してHTTPリクエストを直接送信。
"""

import pytest


pytestmark = [pytest.mark.e2e]


# ==============================================================================
# 認証フロー E2E テスト
# ==============================================================================


class TestAuthFlow:
    """認証APIのE2Eシナリオ"""

    def test_login_with_valid_credentials(self, page, base_url):
        """正常なログイン"""
        response = page.request.post(
            f"{base_url}/api/auth/login",
            data={"email": "operator@example.com", "password": "operator123"},
            headers={"Content-Type": "application/json"},
        )
        assert response.ok
        data = response.json()
        assert data["access_token"]
        assert data["token_type"] == "bearer"
        assert "user_id" in data

    def test_login_with_invalid_credentials(self, page, base_url):
        """不正な認証情報でのログイン"""
        response = page.request.post(
            f"{base_url}/api/auth/login",
            data={"email": "invalid@example.com", "password": "wrongpassword"},
            headers={"Content-Type": "application/json"},
        )
        assert response.status == 401

    def test_logout(self, page, base_url):
        """ログアウト"""
        # 先にログイン
        login_resp = page.request.post(
            f"{base_url}/api/auth/login",
            data={"email": "operator@example.com", "password": "operator123"},
            headers={"Content-Type": "application/json"},
        )
        token = login_resp.json()["access_token"]

        # ログアウト
        logout_resp = page.request.post(
            f"{base_url}/api/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert logout_resp.ok

    def test_get_current_user(self, page, base_url):
        """現在のユーザー情報取得"""
        login_resp = page.request.post(
            f"{base_url}/api/auth/login",
            data={"email": "admin@example.com", "password": "admin123"},
            headers={"Content-Type": "application/json"},
        )
        token = login_resp.json()["access_token"]

        me_resp = page.request.get(
            f"{base_url}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_resp.ok
        data = me_resp.json()
        assert data["email"] == "admin@example.com"
        assert "role" in data

    def test_protected_endpoint_without_token(self, page, base_url):
        """認証なしでの保護エンドポイントアクセス"""
        response = page.request.get(f"{base_url}/api/system/status")
        assert response.status in (401, 403)

    def test_token_refresh(self, page, base_url):
        """トークンリフレッシュ"""
        login_resp = page.request.post(
            f"{base_url}/api/auth/login",
            data={"email": "operator@example.com", "password": "operator123"},
            headers={"Content-Type": "application/json"},
        )
        refresh_token = login_resp.json().get("refresh_token")
        if not refresh_token:
            pytest.skip("refresh_token not in response")

        refresh_resp = page.request.post(
            f"{base_url}/api/auth/refresh",
            headers={"Authorization": f"Bearer {refresh_token}"},
        )
        assert refresh_resp.ok


# ==============================================================================
# システム状態 E2E テスト
# ==============================================================================


class TestSystemStatusFlow:
    """システム状態APIのE2Eシナリオ"""

    @pytest.fixture(autouse=True)
    def setup_token(self, page, base_url):
        """認証トークンをセットアップ"""
        login_resp = page.request.post(
            f"{base_url}/api/auth/login",
            data={"email": "operator@example.com", "password": "operator123"},
            headers={"Content-Type": "application/json"},
        )
        self.token = login_resp.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_get_system_status(self, page, base_url):
        """システム状態取得"""
        response = page.request.get(
            f"{base_url}/api/system/status",
            headers=self.headers,
        )
        assert response.ok
        data = response.json()
        # システム状態レスポンス: cpu, memory, disk, uptime, timestamp
        assert "cpu" in data or "memory" in data

    def test_health_check(self, page, base_url):
        """ヘルスチェックエンドポイント（認証不要）"""
        response = page.request.get(f"{base_url}/health")
        assert response.ok


# ==============================================================================
# ネットワーク情報 E2E テスト
# ==============================================================================


class TestNetworkFlow:
    """ネットワーク情報APIのE2Eシナリオ"""

    @pytest.fixture(autouse=True)
    def setup_token(self, page, base_url):
        login_resp = page.request.post(
            f"{base_url}/api/auth/login",
            data={"email": "viewer@example.com", "password": "viewer123"},
            headers={"Content-Type": "application/json"},
        )
        self.token = login_resp.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_get_network_interfaces(self, page, base_url):
        """ネットワークインターフェース取得"""
        response = page.request.get(
            f"{base_url}/api/network/interfaces",
            headers=self.headers,
        )
        # 成功または503（ラッパーが利用不可の環境）
        assert response.status in (200, 503)
        if response.ok:
            data = response.json()
            assert data["status"] == "success"
            assert "interfaces" in data
            assert "timestamp" in data

    def test_get_network_routes(self, page, base_url):
        """ルーティングテーブル取得"""
        response = page.request.get(
            f"{base_url}/api/network/routes",
            headers=self.headers,
        )
        assert response.status in (200, 503)

    def test_get_network_connections(self, page, base_url):
        """ネットワーク接続取得"""
        response = page.request.get(
            f"{base_url}/api/network/connections",
            headers=self.headers,
        )
        assert response.status in (200, 503)

    def test_get_network_stats(self, page, base_url):
        """ネットワーク統計取得"""
        response = page.request.get(
            f"{base_url}/api/network/stats",
            headers=self.headers,
        )
        assert response.status in (200, 503)

    def test_network_endpoints_require_auth(self, page, base_url):
        """認証なしでのアクセスは拒否"""
        for endpoint in ["/interfaces", "/routes", "/connections", "/stats"]:
            response = page.request.get(f"{base_url}/api/network{endpoint}")
            assert response.status in (401, 403), f"Expected 401/403 for {endpoint}"


# ==============================================================================
# サーバー管理 E2E テスト
# ==============================================================================


class TestServersFlow:
    """サーバー管理APIのE2Eシナリオ"""

    @pytest.fixture(autouse=True)
    def setup_token(self, page, base_url):
        login_resp = page.request.post(
            f"{base_url}/api/auth/login",
            data={"email": "operator@example.com", "password": "operator123"},
            headers={"Content-Type": "application/json"},
        )
        self.token = login_resp.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_get_all_server_status(self, page, base_url):
        """全サーバー状態一括取得"""
        response = page.request.get(
            f"{base_url}/api/servers/status",
            headers=self.headers,
        )
        assert response.status in (200, 503)
        if response.ok:
            data = response.json()
            assert data["status"] == "success"
            assert "servers" in data

    @pytest.mark.parametrize("server", ["nginx", "apache2", "mysql", "postgresql", "redis"])
    def test_get_each_server_status(self, page, base_url, server):
        """各許可サーバーの個別状態取得"""
        response = page.request.get(
            f"{base_url}/api/servers/{server}/status",
            headers=self.headers,
        )
        assert response.status in (200, 400, 503)

    def test_invalid_server_rejected(self, page, base_url):
        """allowlist外のサーバーは拒否"""
        response = page.request.get(
            f"{base_url}/api/servers/bash/status",
            headers=self.headers,
        )
        assert response.status == 422  # Path 正規表現不一致


# ==============================================================================
# ハードウェア情報 E2E テスト
# ==============================================================================


class TestHardwareFlow:
    """ハードウェア情報APIのE2Eシナリオ"""

    @pytest.fixture(autouse=True)
    def setup_token(self, page, base_url):
        login_resp = page.request.post(
            f"{base_url}/api/auth/login",
            data={"email": "viewer@example.com", "password": "viewer123"},
            headers={"Content-Type": "application/json"},
        )
        self.token = login_resp.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_get_hardware_memory(self, page, base_url):
        """メモリ情報取得（/proc/meminfo は常に利用可能）"""
        response = page.request.get(
            f"{base_url}/api/hardware/memory",
            headers=self.headers,
        )
        # /proc/meminfo は Linux では常にアクセス可能
        assert response.ok
        data = response.json()
        assert data["status"] == "success"
        mem = data.get("memory", {})
        assert "total_kb" in mem
        assert mem["total_kb"] > 0

    def test_get_hardware_disk_usage(self, page, base_url):
        """ディスク使用量取得"""
        response = page.request.get(
            f"{base_url}/api/hardware/disk_usage",
            headers=self.headers,
        )
        # df は Linux では常に利用可能
        assert response.status in (200, 503)
        if response.ok:
            data = response.json()
            assert data["status"] == "success"
            assert "usage" in data

    def test_get_hardware_disks(self, page, base_url):
        """ディスク一覧取得"""
        response = page.request.get(
            f"{base_url}/api/hardware/disks",
            headers=self.headers,
        )
        assert response.status in (200, 503)

    def test_smart_invalid_device_rejected(self, page, base_url):
        """不正なデバイスパスは拒否される"""
        from urllib.parse import quote

        for bad_device in ["/etc/passwd", "/dev/sda;ls", "/dev/sda1"]:
            response = page.request.get(
                f"{base_url}/api/hardware/smart?device={quote(bad_device)}",
                headers=self.headers,
            )
            assert response.status in (400, 422), (
                f"Expected 400/422 for bad device '{bad_device}', got {response.status}"
            )


# ==============================================================================
# RBAC E2E テスト（権限分離の確認）
# ==============================================================================


class TestRBACFlow:
    """RBAC（ロールベースアクセス制御）のE2Eシナリオ"""

    def _get_token(self, page, base_url, email, password):
        resp = page.request.post(
            f"{base_url}/api/auth/login",
            data={"email": email, "password": password},
            headers={"Content-Type": "application/json"},
        )
        return resp.json()["access_token"]

    def test_viewer_can_read_status(self, page, base_url):
        """Viewer は状態閲覧可能"""
        token = self._get_token(page, base_url, "viewer@example.com", "viewer123")
        resp = page.request.get(
            f"{base_url}/api/system/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.ok

    def test_viewer_cannot_restart_service(self, page, base_url):
        """Viewer はサービス再起動不可"""
        token = self._get_token(page, base_url, "viewer@example.com", "viewer123")
        resp = page.request.post(
            f"{base_url}/api/services/restart",
            data={"service": "nginx"},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        assert resp.status == 403

    def test_operator_can_restart_service(self, page, base_url):
        """Operator はサービス再起動を試みられる（モック環境では失敗するが権限はある）"""
        token = self._get_token(page, base_url, "operator@example.com", "operator123")
        resp = page.request.post(
            f"{base_url}/api/services/restart",
            data={"service": "nginx"},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        # 権限あり（200 or 422/500/503）、権限なし（403）ではない
        assert resp.status != 403, "Operator should have restart permission"

    def test_admin_can_access_approval(self, page, base_url):
        """Admin は承認ワークフロー（pending）にアクセス可能"""
        token = self._get_token(page, base_url, "admin@example.com", "admin123")
        resp = page.request.get(
            f"{base_url}/api/approval/pending",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.ok

    def test_viewer_cannot_access_approval_pending(self, page, base_url):
        """Viewer は承認待ちリストにアクセス不可"""
        token = self._get_token(page, base_url, "viewer@example.com", "viewer123")
        resp = page.request.get(
            f"{base_url}/api/approval/pending",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status == 403


# ==============================================================================
# API レスポンス構造 E2E テスト
# ==============================================================================


class TestAPIResponseStructure:
    """APIレスポンスの共通構造を検証"""

    @pytest.fixture(autouse=True)
    def setup_token(self, page, base_url):
        login_resp = page.request.post(
            f"{base_url}/api/auth/login",
            data={"email": "operator@example.com", "password": "operator123"},
            headers={"Content-Type": "application/json"},
        )
        self.token = login_resp.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    @pytest.mark.parametrize("endpoint,expected_fields", [
        ("/api/network/interfaces", ["status", "interfaces", "timestamp"]),
        ("/api/network/routes", ["status", "routes", "timestamp"]),
        ("/api/servers/status", ["status", "servers", "timestamp"]),
        ("/api/hardware/memory", ["status", "memory", "timestamp"]),
    ])
    def test_response_has_required_fields(self, page, base_url, endpoint, expected_fields):
        """全APIレスポンスに必須フィールドが存在する"""
        response = page.request.get(
            f"{base_url}{endpoint}",
            headers=self.headers,
        )
        # 200 または 503（サービス不可）のみ許可
        assert response.status in (200, 503), f"{endpoint}: unexpected status {response.status}"
        if response.ok:
            data = response.json()
            for field in expected_fields:
                assert field in data, f"{endpoint}: missing field '{field}'"

    def test_error_response_has_message(self, page, base_url):
        """エラーレスポンスには message フィールドが含まれる"""
        # 存在しないエンドポイント
        response = page.request.get(
            f"{base_url}/api/nonexistent",
            headers=self.headers,
        )
        assert response.status == 404
        data = response.json()
        assert "detail" in data or "message" in data
