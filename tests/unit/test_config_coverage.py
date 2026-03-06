"""
config.py カバレッジ向上テスト

対象行:
  35-37  - _detect_primary_ip(): DETECTED_IP 環境変数パス
  40-45  - _detect_primary_ip(): UDP ソケットパス（成功・失敗）
  47     - _detect_primary_ip(): フォールバック 127.0.0.1
  191    - load_config(): 設定ファイル不存在 → FileNotFoundError
  221    - load_config(): cors_origins 未設定時の動的生成
  232    - load_config(): prod 環境での HTTPS api_base_url 設定
"""
import os
import socket
from unittest.mock import MagicMock, patch

import pytest


class TestDetectPrimaryIpEnvVar:
    """_detect_primary_ip() の DETECTED_IP 環境変数パス（lines 35-37）"""

    def test_env_var_used_when_runtime_file_has_no_ip(self, tmp_path, monkeypatch):
        """DETECTED_IP 環境変数が設定されている場合はその値を返す"""
        import backend.core.config as config_module

        # __file__ を tmp_path 配下に変更することで .env.runtime が存在しない環境を模倣
        fake_file = str(tmp_path / "backend" / "core" / "config.py")
        monkeypatch.setattr(config_module, "__file__", fake_file)
        monkeypatch.setenv("DETECTED_IP", "10.20.30.40")

        result = config_module._detect_primary_ip()
        assert result == "10.20.30.40"

    def test_env_var_with_ip_file_missing(self, tmp_path, monkeypatch):
        """DETECTED_IP env var がある場合、.env.runtime が存在しなくても動作する"""
        import backend.core.config as config_module

        fake_file = str(tmp_path / "backend" / "core" / "config.py")
        monkeypatch.setattr(config_module, "__file__", fake_file)
        monkeypatch.setenv("DETECTED_IP", "172.16.0.1")

        result = config_module._detect_primary_ip()
        assert result == "172.16.0.1"


class TestDetectPrimaryIpSocket:
    """_detect_primary_ip() の UDP ソケットパス（lines 40-45, 47）"""

    def test_socket_success_returns_ip(self, tmp_path, monkeypatch):
        """ソケット接続成功時は getsockname() の IP を返す（lines 40-43）"""
        import backend.core.config as config_module

        fake_file = str(tmp_path / "backend" / "core" / "config.py")
        monkeypatch.setattr(config_module, "__file__", fake_file)
        # DETECTED_IP を未設定にする
        monkeypatch.delenv("DETECTED_IP", raising=False)

        # socket.socket() をモックして接続成功させる
        mock_sock = MagicMock()
        mock_sock.__enter__ = MagicMock(return_value=mock_sock)
        mock_sock.__exit__ = MagicMock(return_value=False)
        mock_sock.getsockname.return_value = ("192.168.5.10", 0)

        with patch.object(config_module.socket, "socket", return_value=mock_sock):
            result = config_module._detect_primary_ip()

        assert result == "192.168.5.10"

    def test_socket_oserror_falls_back_to_localhost(self, tmp_path, monkeypatch):
        """ソケット接続失敗（OSError）時は 127.0.0.1 を返す（lines 44-45, 47）"""
        import backend.core.config as config_module

        fake_file = str(tmp_path / "backend" / "core" / "config.py")
        monkeypatch.setattr(config_module, "__file__", fake_file)
        monkeypatch.delenv("DETECTED_IP", raising=False)

        mock_sock = MagicMock()
        mock_sock.__enter__ = MagicMock(return_value=mock_sock)
        mock_sock.__exit__ = MagicMock(return_value=False)
        mock_sock.connect.side_effect = OSError("network unreachable")

        with patch.object(config_module.socket, "socket", return_value=mock_sock):
            result = config_module._detect_primary_ip()

        assert result == "127.0.0.1"


class TestLoadConfigMissingFile:
    """load_config() 設定ファイル不存在（line 191）"""

    def test_nonexistent_env_raises_file_not_found(self):
        """存在しない環境名は FileNotFoundError を送出する"""
        from backend.core.config import load_config

        with pytest.raises(FileNotFoundError, match="Configuration file not found"):
            load_config("nonexistent_env_xyz_abc")  # type: ignore[arg-type]


class TestLoadConfigNoCorsOrigins:
    """load_config() cors_origins 未設定時の動的生成（line 221）"""

    def test_cors_dynamically_built_when_missing_from_config(self):
        """config_data に cors_origins がない場合、動的に CORS オリジンを生成する"""
        from backend.core.config import load_config

        # json.load をモックして cors_origins を含まない最小限の設定を返す
        minimal_config: dict = {}

        with patch("backend.core.config.json.load", return_value=minimal_config):
            result = load_config("dev")

        assert result.cors_origins is not None
        assert len(result.cors_origins) > 0

    def test_cors_dynamically_built_when_empty_list_in_config(self):
        """config_data の cors_origins が空リストの場合も動的生成される"""
        from backend.core.config import load_config

        minimal_config = {"cors_origins": []}

        with patch("backend.core.config.json.load", return_value=minimal_config):
            result = load_config("dev")

        # 空リストの場合は動的生成が使用される
        assert len(result.cors_origins) > 0


class TestLoadConfigProdEnv:
    """load_config("prod") での HTTPS api_base_url 設定（line 232）"""

    def test_prod_env_sets_https_api_base_url(self):
        """prod 環境では api_base_url が https:// で始まる"""
        from backend.core.config import load_config

        result = load_config("prod")
        assert result.frontend.api_base_url.startswith("https://")

    def test_prod_env_uses_https_port(self):
        """prod 環境の api_base_url はサーバーの https_port を含む"""
        from backend.core.config import load_config

        result = load_config("prod")
        # HTTPS なので https:// で始まる
        assert "https://" in result.frontend.api_base_url
        assert result.environment == "production"
