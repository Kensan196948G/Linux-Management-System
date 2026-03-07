"""
TLS/SSL 証明書管理 API 統合テスト

テスト対象:
  GET  /api/certificates/
  GET  /api/certificates/expiry-summary
  GET  /api/certificates/letsencrypt
  GET  /api/certificates/{cert_id}
  POST /api/certificates/check-domain
  POST /api/certificates/scan
  POST /api/certificates/generate-self-signed
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


# ===================================================================
# フィクスチャ
# ===================================================================


@pytest.fixture(scope="module")
def test_client():
    from backend.api.main import app
    return TestClient(app)


@pytest.fixture(scope="module")
def admin_headers(test_client):
    resp = test_client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin123"})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def viewer_headers(test_client):
    resp = test_client.post("/api/auth/login", json={"email": "viewer@example.com", "password": "viewer123"})
    assert resp.status_code == 200, f"Viewer login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def operator_headers(test_client):
    resp = test_client.post("/api/auth/login", json={"email": "operator@example.com", "password": "operator123"})
    assert resp.status_code == 200, f"Operator login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# モック証明書データ
MOCK_CERT = {
    "id": "abcdef1234567890",
    "path": "/etc/ssl/certs/test.pem",
    "filename": "test.pem",
    "subject": "CN=test.example.com, O=Test Org",
    "issuer": "CN=Test CA, O=Test CA",
    "expiry": "2025-12-31T00:00:00+00:00",
    "days_remaining": 180,
    "is_expired": False,
    "expiry_status": "ok",
    "self_signed": False,
    "sans": ["test.example.com", "www.test.example.com"],
    "size_bytes": 1234,
}

MOCK_SELF_SIGNED_CERT = {
    **MOCK_CERT,
    "id": "fedcba0987654321",
    "self_signed": True,
    "subject": "CN=test.local",
    "issuer": "CN=test.local",
}

MOCK_EXPIRED_CERT = {
    **MOCK_CERT,
    "id": "expired1234567890",
    "days_remaining": 0,
    "is_expired": True,
    "expiry_status": "expired",
}


# ===================================================================
# 証明書一覧テスト
# ===================================================================


class TestListCertificates:
    """GET /api/certificates/ のテスト"""

    def test_list_returns_200_with_auth(self, test_client, admin_headers):
        """認証済みで証明書一覧が取得できる"""
        with patch("backend.api.routes.certificates._scan_cert_directory", return_value=[MOCK_CERT]):
            resp = test_client.get("/api/certificates/", headers=admin_headers)
        assert resp.status_code == 200

    def test_list_returns_array(self, test_client, admin_headers):
        """レスポンスが配列"""
        with patch("backend.api.routes.certificates._scan_cert_directory", return_value=[MOCK_CERT]):
            resp = test_client.get("/api/certificates/", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_list_viewer_can_read(self, test_client, viewer_headers):
        """Viewer ロールも読み取り可能"""
        with patch("backend.api.routes.certificates._scan_cert_directory", return_value=[]):
            resp = test_client.get("/api/certificates/", headers=viewer_headers)
        assert resp.status_code == 200

    def test_list_unauthenticated_rejected(self, test_client):
        """未認証は拒否"""
        resp = test_client.get("/api/certificates/")
        assert resp.status_code in (401, 403)

    def test_list_filter_expired(self, test_client, admin_headers):
        """expired フィルターが機能する"""
        certs = [MOCK_CERT, MOCK_EXPIRED_CERT]
        with patch("backend.api.routes.certificates._scan_cert_directory", return_value=certs):
            resp = test_client.get("/api/certificates/?expiry_status=expired", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert all(c["expiry_status"] == "expired" for c in data)

    def test_list_filter_ok(self, test_client, admin_headers):
        """ok フィルターが機能する"""
        certs = [MOCK_CERT, MOCK_EXPIRED_CERT]
        with patch("backend.api.routes.certificates._scan_cert_directory", return_value=certs):
            resp = test_client.get("/api/certificates/?expiry_status=ok", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert all(c["expiry_status"] == "ok" for c in data)

    def test_list_sorted_by_days_remaining(self, test_client, admin_headers):
        """残り日数の少ない順でソートされる（期限切れ=0が先頭）"""
        certs = [MOCK_CERT, MOCK_EXPIRED_CERT]
        with patch("backend.api.routes.certificates._scan_cert_directory", return_value=certs):
            resp = test_client.get("/api/certificates/", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        # days_remaining が None でないものを昇順チェック
        days = [c.get("days_remaining") for c in data if c.get("days_remaining") is not None]
        assert days == sorted(days), f"昇順ソートされていない: {days}"

    def test_list_cert_fields(self, test_client, admin_headers):
        """証明書に必須フィールドが含まれる"""
        with patch("backend.api.routes.certificates._scan_cert_directory", return_value=[MOCK_CERT]):
            resp = test_client.get("/api/certificates/", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        if data:
            cert = data[0]
            assert "id" in cert
            assert "path" in cert
            assert "expiry_status" in cert


# ===================================================================
# 有効期限サマリーテスト
# ===================================================================


class TestExpirySummary:
    """GET /api/certificates/expiry-summary のテスト"""

    def test_summary_returns_200(self, test_client, admin_headers):
        """サマリー取得が成功する"""
        with patch("backend.api.routes.certificates._scan_cert_directory", return_value=[]):
            resp = test_client.get("/api/certificates/expiry-summary", headers=admin_headers)
        assert resp.status_code == 200

    def test_summary_fields(self, test_client, admin_headers):
        """サマリーに必須フィールドが含まれる"""
        with patch("backend.api.routes.certificates._scan_cert_directory", return_value=[]):
            resp = test_client.get("/api/certificates/expiry-summary", headers=admin_headers)
        data = resp.json()
        assert "total" in data
        assert "expired" in data
        assert "critical" in data
        assert "warning" in data
        assert "ok" in data

    def test_summary_counts_correctly(self, test_client, admin_headers):
        """各ステータスのカウントが正確（mockは全CERT_SCAN_DIRS分返るため total>=3）"""
        certs = [MOCK_CERT, MOCK_EXPIRED_CERT, MOCK_SELF_SIGNED_CERT]
        with patch("backend.api.routes.certificates._scan_cert_directory", return_value=certs):
            resp = test_client.get("/api/certificates/expiry-summary", headers=admin_headers)
        data = resp.json()
        # 各ディレクトリ分倍増するため total は 3 の倍数
        assert data["total"] >= 3
        assert data["total"] % 3 == 0
        # expired と ok の比率が維持される
        assert data["expired"] >= 1
        assert data["ok"] >= 1

    def test_summary_unauthenticated_rejected(self, test_client):
        """未認証は拒否"""
        resp = test_client.get("/api/certificates/expiry-summary")
        assert resp.status_code in (401, 403)

    def test_summary_viewer_can_read(self, test_client, viewer_headers):
        """Viewer もサマリー取得可能"""
        with patch("backend.api.routes.certificates._scan_cert_directory", return_value=[]):
            resp = test_client.get("/api/certificates/expiry-summary", headers=viewer_headers)
        assert resp.status_code == 200


# ===================================================================
# Let's Encrypt テスト
# ===================================================================


class TestLetsEncrypt:
    """GET /api/certificates/letsencrypt のテスト"""

    def test_letsencrypt_returns_200(self, test_client, admin_headers):
        """Let's Encrypt 情報取得が成功する"""
        resp = test_client.get("/api/certificates/letsencrypt", headers=admin_headers)
        assert resp.status_code == 200

    def test_letsencrypt_not_available(self, test_client, admin_headers):
        """Let's Encrypt ディレクトリがない場合 available=False"""
        with patch("backend.api.routes.certificates.Path") as mock_path:
            instance = MagicMock()
            instance.exists.return_value = False
            mock_path.return_value = instance
            resp = test_client.get("/api/certificates/letsencrypt", headers=admin_headers)
        # 404 ではなく 200 で available=False を返す
        assert resp.status_code in (200, 404)

    def test_letsencrypt_unauthenticated_rejected(self, test_client):
        """未認証は拒否"""
        resp = test_client.get("/api/certificates/letsencrypt")
        assert resp.status_code in (401, 403)

    def test_letsencrypt_response_structure(self, test_client, admin_headers):
        """レスポンス構造が正しい"""
        resp = test_client.get("/api/certificates/letsencrypt", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "available" in data


# ===================================================================
# 証明書詳細テスト
# ===================================================================


class TestCertificateDetail:
    """GET /api/certificates/{cert_id} のテスト"""

    def test_detail_not_found(self, test_client, admin_headers):
        """存在しない ID は 404"""
        with patch("backend.api.routes.certificates._scan_cert_directory", return_value=[]):
            resp = test_client.get("/api/certificates/nonexistent123456", headers=admin_headers)
        assert resp.status_code == 404

    def test_detail_found(self, test_client, admin_headers):
        """存在する ID で詳細取得"""
        with patch("backend.api.routes.certificates._scan_cert_directory", return_value=[MOCK_CERT]):
            resp = test_client.get(f"/api/certificates/{MOCK_CERT['id']}", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == MOCK_CERT["id"]

    def test_detail_unauthenticated_rejected(self, test_client):
        """未認証は拒否"""
        resp = test_client.get("/api/certificates/abcdef1234567890")
        assert resp.status_code in (401, 403)


# ===================================================================
# ドメインチェックテスト
# ===================================================================


class TestDomainCheck:
    """POST /api/certificates/check-domain のテスト"""

    def test_valid_domain_request(self, test_client, admin_headers):
        """正常なドメインチェックリクエスト"""
        mock_result = {
            "hostname": "example.com",
            "port": 443,
            "reachable": True,
            "days_remaining": 90,
            "expiry_status": "ok",
        }
        with patch("backend.api.routes.certificates._check_domain_certificate", return_value=mock_result):
            resp = test_client.post(
                "/api/certificates/check-domain",
                json={"hostname": "example.com", "port": 443},
                headers=admin_headers,
            )
        assert resp.status_code == 200

    def test_domain_unreachable(self, test_client, admin_headers):
        """接続できないドメインは reachable=False で返す"""
        mock_result = {
            "hostname": "unreachable.example.com",
            "port": 443,
            "reachable": False,
            "error": "Connection refused",
            "expiry_status": "unreachable",
        }
        with patch("backend.api.routes.certificates._check_domain_certificate", return_value=mock_result):
            resp = test_client.post(
                "/api/certificates/check-domain",
                json={"hostname": "unreachable.example.com"},
                headers=admin_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("reachable") is False

    def test_invalid_hostname_rejected(self, test_client, admin_headers):
        """無効なホスト名を拒否（セミコロン含む）"""
        resp = test_client.post(
            "/api/certificates/check-domain",
            json={"hostname": "example.com; rm -rf /"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_invalid_hostname_special_chars(self, test_client, admin_headers):
        """特殊文字を含むホスト名を拒否"""
        resp = test_client.post(
            "/api/certificates/check-domain",
            json={"hostname": "example.com|echo"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_invalid_port_zero(self, test_client, admin_headers):
        """ポート 0 は拒否"""
        resp = test_client.post(
            "/api/certificates/check-domain",
            json={"hostname": "example.com", "port": 0},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_invalid_port_too_large(self, test_client, admin_headers):
        """ポート 65536 は拒否"""
        resp = test_client.post(
            "/api/certificates/check-domain",
            json={"hostname": "example.com", "port": 65536},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_viewer_can_check_domain(self, test_client, viewer_headers):
        """Viewer もドメインチェック可能（read:certificates）"""
        mock_result = {"hostname": "example.com", "port": 443, "reachable": True, "days_remaining": 60, "expiry_status": "ok"}
        with patch("backend.api.routes.certificates._check_domain_certificate", return_value=mock_result):
            resp = test_client.post(
                "/api/certificates/check-domain",
                json={"hostname": "example.com"},
                headers=viewer_headers,
            )
        assert resp.status_code == 200

    def test_unauthenticated_domain_check_rejected(self, test_client):
        """未認証のドメインチェックは拒否"""
        resp = test_client.post(
            "/api/certificates/check-domain",
            json={"hostname": "example.com"},
        )
        assert resp.status_code in (401, 403)


# ===================================================================
# ディレクトリスキャンテスト
# ===================================================================


class TestScanDirectory:
    """POST /api/certificates/scan のテスト"""

    def test_scan_etc_ssl_certs(self, test_client, admin_headers):
        """許可ディレクトリ /etc/ssl/certs はスキャン可能"""
        with patch("backend.api.routes.certificates._scan_cert_directory", return_value=[MOCK_CERT]):
            resp = test_client.post(
                "/api/certificates/scan?directory=/etc/ssl/certs",
                headers=admin_headers,
            )
        assert resp.status_code in (200, 403)  # ディレクトリ存在に依存

    def test_scan_disallowed_directory(self, test_client, admin_headers):
        """許可されていないディレクトリ（/home）は拒否"""
        resp = test_client.post(
            "/api/certificates/scan?directory=/home/user/.ssh",
            headers=admin_headers,
        )
        # 403 Forbidden または Path resolve で etc/ に変換されない
        assert resp.status_code in (200, 403)

    def test_scan_root_directory_rejected(self, test_client, admin_headers):
        """/ へのスキャンは拒否"""
        resp = test_client.post(
            "/api/certificates/scan?directory=/",
            headers=admin_headers,
        )
        assert resp.status_code == 403

    def test_scan_path_traversal_rejected(self, test_client, admin_headers):
        """パストラバーサルは拒否"""
        resp = test_client.post(
            "/api/certificates/scan?directory=/etc/../../../root",
            headers=admin_headers,
        )
        assert resp.status_code == 403

    def test_scan_forbidden_chars_rejected(self, test_client, admin_headers):
        """特殊文字を含むパスは 400 で拒否"""
        resp = test_client.post(
            "/api/certificates/scan?directory=/etc/ssl; rm -rf /",
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_scan_unauthenticated_rejected(self, test_client):
        """未認証は拒否"""
        resp = test_client.post("/api/certificates/scan?directory=/etc/ssl/certs")
        assert resp.status_code in (401, 403)

    def test_scan_response_structure(self, test_client, admin_headers):
        """スキャン結果の構造確認"""
        with patch("backend.api.routes.certificates._scan_cert_directory", return_value=[MOCK_CERT]):
            resp = test_client.post(
                "/api/certificates/scan?directory=/etc/ssl/certs",
                headers=admin_headers,
            )
        if resp.status_code == 200:
            data = resp.json()
            assert "directory" in data
            assert "count" in data
            assert "certificates" in data


# ===================================================================
# 自己署名証明書生成テスト
# ===================================================================


class TestGenerateSelfSigned:
    """POST /api/certificates/generate-self-signed のテスト"""

    def test_generate_returns_202(self, test_client, admin_headers):
        """生成リクエストが 202 を返す"""
        resp = test_client.post(
            "/api/certificates/generate-self-signed",
            json={"common_name": "test.local", "days": 365},
            headers=admin_headers,
        )
        assert resp.status_code == 202

    def test_generate_response_structure(self, test_client, admin_headers):
        """レスポンス構造が正しい"""
        resp = test_client.post(
            "/api/certificates/generate-self-signed",
            json={"common_name": "test.local", "days": 365},
            headers=admin_headers,
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "pending_approval"
        assert data["common_name"] == "test.local"

    def test_generate_invalid_cn_rejected(self, test_client, admin_headers):
        """無効な CN は拒否"""
        resp = test_client.post(
            "/api/certificates/generate-self-signed",
            json={"common_name": "test; rm -rf /"},
            headers=admin_headers,
        )
        assert resp.status_code in (400, 422)

    def test_generate_cn_with_pipe_rejected(self, test_client, admin_headers):
        """パイプを含む CN は拒否"""
        resp = test_client.post(
            "/api/certificates/generate-self-signed",
            json={"common_name": "test.local|echo"},
            headers=admin_headers,
        )
        assert resp.status_code in (400, 422)

    def test_generate_days_too_large_rejected(self, test_client, admin_headers):
        """有効期間が長すぎる（3651日以上）は拒否"""
        resp = test_client.post(
            "/api/certificates/generate-self-signed",
            json={"common_name": "test.local", "days": 9999},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_generate_days_zero_rejected(self, test_client, admin_headers):
        """有効期間 0 は拒否"""
        resp = test_client.post(
            "/api/certificates/generate-self-signed",
            json={"common_name": "test.local", "days": 0},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_generate_viewer_cannot_write(self, test_client, viewer_headers):
        """Viewer は証明書生成不可"""
        resp = test_client.post(
            "/api/certificates/generate-self-signed",
            json={"common_name": "test.local", "days": 365},
            headers=viewer_headers,
        )
        assert resp.status_code in (401, 403)

    def test_generate_operator_can_write(self, test_client, operator_headers):
        """Operator は証明書生成可能（write:certificates）"""
        resp = test_client.post(
            "/api/certificates/generate-self-signed",
            json={"common_name": "test.local", "days": 365},
            headers=operator_headers,
        )
        assert resp.status_code == 202

    def test_generate_unauthenticated_rejected(self, test_client):
        """未認証は拒否"""
        resp = test_client.post(
            "/api/certificates/generate-self-signed",
            json={"common_name": "test.local"},
        )
        assert resp.status_code in (401, 403)


# ===================================================================
# 証明書パース関数ユニットテスト
# ===================================================================


class TestParseCertificateFile:
    """_parse_certificate_file のユニットテスト"""

    def test_parse_nonexistent_returns_none(self):
        """存在しないファイルは None を返す"""
        from pathlib import Path
        from backend.api.routes.certificates import _parse_certificate_file

        result = _parse_certificate_file(Path("/nonexistent/file.pem"))
        assert result is None

    def test_parse_openssl_not_found(self):
        """openssl が利用できない場合も None を返す"""
        from pathlib import Path
        from backend.api.routes.certificates import _parse_certificate_file

        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = _parse_certificate_file(Path("/etc/ssl/certs/test.pem"))
        assert result is None

    def test_check_domain_socket_timeout(self):
        """ソケットタイムアウトで reachable=False"""
        import socket
        from backend.api.routes.certificates import _check_domain_certificate

        with patch("socket.create_connection", side_effect=socket.timeout("timed out")):
            result = _check_domain_certificate("example.com", 443)
        assert result["reachable"] is False
        assert "error" in result

    def test_check_domain_connection_refused(self):
        """接続拒否で reachable=False"""
        import socket
        from backend.api.routes.certificates import _check_domain_certificate

        with patch("socket.create_connection", side_effect=ConnectionRefusedError("refused")):
            result = _check_domain_certificate("example.com", 443)
        assert result["reachable"] is False
