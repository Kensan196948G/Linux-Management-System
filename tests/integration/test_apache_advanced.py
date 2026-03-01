"""
Apache 設定管理強化 - 統合テスト (Step 24)

テストケース数: 6件
  - GET /api/apache/vhosts-detail: 正常系・SudoWrapperError・未認証
  - GET /api/apache/ssl-certs:     正常系・SudoWrapperError・未認証
"""

from unittest.mock import patch

import pytest

from backend.core.sudo_wrapper import SudoWrapperError

# ===================================================================
# テストデータ
# ===================================================================

VHOSTS_DETAIL_OK = {
    "status": "success",
    "data": "VirtualHost configuration:\n*:80 localhost (/etc/apache2/sites-enabled/000-default.conf:1)",
    "timestamp": "2026-03-01T00:00:00Z",
}

SSL_CERTS_OK = {
    "status": "success",
    "data": "/etc/ssl/certs/ca-certificates.crt|Mar 12 00:00:00 2027 GMT\n",
    "timestamp": "2026-03-01T00:00:00Z",
}


# ===================================================================
# テストクラス
# ===================================================================


class TestApacheVhostsDetail:
    """GET /api/apache/vhosts-detail テスト"""

    def test_TC_APH_ADV_001_vhosts_detail_ok(self, test_client, admin_token):
        """正常系: vhosts-detail が 200 + data キーを返す"""
        with patch("backend.api.routes.apache.sudo_wrapper.get_apache_vhosts_detail", return_value=VHOSTS_DETAIL_OK):
            resp = test_client.get(
                "/api/apache/vhosts-detail",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_TC_APH_ADV_002_vhosts_detail_wrapper_error(self, test_client, admin_token):
        """異常系: SudoWrapperError → 503"""
        with patch(
            "backend.api.routes.apache.sudo_wrapper.get_apache_vhosts_detail",
            side_effect=SudoWrapperError("wrapper failed"),
        ):
            resp = test_client.get(
                "/api/apache/vhosts-detail",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 503

    def test_TC_APH_ADV_003_vhosts_detail_unauthorized(self, test_client):
        """未認証: 401 or 403"""
        resp = test_client.get("/api/apache/vhosts-detail")
        assert resp.status_code in (401, 403)


class TestApacheSslCerts:
    """GET /api/apache/ssl-certs テスト"""

    def test_TC_APH_ADV_004_ssl_certs_ok(self, test_client, admin_token):
        """正常系: ssl-certs が 200 + data キーを返す"""
        with patch("backend.api.routes.apache.sudo_wrapper.get_apache_ssl_certs", return_value=SSL_CERTS_OK):
            resp = test_client.get(
                "/api/apache/ssl-certs",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_TC_APH_ADV_005_ssl_certs_wrapper_error(self, test_client, admin_token):
        """異常系: SudoWrapperError → 503"""
        with patch(
            "backend.api.routes.apache.sudo_wrapper.get_apache_ssl_certs",
            side_effect=SudoWrapperError("wrapper failed"),
        ):
            resp = test_client.get(
                "/api/apache/ssl-certs",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 503

    def test_TC_APH_ADV_006_ssl_certs_unauthorized(self, test_client):
        """未認証: 401 or 403"""
        resp = test_client.get("/api/apache/ssl-certs")
        assert resp.status_code in (401, 403)
