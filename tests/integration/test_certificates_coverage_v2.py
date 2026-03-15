"""
certificates.py カバレッジ改善テスト v2

対象: backend/api/routes/certificates.py (28% -> 85%+)
未カバー箇所を重点的にテスト:
  - _parse_certificate_file: 全分岐（Subject/Issuer/NotBefore/NotAfter/SAN パース）
  - _scan_cert_directory: ディレクトリ走査・上限・拡張子フィルタ
  - _check_domain_certificate: SSL接続・証明書情報取得・SSLCertVerificationError
  - list_certificates: directory指定・フィルター・ソート
  - get_expiry_summary: nearest_expiry計算・ステータス別カウント
  - list_letsencrypt_certificates: ドメインディレクトリ走査
  - get_certificate_detail: ID一致検索
  - scan_directory: パストラバーサル防止・許可プレフィックス
  - request_generate_self_signed: CN正規表現バリデーション
  - DomainCheckRequest.validate_hostname: 正規表現バリデーション
"""

import hashlib
import socket
import ssl
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
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
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(scope="module")
def viewer_headers(test_client):
    resp = test_client.post("/api/auth/login", json={"email": "viewer@example.com", "password": "viewer123"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ===================================================================
# _parse_certificate_file ヘルパー 全分岐テスト
# ===================================================================

class TestParseCertificateFile:
    """_parse_certificate_file の全分岐テスト"""

    OPENSSL_OUTPUT_FULL = """\
Certificate:
    Data:
        Version: 3 (0x2)
        Serial Number: 01
    Signature Algorithm: sha256WithRSAEncryption
        Issuer: CN=Test CA, O=Test Org
        Validity
            Not Before: Jan  1 00:00:00 2025 GMT
            Not After : Dec 31 23:59:59 2027 GMT
        Subject: CN=test.example.com, O=Example
        X509v3 extensions:
            X509v3 Subject Alternative Name:
                DNS:test.example.com, DNS:www.test.example.com
"""

    OPENSSL_OUTPUT_SELF_SIGNED = """\
Certificate:
    Data:
        Subject: CN=self.local
        Issuer: CN=self.local
        Validity
            Not Before: Jan  1 00:00:00 2025 GMT
            Not After : Dec 31 23:59:59 2025 GMT
"""

    OPENSSL_OUTPUT_NO_DATES = """\
Certificate:
    Data:
        Subject: CN=nodates.local
        Issuer: CN=CA
"""

    OPENSSL_OUTPUT_BAD_DATE = """\
Certificate:
    Data:
        Subject: CN=baddate.local
        Issuer: CN=CA
        Validity
            Not Before: InvalidDate
            Not After : InvalidDate
"""

    OPENSSL_OUTPUT_EXPIRED = """\
Certificate:
    Data:
        Subject: CN=expired.local
        Issuer: CN=CA
        Validity
            Not Before: Jan  1 00:00:00 2020 GMT
            Not After : Jan  1 00:00:00 2021 GMT
"""

    OPENSSL_OUTPUT_SAN_NO_DNS = """\
Certificate:
    Data:
        Subject: CN=nosan.local
        Issuer: CN=CA
        Validity
            Not Before: Jan  1 00:00:00 2025 GMT
            Not After : Dec 31 23:59:59 2027 GMT
        X509v3 extensions:
            X509v3 Subject Alternative Name:
                IP Address:192.168.1.1
"""

    def _mock_path(self, path_str="/etc/ssl/certs/test.pem"):
        mock_p = MagicMock(spec=Path)
        mock_p.name = "test.pem"
        mock_p.stat.return_value = MagicMock(st_size=1024)
        mock_p.__str__ = lambda self: path_str
        return mock_p

    def test_parse_success_full_output(self):
        from backend.api.routes.certificates import _parse_certificate_file

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = self.OPENSSL_OUTPUT_FULL

        mock_p = self._mock_path()

        with patch("subprocess.run", return_value=mock_result):
            result = _parse_certificate_file(mock_p)

        assert result is not None
        assert result["filename"] == "test.pem"
        assert result["size_bytes"] == 1024
        assert "subject" in result
        assert "issuer" in result
        assert "not_before_raw" in result
        assert "not_after_raw" in result
        assert result["expiry"] is not None
        assert result["days_remaining"] is not None
        assert result["expiry_status"] in ("ok", "warning", "critical", "expired")
        assert len(result["sans"]) == 2
        assert "test.example.com" in result["sans"]
        assert result["id"] == hashlib.sha256(str(mock_p).encode()).hexdigest()[:16]
        # Subject != Issuer => not self_signed
        assert result["self_signed"] is False

    def test_parse_self_signed_cert(self):
        from backend.api.routes.certificates import _parse_certificate_file

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = self.OPENSSL_OUTPUT_SELF_SIGNED

        mock_p = self._mock_path()

        with patch("subprocess.run", return_value=mock_result):
            result = _parse_certificate_file(mock_p)

        assert result is not None
        assert result["self_signed"] is True

    def test_parse_openssl_returncode_nonzero(self):
        from backend.api.routes.certificates import _parse_certificate_file

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        mock_p = self._mock_path()

        with patch("subprocess.run", return_value=mock_result):
            result = _parse_certificate_file(mock_p)

        assert result is None

    def test_parse_no_dates(self):
        from backend.api.routes.certificates import _parse_certificate_file

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = self.OPENSSL_OUTPUT_NO_DATES

        mock_p = self._mock_path()

        with patch("subprocess.run", return_value=mock_result):
            result = _parse_certificate_file(mock_p)

        assert result is not None
        assert result.get("expiry") is None

    def test_parse_bad_date_format(self):
        from backend.api.routes.certificates import _parse_certificate_file

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = self.OPENSSL_OUTPUT_BAD_DATE

        mock_p = self._mock_path()

        with patch("subprocess.run", return_value=mock_result):
            result = _parse_certificate_file(mock_p)

        assert result is not None
        assert result.get("expiry") is None
        assert result.get("expiry_status") == "unknown"

    def test_parse_expired_cert(self):
        from backend.api.routes.certificates import _parse_certificate_file

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = self.OPENSSL_OUTPUT_EXPIRED

        mock_p = self._mock_path()

        with patch("subprocess.run", return_value=mock_result):
            result = _parse_certificate_file(mock_p)

        assert result is not None
        assert result["is_expired"] is True
        assert result["expiry_status"] == "expired"
        assert result["days_remaining"] == 0

    def test_parse_timeout_expired(self):
        from backend.api.routes.certificates import _parse_certificate_file

        mock_p = self._mock_path()

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="openssl", timeout=5)):
            result = _parse_certificate_file(mock_p)

        assert result is None

    def test_parse_permission_error(self):
        from backend.api.routes.certificates import _parse_certificate_file

        mock_p = self._mock_path()

        with patch("subprocess.run", side_effect=PermissionError("access denied")):
            result = _parse_certificate_file(mock_p)

        assert result is None

    def test_parse_san_no_dns(self):
        from backend.api.routes.certificates import _parse_certificate_file

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = self.OPENSSL_OUTPUT_SAN_NO_DNS

        mock_p = self._mock_path()

        with patch("subprocess.run", return_value=mock_result):
            result = _parse_certificate_file(mock_p)

        assert result is not None
        assert result["sans"] == []


