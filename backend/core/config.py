"""
設定管理モジュール

環境変数と設定ファイル（dev.json / prod.json）を統合して読み込む
"""

import json
import os
from pathlib import Path
from typing import List, Literal

from pydantic import Field
from pydantic_settings import BaseSettings


class ServerConfig(BaseSettings):
    """サーバー設定"""

    host: str = "0.0.0.0"
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

    allowed_services: List[str] = Field(default_factory=lambda: ["nginx", "postgresql", "redis"])
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

    # CORS 設定
    cors_origins: List[str] = Field(
        default_factory=lambda: (
            [
                "http://localhost:5012",
                "https://localhost:5443",
                "http://localhost:8000",
                "https://localhost:8443",
                "http://127.0.0.1:5012",
                "http://192.168.0.185:5012",  # LAN アクセス
                "*",  # 開発環境では全オリジンを許可
            ]
            if os.getenv("ENVIRONMENT", "development") == "development"
            else []  # Production: Must be explicitly specified in prod.json
        )
    )

    model_config = {
        "extra": "ignore",  # JSON から余分なフィールドを無視
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


def load_config(env: Literal["dev", "prod"] = "dev") -> Settings:
    """
    環境設定を読み込む

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

    # 環境変数を上書き
    # .env ファイルから読み込み
    from dotenv import load_dotenv

    load_dotenv(project_root / ".env")

    # JWT 秘密鍵を環境変数から取得
    jwt_secret = os.getenv("SESSION_SECRET", "change-this-in-production")
    config_data["jwt_secret_key"] = jwt_secret

    # Settings オブジェクトを作成
    settings = Settings(**config_data)

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
