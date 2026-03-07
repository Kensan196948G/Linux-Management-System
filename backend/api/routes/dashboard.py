"""ダッシュボード設定管理 API ルーター

ユーザーごとのウィジェット設定（表示順・非表示・テーマ等）を
data/dashboard_configs/{user_id}.json に永続化する。
"""

import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from ...core import require_permission
from ...core.audit_log import audit_log
from ...core.auth import TokenData

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# ===================================================================
# 定数
# ===================================================================

# 許可されたウィジェット ID（allowlist）
ALLOWED_WIDGET_IDS: list[str] = [
    "health-score",
    "cpu-ring",
    "cpu-line",
    "mem-bar",
    "net-line",
    "error-log",
    "nic-stats",
]

# 許可されたテーマ
ALLOWED_THEMES: list[str] = ["default", "dark", "compact"]

# 許可されたリフレッシュ間隔（秒）
ALLOWED_REFRESH_INTERVALS: list[int] = [5, 10, 15, 30, 60, 120]

# 設定保存ディレクトリ
_CONFIGS_DIR = Path(__file__).parent.parent.parent.parent / "data" / "dashboard_configs"

# プリセット定義
PRESETS: dict[str, dict[str, Any]] = {
    "sysadmin": {
        "id": "sysadmin",
        "name": "システム管理者向け",
        "description": "全ウィジェットを表示、10秒更新",
        "config": {
            "widget_order": ["health-score", "cpu-ring", "cpu-line", "mem-bar", "net-line", "error-log", "nic-stats"],
            "hidden_widgets": [],
            "theme": "default",
            "refresh_interval": 10,
            "compact_mode": False,
        },
    },
    "developer": {
        "id": "developer",
        "name": "開発者向け",
        "description": "CPU・ネットワーク中心、コンパクト表示",
        "config": {
            "widget_order": ["cpu-ring", "cpu-line", "net-line", "mem-bar", "health-score", "nic-stats", "error-log"],
            "hidden_widgets": [],
            "theme": "compact",
            "refresh_interval": 5,
            "compact_mode": True,
        },
    },
    "monitoring": {
        "id": "monitoring",
        "name": "監視オペレーター向け",
        "description": "ヘルススコアとアラート重視、30秒更新",
        "config": {
            "widget_order": ["health-score", "error-log", "cpu-ring", "mem-bar", "net-line", "cpu-line", "nic-stats"],
            "hidden_widgets": [],
            "theme": "default",
            "refresh_interval": 30,
            "compact_mode": False,
        },
    },
    "minimal": {
        "id": "minimal",
        "name": "ミニマル",
        "description": "必要最小限のウィジェットのみ",
        "config": {
            "widget_order": ["health-score", "cpu-ring", "mem-bar"],
            "hidden_widgets": ["cpu-line", "net-line", "error-log", "nic-stats"],
            "theme": "compact",
            "refresh_interval": 30,
            "compact_mode": True,
        },
    },
}

# デフォルト設定
DEFAULT_CONFIG: dict[str, Any] = {
    "widget_order": ["health-score", "cpu-ring", "cpu-line", "mem-bar", "net-line", "error-log", "nic-stats"],
    "hidden_widgets": [],
    "theme": "default",
    "refresh_interval": 10,
    "compact_mode": False,
}


# ===================================================================
# Pydantic スキーマ
# ===================================================================


class DashboardConfig(BaseModel):
    """ダッシュボード設定スキーマ"""

    widget_order: list[str] = Field(default_factory=lambda: list(DEFAULT_CONFIG["widget_order"]))
    hidden_widgets: list[str] = Field(default_factory=list)
    theme: str = Field(default="default")
    refresh_interval: int = Field(default=10)
    compact_mode: bool = Field(default=False)

    @field_validator("widget_order")
    @classmethod
    def validate_widget_order(cls, v: list[str]) -> list[str]:
        """widget_order は allowlist 内のIDのみ許可。"""
        for wid in v:
            if wid not in ALLOWED_WIDGET_IDS:
                raise ValueError(f"Unknown widget id: {wid!r}. Allowed: {ALLOWED_WIDGET_IDS}")
        return v

    @field_validator("hidden_widgets")
    @classmethod
    def validate_hidden_widgets(cls, v: list[str]) -> list[str]:
        """hidden_widgets は allowlist 内のIDのみ許可。"""
        for wid in v:
            if wid not in ALLOWED_WIDGET_IDS:
                raise ValueError(f"Unknown widget id: {wid!r}. Allowed: {ALLOWED_WIDGET_IDS}")
        return v

    @field_validator("theme")
    @classmethod
    def validate_theme(cls, v: str) -> str:
        """テーマは allowlist 内の値のみ許可。"""
        if v not in ALLOWED_THEMES:
            raise ValueError(f"Unknown theme: {v!r}. Allowed: {ALLOWED_THEMES}")
        return v

    @field_validator("refresh_interval")
    @classmethod
    def validate_refresh_interval(cls, v: int) -> int:
        """リフレッシュ間隔は許可値リスト内のみ許可。"""
        if v not in ALLOWED_REFRESH_INTERVALS:
            raise ValueError(f"Invalid refresh_interval: {v}. Allowed: {ALLOWED_REFRESH_INTERVALS}")
        return v