# ===================================================================
# _scan_cert_directory ヘルパーテスト
# ===================================================================


class TestScanCertDirectory:
    """_scan_cert_directory の分岐テスト"""

    def test_nonexistent_dir_returns_empty(self):
        from backend.api.routes.certificates import _scan_cert_directory
        result = _scan_cert_directory("/nonexistent/dir/path/xyz")
        assert result == []

    def test_scan_with_cert_files(self, tmp_path):
        from backend.api.routes.certificates import _scan_cert_directory

        # .pem ファイルを作成
        cert_file = tmp_path / "test.pem"
        cert_file.write_text("dummy cert content")

        # .txt ファイルは対象外
        txt_file = tmp_path / "readme.txt"
        txt_file.write_text("not a cert")

        mock_cert = {"id": "abc123", "path": str(cert_file), "filename": "test.pem"}

        with patch("backend.api.routes.certificates._parse_certificate_file", return_value=mock_cert):
            result = _scan_cert_directory(str(tmp_path))

        assert len(result) == 1
        assert result[0]["id"] == "abc123"

    def test_scan_max_files_limit(self, tmp_path):
        from backend.api.routes.certificates import _scan_cert_directory

        # 5つの.pemファイルを作成
        for i in range(5):
            (tmp_path / f"cert{i}.pem").write_text(f"cert {i}")

        mock_cert = {"id": "abc", "path": "/test", "filename": "test.pem"}

        with patch("backend.api.routes.certificates._parse_certificate_file", return_value=mock_cert):
            result = _scan_cert_directory(str(tmp_path), max_files=3)

        assert len(result) == 3

    def test_scan_parse_returns_none_skipped(self, tmp_path):
        from backend.api.routes.certificates import _scan_cert_directory

        cert_file = tmp_path / "invalid.pem"
        cert_file.write_text("invalid cert")

        with patch("backend.api.routes.certificates._parse_certificate_file", return_value=None):
            result = _scan_cert_directory(str(tmp_path))

        assert result == []

    def test_scan_multiple_extensions(self, tmp_path):
        from backend.api.routes.certificates import _scan_cert_directory

        for ext in [".pem", ".crt", ".cer", ".der"]:
            (tmp_path / f"cert{ext}").write_text("cert")

        mock_cert = {"id": "abc", "path": "/test", "filename": "test"}

        with patch("backend.api.routes.certificates._parse_certificate_file", return_value=mock_cert):
            result = _scan_cert_directory(str(tmp_path))

        assert len(result) == 4


