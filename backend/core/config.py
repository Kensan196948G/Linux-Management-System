"""
設定管理モジュール

環境変数と設定ファイル（dev.json / prod.json）を統合して読み込む。
実行環境のIPアドレスを自動検出し、CORS・api_base_url に反映する。
"""

import json
import os
import socket
from pathlib import Path
from typing import List, Literal

from pydantic import Field
from pydantic_settings import BaseSettings


def _detect_primary_ip() -> str:
    """デフォルトルートで使用されるNICのIPアドレスを自動検出する。

    Returns:
        検出されたIPアドレス文字列。検出失敗時は "127.0.0.1"。
    """
    # .env.runtime から取得（Systemd ExecStartPre が書き出す）
    project_root = Path(__file__).parent.parent.parent
    runtime_env = project_root / ".env.runtime"
    if runtime_env.exists():
        for line in runtime_env.read_text(encoding="utf-8").splitlines():
            if line.startswith("DETECTED_IP="):
                ip = line.split("=", 1)[1].strip()
                if ip:
                    return ip

    # 環境変数から取得
    env_ip = os.getenv("DETECTED_IP", "")
    if env_ip:
        return env_ip

    # UDP trick: パケット送信なしでソースIPを特定
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        pass

    return "127.0.0.1"


class ServerConfig(BaseSettings):
    """サーバー設定"""

    host: str = "0.0.0.0"  # nosec B104
    http_port: int = 3000
    https_port: int = 3443
    ssl_enabled: bool = True
    ssl_cert: str = "./certs/dev/cert.pem"
    ssl_key: str = "./certs/dev/key.pem"


class DatabaseConfig(BaseSettings):
    """データベース設定"""

    path: str = "./data/dev/database.db"
    backup_enabled: bool = True
    backup_interval: int = 3600


class LoggingConfig(BaseSettings):
    """ログ設定"""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    file: str = "./logs/dev/app.log"
    max_size: str = "10MB"
    backup_count: int = 5


class SecurityConfig(BaseSettings):
    """セキュリティ設定"""

    allowed_services: List[str] = Field(
        default_factory=lambda: ["nginx", "postgresql", "redis"]
    )
    session_timeout: int = 3600
    max_login_attempts: int = 5
    require_https: bool = False


class FeaturesConfig(BaseSettings):
    """機能設定"""

    demo_data_enabled: bool = True
    debug_mode: bool = True
    hot_reload: bool = True
    api_docs_enabled: bool = True


class FrontendConfig(BaseSettings):
    """フロントエンド設定"""

    title: str = "【開発】Linux Management System"
    show_env_badge: bool = True
    api_base_url: str = "http://localhost:3000/api"


def _build_cors_origins(env: str, primary_ip: str, http_port: int, https_port: int) -> List[str]:
    """環境・IPアドレス・ポートから CORS 許可オリジンリストを動的生成する。

    Args:
        env: 環境名 ("development" / "production")
        primary_ip: 検出済みIPアドレス
        http_port: HTTPポート番号
        https_port: HTTPSポート番号

    Returns:
        CORS 許可オリジン一覧
    """
    origins = [
        f"http://localhost:{http_port}",
        f"https://localhost:{https_port}",
        f"http://127.0.0.1:{http_port}",
        f"https://127.0.0.1:{https_port}",
        f"http://{primary_ip}:{http_port}",
        f"https://{primary_ip}:{https_port}",
    ]
    if env == "development":
        origins.append("*")  # 開発環境では全オリジン許可
    return origins


class Settings(BaseSettings):
    """全体設定"""

    # 環境（dev / prod）
    environment: Literal["development", "production"] = "development"

    # 各種設定
    server: ServerConfig = Field(default_factory=ServerConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    features: FeaturesConfig = Field(default_factory=FeaturesConfig)
    frontend: FrontendConfig = Field(default_factory=FrontendConfig)

    # JWT 設定
    jwt_secret_key: str = "change-this-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60

    # CORS 設定（動的生成 - load_config() で上書き）
    # ENVIRONMENT=production のときデフォルトは空（prod.json で明示設定が必要）
    cors_origins: List[str] = Field(
        default_factory=lambda: (
            [
                "http://localhost:5012",
                "https://localhost:5443",
                "http://localhost:8000",
                "https://localhost:8443",
                "http://127.0.0.1:5012",
                "*",
            ]
            if os.getenv("ENVIRONMENT", "development") != "production"
            else []
        )
    )

    # 検出済みIPアドレス（情報参照用）
    detected_ip: str = "127.0.0.1"

    model_config = {
        "extra": "ignore",  # JSON から余分なフィールドを無視
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


def load_config(env: Literal["dev", "prod"] = "dev") -> Settings:
    """
    環境設定を読み込む。IPアドレスを自動検出して CORS・api_base_url に反映する。

    Args:
        env: 環境（dev / prod）

    Returns:
        Settings オブジェクト
    """
    project_root = Path(__file__).parent.parent.parent
    config_file = project_root / "config" / f"{env}.json"

    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_file}")

    # JSON 設定ファイルを読み込み
    with open(config_file, "r", encoding="utf-8") as f:
        config_data = json.load(f)

    # .env / .env.runtime を読み込み
    from dotenv import load_dotenv

    load_dotenv(project_root / ".env")
    load_dotenv(project_root / ".env.runtime")  # detect-ip.sh が生成

    # JWT 秘密鍵を環境変数から取得
    jwt_secret = os.getenv("SESSION_SECRET", "change-this-in-production")
    config_data["jwt_secret_key"] = jwt_secret

    # Settings オブジェクトを作成（一時）
    settings = Settings(**config_data)

    # ─── 動的IP対応 ───────────────────────────
    primary_ip = _detect_primary_ip()
    http_port = settings.server.http_port
    https_port = settings.server.https_port
    env_long = settings.environment  # "development" / "production"

    # detected_ip を設定
    settings.detected_ip = primary_ip

    # CORS: prod.json に明示指定がある場合はそちらを優先
    if "cors_origins" not in config_data or not config_data.get("cors_origins"):
        settings.cors_origins = _build_cors_origins(env_long, primary_ip, http_port, https_port)
    else:
        # 既存リストに動的エントリを追加（重複除去）
        dynamic = _build_cors_origins(env_long, primary_ip, http_port, https_port)
        merged = list(dict.fromkeys(settings.cors_origins + dynamic))
        settings.cors_origins = merged

    # api_base_url を動的IPで再設定（固定IPのプレースホルダーを置換）
    if env == "dev":
        settings.frontend.api_base_url = f"http://{primary_ip}:{http_port}/api"
    else:
        settings.frontend.api_base_url = f"https://{primary_ip}:{https_port}/api"
    # ─────────────────────────────────────────

    return settings


# デフォルト設定のインスタンス（遅延初期化）
_settings_cache = None


def get_settings() -> Settings:
    """設定を取得（遅延初期化）"""
    global _settings_cache

    if _settings_cache is None:
        current_env = os.getenv("ENV", "dev")
        _settings_cache = load_config(current_env)

    return _settings_cache


# 後方互換性のため
settings = get_settings()