# ===================================================================
# ヘルパー
# ===================================================================


def _safe_user_id(user_id: str) -> str:
    """ユーザーIDをファイル名として安全な文字列に変換する。

    Args:
        user_id: 元のユーザーID

    Returns:
        ファイル名として安全な文字列
    """
    # 英数字・ハイフン・アンダースコア・ドット以外を除去
    safe = re.sub(r"[^a-zA-Z0-9._@\-]", "_", user_id)
    return safe[:128]


def _config_path(user_id: str) -> Path:
    """ユーザーの設定ファイルパスを返す。

    Args:
        user_id: ユーザーID

    Returns:
        設定ファイルの Path オブジェクト
    """
    _CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
    filename = _safe_user_id(user_id) + ".json"
    # パストラバーサル対策: 生成パスが configs ディレクトリ配下であることを確認
    resolved = (_CONFIGS_DIR / filename).resolve()
    if not str(resolved).startswith(str(_CONFIGS_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid user id")
    return resolved


def _load_config(user_id: str) -> dict[str, Any]:
    """ユーザー設定を読み込む。存在しない場合はデフォルトを返す。

    Args:
        user_id: ユーザーID

    Returns:
        設定辞書
    """
    path = _config_path(user_id)
    if not path.exists():
        return dict(DEFAULT_CONFIG)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        # 不足キーをデフォルトで補完
        for key, default_val in DEFAULT_CONFIG.items():
            if key not in data:
                data[key] = default_val
        return data
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_CONFIG)


def _save_config(user_id: str, config: dict[str, Any]) -> None:
    """ユーザー設定をファイルに保存する。

    Args:
        user_id: ユーザーID
        config: 保存する設定辞書
    """
    path = _config_path(user_id)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


# ===================================================================
# エンドポイント
# ===================================================================


@router.get("/config")
async def get_dashboard_config(
    current_user: TokenData = Depends(require_permission("read:dashboard")),
) -> dict[str, Any]:
    """ユーザーのダッシュボード設定を取得する。

    Args:
        current_user: 現在のユーザー（read:dashboard 権限必須）

    Returns:
        ダッシュボード設定辞書
    """
    config = _load_config(current_user.user_id)
    audit_log.record(
        operation="dashboard_config_read",
        user_id=current_user.user_id,
        target="dashboard_config",
        status="success",
    )
    return {"status": "ok", "config": config}


@router.put("/config")
async def put_dashboard_config(
    body: DashboardConfig,
    current_user: TokenData = Depends(require_permission("write:dashboard")),
) -> dict[str, Any]:
    """ユーザーのダッシュボード設定を保存する。

    Args:
        body: 保存する設定
        current_user: 現在のユーザー（write:dashboard 権限必須）

    Returns:
        保存後の設定辞書
    """
    config = body.model_dump()
    _save_config(current_user.user_id, config)
    audit_log.record(
        operation="dashboard_config_save",
        user_id=current_user.user_id,
        target="dashboard_config",
        status="success",
    )
    return {"status": "ok", "config": config}


@router.delete("/config")
async def delete_dashboard_config(
    current_user: TokenData = Depends(require_permission("write:dashboard")),
) -> dict[str, Any]:
    """ユーザーのダッシュボード設定をリセット（デフォルト復元）する。

    Args:
        current_user: 現在のユーザー（write:dashboard 権限必須）

    Returns:
        デフォルト設定辞書
    """
    path = _config_path(current_user.user_id)
    if path.exists():
        path.unlink()
    audit_log.record(
        operation="dashboard_config_reset",
        user_id=current_user.user_id,
        target="dashboard_config",
        status="success",
    )
    return {"status": "ok", "config": dict(DEFAULT_CONFIG)}


@router.get("/presets")
async def get_dashboard_presets(
    current_user: TokenData = Depends(require_permission("read:dashboard")),
) -> dict[str, Any]:
    """利用可能なダッシュボードプリセット一覧を返す。

    Args:
        current_user: 現在のユーザー（read:dashboard 権限必須）

    Returns:
        プリセット一覧
    """
    return {
        "status": "ok",
        "presets": [
            {
                "id": p["id"],
                "name": p["name"],
                "description": p["description"],
            }
            for p in PRESETS.values()
        ],
    }


@router.post("/presets/{preset_id}/apply")
async def apply_dashboard_preset(
    preset_id: str,
    current_user: TokenData = Depends(require_permission("write:dashboard")),
) -> dict[str, Any]:
    """指定プリセットをユーザーの設定として適用する。

    Args:
        preset_id: 適用するプリセットID
        current_user: 現在のユーザー（write:dashboard 権限必須）

    Returns:
        適用後の設定辞書

    Raises:
        HTTPException: プリセットが存在しない場合
    """
    if preset_id not in PRESETS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Preset not found: {preset_id!r}",
        )
    config = dict(PRESETS[preset_id]["config"])
    _save_config(current_user.user_id, config)
    audit_log.record(
        operation="dashboard_preset_apply",
        user_id=current_user.user_id,
        target=f"preset:{preset_id}",
        status="success",
    )
    return {"status": "ok", "config": config, "preset_id": preset_id}