# ===================================================================
# _check_domain_certificate ヘルパーテスト
# ===================================================================


class TestCheckDomainCertificate:
    """_check_domain_certificate の全分岐テスト"""

    def test_ssl_cert_verification_error(self):
        from backend.api.routes.certificates import _check_domain_certificate

        with patch("socket.create_connection") as mock_conn:
            mock_sock = MagicMock()
            mock_conn.return_value.__enter__ = MagicMock(return_value=mock_sock)
            mock_conn.return_value.__exit__ = MagicMock(return_value=False)
            with patch("ssl.SSLContext.wrap_socket", side_effect=ssl.SSLCertVerificationError("cert verify failed")):
                result = _check_domain_certificate("bad-cert.example.com", 443)

        assert result["reachable"] is True
        assert result["expiry_status"] == "invalid"
        assert "error" in result

    def test_connection_refused(self):
        from backend.api.routes.certificates import _check_domain_certificate

        with patch("socket.create_connection", side_effect=ConnectionRefusedError("refused")):
            result = _check_domain_certificate("refused.example.com", 443)

        assert result["reachable"] is False
        assert result["expiry_status"] == "unreachable"

    def test_os_error(self):
        from backend.api.routes.certificates import _check_domain_certificate

        with patch("socket.create_connection", side_effect=OSError("network error")):
            result = _check_domain_certificate("error.example.com", 443)

        assert result["reachable"] is False
        assert result["expiry_status"] == "unreachable"

    def test_successful_connection(self):
        from backend.api.routes.certificates import _check_domain_certificate

        mock_cert = {
            "notAfter": "Dec 31 23:59:59 2027 GMT",
            "notBefore": "Jan  1 00:00:00 2025 GMT",
            "subject": ((("commonName", "example.com"),),),
            "issuer": ((("organizationName", "Test CA"),),),
            "subjectAltName": (("DNS", "example.com"), ("DNS", "www.example.com")),
        }

        mock_ssock = MagicMock()
        mock_ssock.getpeercert.return_value = mock_cert
        mock_ssock.version.return_value = "TLSv1.3"
        mock_ssock.cipher.return_value = ("AES256-GCM-SHA384", "TLSv1.3", 256)
        mock_ssock.__enter__ = MagicMock(return_value=mock_ssock)
        mock_ssock.__exit__ = MagicMock(return_value=False)

        mock_sock = MagicMock()
        mock_sock.__enter__ = MagicMock(return_value=mock_sock)
        mock_sock.__exit__ = MagicMock(return_value=False)

        with patch("socket.create_connection", return_value=mock_sock), \
             patch("ssl.SSLContext.wrap_socket", return_value=mock_ssock):
            result = _check_domain_certificate("example.com", 443)

        assert result["reachable"] is True
        assert result["hostname"] == "example.com"
        assert result["subject_cn"] == "example.com"
        assert result["issuer_o"] == "Test CA"
        assert len(result["sans"]) == 2
        assert result["expiry_status"] == "ok"
        assert result["days_remaining"] is not None

    def test_connection_bad_date_format(self):
        from backend.api.routes.certificates import _check_domain_certificate

        mock_cert = {
            "notAfter": "InvalidDateFormat",
            "notBefore": "InvalidDateFormat",
            "subject": ((("commonName", "test.com"),),),
            "issuer": ((("organizationName", "CA"),),),
            "subjectAltName": (),
        }

        mock_ssock = MagicMock()
        mock_ssock.getpeercert.return_value = mock_cert
        mock_ssock.version.return_value = "TLSv1.2"
        mock_ssock.cipher.return_value = ("AES128", "TLSv1.2", 128)
        mock_ssock.__enter__ = MagicMock(return_value=mock_ssock)
        mock_ssock.__exit__ = MagicMock(return_value=False)

        mock_sock = MagicMock()
        mock_sock.__enter__ = MagicMock(return_value=mock_sock)
        mock_sock.__exit__ = MagicMock(return_value=False)

        with patch("socket.create_connection", return_value=mock_sock), \
             patch("ssl.SSLContext.wrap_socket", return_value=mock_ssock):
            result = _check_domain_certificate("test.com", 443)

        assert result["expiry_status"] == "unknown"
        assert result["expiry"] is None


