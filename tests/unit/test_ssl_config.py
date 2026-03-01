"""
SSL/HTTPS 設定のユニットテスト

以下を検証する:
- nginx 設定ファイルの存在と内容
- scripts/ の実行可能ビット
- prod.json のセキュリティ設定
"""

import json
import os
import stat
from pathlib import Path

import pytest

# プロジェクトルート
PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestNginxConfigExists:
    """nginx 設定ファイルの存在確認"""

    def test_adminui_conf_exists(self) -> None:
        """config/nginx/adminui.conf が存在すること"""
        conf = PROJECT_ROOT / "config" / "nginx" / "adminui.conf"
        assert conf.exists(), f"nginx 設定ファイルが見つかりません: {conf}"

    def test_adminui_http_only_conf_exists(self) -> None:
        """config/nginx/adminui-http-only.conf が存在すること"""
        conf = PROJECT_ROOT / "config" / "nginx" / "adminui-http-only.conf"
        assert conf.exists(), f"HTTP only 設定ファイルが見つかりません: {conf}"


class TestNginxSslDirectives:
    """nginx 設定に SSL ディレクティブが含まれること"""

    @pytest.fixture(scope="class")
    def nginx_conf_content(self) -> str:
        """adminui.conf の内容を返す"""
        conf = PROJECT_ROOT / "config" / "nginx" / "adminui.conf"
        return conf.read_text(encoding="utf-8")

    def test_ssl_certificate_directive(self, nginx_conf_content: str) -> None:
        """ssl_certificate ディレクティブが含まれること"""
        assert "ssl_certificate " in nginx_conf_content, \
            "nginx 設定に ssl_certificate ディレクティブがありません"

    def test_ssl_certificate_key_directive(self, nginx_conf_content: str) -> None:
        """ssl_certificate_key ディレクティブが含まれること"""
        assert "ssl_certificate_key " in nginx_conf_content, \
            "nginx 設定に ssl_certificate_key ディレクティブがありません"

    def test_ssl_certificate_path(self, nginx_conf_content: str) -> None:
        """証明書パスが /etc/ssl/adminui/server.crt であること"""
        assert "/etc/ssl/adminui/server.crt" in nginx_conf_content, \
            "ssl_certificate のパスが /etc/ssl/adminui/server.crt ではありません"

    def test_ssl_key_path(self, nginx_conf_content: str) -> None:
        """秘密鍵パスが /etc/ssl/adminui/server.key であること"""
        assert "/etc/ssl/adminui/server.key" in nginx_conf_content, \
            "ssl_certificate_key のパスが /etc/ssl/adminui/server.key ではありません"


class TestNginxTlsProtocols:
    """nginx 設定に TLSv1.2/TLSv1.3 のみが設定されていること"""

    @pytest.fixture(scope="class")
    def nginx_conf_content(self) -> str:
        """adminui.conf の内容を返す"""
        conf = PROJECT_ROOT / "config" / "nginx" / "adminui.conf"
        return conf.read_text(encoding="utf-8")

    def test_tls_protocols_directive_present(self, nginx_conf_content: str) -> None:
        """ssl_protocols ディレクティブが含まれること"""
        assert "ssl_protocols " in nginx_conf_content, \
            "nginx 設定に ssl_protocols ディレクティブがありません"

    def test_tlsv12_enabled(self, nginx_conf_content: str) -> None:
        """TLSv1.2 が有効であること"""
        assert "TLSv1.2" in nginx_conf_content, \
            "TLSv1.2 が ssl_protocols に含まれていません"

    def test_tlsv13_enabled(self, nginx_conf_content: str) -> None:
        """TLSv1.3 が有効であること"""
        assert "TLSv1.3" in nginx_conf_content, \
            "TLSv1.3 が ssl_protocols に含まれていません"

    def test_tlsv10_not_present(self, nginx_conf_content: str) -> None:
        """TLSv1.0 が無効であること (古い脆弱なプロトコル)"""
        assert "TLSv1.0" not in nginx_conf_content, \
            "脆弱なプロトコル TLSv1.0 が ssl_protocols に含まれています"

    def test_tlsv11_not_present(self, nginx_conf_content: str) -> None:
        """TLSv1.1 が無効であること (古い脆弱なプロトコル)"""
        assert "TLSv1.1" not in nginx_conf_content, \
            "脆弱なプロトコル TLSv1.1 が ssl_protocols に含まれています"


class TestNginxHstsHeader:
    """nginx 設定に HSTS ヘッダーが含まれること"""

    @pytest.fixture(scope="class")
    def nginx_conf_content(self) -> str:
        """adminui.conf の内容を返す"""
        conf = PROJECT_ROOT / "config" / "nginx" / "adminui.conf"
        return conf.read_text(encoding="utf-8")

    def test_hsts_header_present(self, nginx_conf_content: str) -> None:
        """Strict-Transport-Security ヘッダーが含まれること"""
        assert "Strict-Transport-Security" in nginx_conf_content, \
            "nginx 設定に HSTS (Strict-Transport-Security) ヘッダーがありません"

    def test_hsts_max_age(self, nginx_conf_content: str) -> None:
        """HSTS の max-age が設定されていること"""
        assert "max-age=" in nginx_conf_content, \
            "HSTS の max-age が設定されていません"

    def test_hsts_include_subdomains(self, nginx_conf_content: str) -> None:
        """HSTS に includeSubDomains が含まれること"""
        assert "includeSubDomains" in nginx_conf_content, \
            "HSTS に includeSubDomains が含まれていません"


class TestScriptExecutable:
    """スクリプトが実行可能であること"""

    def test_generate_ssl_cert_executable(self) -> None:
        """scripts/generate-ssl-cert.sh が実行可能であること"""
        script = PROJECT_ROOT / "scripts" / "generate-ssl-cert.sh"
        assert script.exists(), f"スクリプトが見つかりません: {script}"
        mode = os.stat(script).st_mode
        assert mode & stat.S_IXUSR, \
            f"scripts/generate-ssl-cert.sh に実行権限がありません (mode={oct(mode)})"

    def test_setup_https_executable(self) -> None:
        """scripts/setup-https.sh が実行可能であること"""
        script = PROJECT_ROOT / "scripts" / "setup-https.sh"
        assert script.exists(), f"スクリプトが見つかりません: {script}"
        mode = os.stat(script).st_mode
        assert mode & stat.S_IXUSR, \
            f"scripts/setup-https.sh に実行権限がありません (mode={oct(mode)})"


class TestProdJsonSslConfig:
    """prod.json の SSL 設定"""

    @pytest.fixture(scope="class")
    def prod_config(self) -> dict:
        """prod.json の内容を返す"""
        conf = PROJECT_ROOT / "config" / "prod.json"
        return json.loads(conf.read_text(encoding="utf-8"))

    def test_prod_json_exists(self) -> None:
        """config/prod.json が存在すること"""
        conf = PROJECT_ROOT / "config" / "prod.json"
        assert conf.exists(), f"prod.json が見つかりません: {conf}"

    def test_require_https_is_true(self, prod_config: dict) -> None:
        """prod.json の require_https が true であること"""
        require_https = prod_config.get("security", {}).get("require_https")
        assert require_https is True, \
            f"prod.json の security.require_https が true ではありません (値: {require_https})"