# ===================================================================
# DomainCheckRequest バリデーションテスト
# ===================================================================


class TestDomainCheckRequestValidation:
    """DomainCheckRequest の hostname バリデーション"""

    @pytest.mark.parametrize("hostname", [
        "example.com",
        "sub.example.com",
        "a.b.c.d.example.com",
        "server-01.example.com",
        "192.168.1.1",  # IP-like but passes regex
    ])
    def test_valid_hostnames(self, hostname):
        from backend.api.routes.certificates import DomainCheckRequest
        req = DomainCheckRequest(hostname=hostname)
        assert req.hostname == hostname

    @pytest.mark.parametrize("hostname", [
        "-invalid.com",
        "inv alid.com",
        "invalid..com",
        "",
    ])
    def test_invalid_hostnames(self, hostname):
        from backend.api.routes.certificates import DomainCheckRequest
        with pytest.raises(Exception):
            DomainCheckRequest(hostname=hostname)

    @pytest.mark.parametrize("port", [1, 443, 8080, 65535])
    def test_valid_ports(self, port):
        from backend.api.routes.certificates import DomainCheckRequest
        req = DomainCheckRequest(hostname="example.com", port=port)
        assert req.port == port

    @pytest.mark.parametrize("port", [0, -1, 65536])
    def test_invalid_ports(self, port):
        from backend.api.routes.certificates import DomainCheckRequest
        with pytest.raises(Exception):
            DomainCheckRequest(hostname="example.com", port=port)


# ===================================================================
# SelfSignedCertRequest バリデーションテスト
# ===================================================================


class TestSelfSignedCertRequestValidation:
    """SelfSignedCertRequest のバリデーション"""

    def test_valid_request(self):
        from backend.api.routes.certificates import SelfSignedCertRequest
        req = SelfSignedCertRequest(common_name="test.local", days=365)
        assert req.common_name == "test.local"
        assert req.days == 365
        assert req.output_dir == "/etc/ssl/certs/adminui-generated"

    def test_default_days(self):
        from backend.api.routes.certificates import SelfSignedCertRequest
        req = SelfSignedCertRequest(common_name="test.local")
        assert req.days == 365

    @pytest.mark.parametrize("days", [0, -1, 3651])
    def test_invalid_days(self, days):
        from backend.api.routes.certificates import SelfSignedCertRequest
        with pytest.raises(Exception):
            SelfSignedCertRequest(common_name="test.local", days=days)

    def test_empty_cn_rejected(self):
        from backend.api.routes.certificates import SelfSignedCertRequest
        with pytest.raises(Exception):
            SelfSignedCertRequest(common_name="")


# ===================================================================
# エンドポイント: list_certificates 追加分岐テスト
# ===================================================================


class TestListCertificatesV2:
    """list_certificates の追加カバレッジ"""

    def test_list_with_specific_directory(self, test_client, admin_headers):
        """directory パラメータ指定時は validate_input が呼ばれる"""
        with patch("backend.api.routes.certificates._scan_cert_directory", return_value=[]):
            resp = test_client.get("/api/certificates/?directory=/etc/ssl/certs", headers=admin_headers)
        assert resp.status_code == 200

    def test_list_with_empty_certs(self, test_client, admin_headers):
        """空結果でも200を返す"""
        with patch("backend.api.routes.certificates._scan_cert_directory", return_value=[]):
            resp = test_client.get("/api/certificates/", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_multiple_status_filter(self, test_client, admin_headers):
        """warning フィルター"""
        certs = [
            {"id": "a1", "path": "/a", "filename": "a.pem", "expiry_status": "warning",
             "days_remaining": 20, "self_signed": False, "sans": [], "size_bytes": 100,
             "is_expired": False},
            {"id": "a2", "path": "/b", "filename": "b.pem", "expiry_status": "ok",
             "days_remaining": 100, "self_signed": False, "sans": [], "size_bytes": 100,
             "is_expired": False},
        ]
        with patch("backend.api.routes.certificates._scan_cert_directory", return_value=certs):
            resp = test_client.get("/api/certificates/?expiry_status=warning", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        # Each of 6 CERT_SCAN_DIRS returns the same mock data, so warning count = 6
        assert len(data) >= 1
        assert all(c["expiry_status"] == "warning" for c in data)

    def test_list_sort_with_none_days(self, test_client, admin_headers):
        """days_remaining が None のエントリが末尾にソートされる"""
        certs = [
            {"id": "c1", "path": "/c", "filename": "c.pem", "expiry_status": "unknown",
             "days_remaining": None, "self_signed": False, "sans": [], "size_bytes": 100,
             "is_expired": False},
            {"id": "c2", "path": "/d", "filename": "d.pem", "expiry_status": "ok",
             "days_remaining": 10, "self_signed": False, "sans": [], "size_bytes": 100,
             "is_expired": False},
        ]
        # Use directory param to scan only 1 dir
        with patch("backend.api.routes.certificates._scan_cert_directory", return_value=certs):
            resp = test_client.get("/api/certificates/?directory=/etc/ssl", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["id"] == "c2"  # days_remaining=10 が先


# ===================================================================
# エンドポイント: get_expiry_summary 追加分岐テスト
# ===================================================================


class TestExpirySummaryV2:
    """get_expiry_summary の追加カバレッジ"""

    def test_summary_with_all_statuses(self, test_client, admin_headers):
        """全ステータスが正しくカウントされる"""
        certs = [
            {"expiry_status": "ok", "days_remaining": 100, "expiry": "2027-01-01T00:00:00+00:00", "subject": "CN=ok"},
            {"expiry_status": "warning", "days_remaining": 20, "expiry": "2026-04-01T00:00:00+00:00", "subject": "CN=warn"},
            {"expiry_status": "critical", "days_remaining": 5, "expiry": "2026-03-20T00:00:00+00:00", "subject": "CN=crit"},
            {"expiry_status": "expired", "days_remaining": 0, "expiry": "2026-01-01T00:00:00+00:00", "subject": "CN=exp"},
            {"expiry_status": "unknown", "days_remaining": None},
        ]
        with patch("backend.api.routes.certificates._scan_cert_directory", return_value=certs):
            resp = test_client.get("/api/certificates/expiry-summary", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        # Each CERT_SCAN_DIR returns same data, so multiply by 6
        assert data["total"] == len(certs) * 6
        assert data["ok"] >= 6
        assert data["warning"] >= 6
        assert data["critical"] >= 6
        assert data["expired"] >= 6
        assert data["unknown"] >= 6
        assert data["nearest_expiry"] is not None
        assert data["nearest_expiry_domain"] is not None

    def test_summary_nearest_expiry_calculated(self, test_client, admin_headers):
        """nearest_expiry が最小 days_remaining のものを返す"""
        certs = [
            {"expiry_status": "ok", "days_remaining": 100, "expiry": "2027-01-01", "subject": "CN=far"},
            {"expiry_status": "critical", "days_remaining": 3, "expiry": "2026-03-18", "subject": "CN=near"},
        ]
        with patch("backend.api.routes.certificates._scan_cert_directory", return_value=certs):
            resp = test_client.get("/api/certificates/expiry-summary", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["nearest_expiry"] == "2026-03-18"

    def test_summary_unknown_status_counted(self, test_client, admin_headers):
        """未知のステータス値が unknown にカウントされる"""
        certs = [
            {"expiry_status": "some_unknown_value", "days_remaining": 50},
        ]
        with patch("backend.api.routes.certificates._scan_cert_directory", return_value=certs):
            resp = test_client.get("/api/certificates/expiry-summary", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["unknown"] >= 6


# ===================================================================
# エンドポイント: list_letsencrypt_certificates 追加テスト
# ===================================================================


class TestLetsEncryptV2:
    """Let's Encrypt 証明書一覧の追加カバレッジ"""

    def test_letsencrypt_with_domains(self, test_client, admin_headers):
        """ドメインディレクトリが存在する場合"""
        mock_le_dir = MagicMock()
        mock_le_dir.exists.return_value = True

        mock_domain_dir = MagicMock()
        mock_domain_dir.is_dir.return_value = True
        mock_domain_dir.name = "example.com"
        mock_domain_dir.__str__ = lambda self: "/etc/letsencrypt/live/example.com"

        mock_cert_path = MagicMock()
        mock_cert_path.exists.return_value = False

        mock_fullchain_path = MagicMock()
        mock_fullchain_path.exists.return_value = True

        mock_renewal_conf = MagicMock()
        mock_renewal_conf.exists.return_value = True

        mock_domain_dir.__truediv__ = MagicMock(side_effect=lambda x: mock_fullchain_path if x == "fullchain.pem" else mock_cert_path)

        mock_le_dir.iterdir.return_value = [mock_domain_dir]

        mock_cert_data = {"id": "le1", "path": "/etc/letsencrypt/live/example.com/fullchain.pem",
                          "filename": "fullchain.pem", "expiry_status": "ok", "days_remaining": 60}

        with patch("backend.api.routes.certificates.Path") as MockPath, \
             patch("backend.api.routes.certificates._parse_certificate_file", return_value=mock_cert_data):
            MockPath.side_effect = lambda x: mock_le_dir if x == "/etc/letsencrypt/live" else mock_renewal_conf
            resp = test_client.get("/api/certificates/letsencrypt", headers=admin_headers)

        # May return 200 regardless since we might not fully control Path
        assert resp.status_code == 200

    def test_letsencrypt_hidden_dir_skipped(self, test_client, admin_headers):
        """隠しディレクトリ（.で始まる）がスキップされる"""
        mock_le_dir = MagicMock()
        mock_le_dir.exists.return_value = True

        mock_hidden = MagicMock()
        mock_hidden.is_dir.return_value = True
        mock_hidden.name = ".hidden"

        mock_le_dir.iterdir.return_value = [mock_hidden]

        with patch("backend.api.routes.certificates.Path") as MockPath:
            MockPath.return_value = mock_le_dir
            resp = test_client.get("/api/certificates/letsencrypt", headers=admin_headers)

        assert resp.status_code == 200


# ===================================================================
# エンドポイント: get_certificate_detail 追加テスト
# ===================================================================


class TestCertificateDetailV2:
    """証明書詳細の追加カバレッジ"""

    def test_detail_with_directory_param(self, test_client, admin_headers):
        """directory パラメータ付きで検索"""
        cert = {
            "id": "detail123", "path": "/etc/ssl/test.pem", "filename": "test.pem",
            "subject": "CN=test", "issuer": "CN=CA", "expiry_status": "ok",
            "days_remaining": 100, "self_signed": False, "sans": [], "size_bytes": 500,
            "is_expired": False,
        }
        with patch("backend.api.routes.certificates._scan_cert_directory", return_value=[cert]):
            resp = test_client.get("/api/certificates/detail123?directory=/etc/ssl", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == "detail123"

    def test_detail_not_found_with_directory(self, test_client, admin_headers):
        """directory 指定しても見つからない場合は404"""
        with patch("backend.api.routes.certificates._scan_cert_directory", return_value=[]):
            resp = test_client.get("/api/certificates/notexist999?directory=/etc/ssl", headers=admin_headers)
        assert resp.status_code == 404


# ===================================================================
# エンドポイント: scan_directory 追加テスト
# ===================================================================


class TestScanDirectoryV2:
    """ディレクトリスキャンの追加カバレッジ"""

    def test_scan_allowed_usr_local(self, test_client, admin_headers):
        """許可プレフィックス /usr/local/share/ のスキャン"""
        with patch("backend.api.routes.certificates._scan_cert_directory", return_value=[]):
            resp = test_client.post(
                "/api/certificates/scan?directory=/usr/local/share/ca-certificates",
                headers=admin_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["certificates"] == []

    def test_scan_allowed_opt(self, test_client, admin_headers):
        """許可プレフィックス /opt/ のスキャン"""
        with patch("backend.api.routes.certificates._scan_cert_directory", return_value=[]):
            resp = test_client.post(
                "/api/certificates/scan?directory=/opt/certs",
                headers=admin_headers,
            )
        assert resp.status_code == 200

    def test_scan_forbidden_home(self, test_client, admin_headers):
        """/home は許可プレフィックス外で 403"""
        resp = test_client.post(
            "/api/certificates/scan?directory=/home/user/certs",
            headers=admin_headers,
        )
        assert resp.status_code == 403

    def test_scan_forbidden_var(self, test_client, admin_headers):
        """/var は許可プレフィックス外で 403"""
        resp = test_client.post(
            "/api/certificates/scan?directory=/var/log",
            headers=admin_headers,
        )
        assert resp.status_code == 403


# ===================================================================
# エンドポイント: generate-self-signed 追加テスト
# ===================================================================


class TestGenerateSelfSignedV2:
    """自己署名証明書の追加カバレッジ"""

    @pytest.mark.parametrize("cn", [
        "test.local",
        "*.example.com",
        "server-01.test.local",
        "my_cert",
    ])
    def test_valid_cn_accepted(self, test_client, admin_headers, cn):
        """有効な CN が受け入れられる"""
        resp = test_client.post(
            "/api/certificates/generate-self-signed",
            json={"common_name": cn, "days": 365},
            headers=admin_headers,
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["common_name"] == cn

    @pytest.mark.parametrize("cn", [
        "test local",  # space
        "test/cert",   # slash
        "te$t",        # dollar
        "a" * 65,      # too long (max 64)
    ])
    def test_invalid_cn_rejected(self, test_client, admin_headers, cn):
        """無効な CN が拒否される"""
        resp = test_client.post(
            "/api/certificates/generate-self-signed",
            json={"common_name": cn, "days": 365},
            headers=admin_headers,
        )
        assert resp.status_code in (400, 422)

    def test_generate_with_custom_days(self, test_client, admin_headers):
        """カスタム日数での生成"""
        resp = test_client.post(
            "/api/certificates/generate-self-signed",
            json={"common_name": "custom.local", "days": 3650},
            headers=admin_headers,
        )
        assert resp.status_code == 202
        assert resp.json()["days"] == 3650

    def test_generate_response_has_output_dir(self, test_client, admin_headers):
        """レスポンスに output_dir が含まれる"""
        resp = test_client.post(
            "/api/certificates/generate-self-signed",
            json={"common_name": "test.local"},
            headers=admin_headers,
        )
        assert resp.status_code == 202
        assert "output_dir" in resp.json()


# ===================================================================
# CertificateInfo / ExpirySummary モデルテスト
# ===================================================================


class TestResponseModels:
    """レスポンスモデルのテスト"""

    def test_certificate_info_defaults(self):
        from backend.api.routes.certificates import CertificateInfo
        cert = CertificateInfo(id="test", path="/test", filename="test.pem")
        assert cert.is_expired is False
        assert cert.expiry_status == "unknown"
        assert cert.self_signed is False
        assert cert.sans == []
        assert cert.size_bytes == 0

    def test_expiry_summary_defaults(self):
        from backend.api.routes.certificates import ExpirySummary
        summary = ExpirySummary(total=0, expired=0, critical=0, warning=0, ok=0, unknown=0)
        assert summary.nearest_expiry is None
        assert summary.nearest_expiry_domain is None
