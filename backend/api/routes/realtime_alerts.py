"""
リアルタイムアラート配信

CPU/メモリ/ディスク/ロード閾値超過をWebSocket経由でプッシュ配信する。
ユーザー定義アラートルールのCRUDと、発火履歴管理を提供する。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Optional

import psutil
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.websockets import WebSocketState
from jose import JWTError, jwt
from pydantic import BaseModel, field_validator

from ...core.audit_log import audit_log
from ...core.auth import TokenData, require_permission
from ...core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/realtime-alerts", tags=["realtime-alerts"])

# ===================================================================
# 定数・許可リスト
# ===================================================================

ALLOWED_METRICS: frozenset[str] = frozenset({"cpu_percent", "memory_percent", "disk_percent", "load1"})
ALLOWED_OPERATORS: frozenset[str] = frozenset({"gt", "lt", "gte", "lte"})
ALLOWED_SEVERITIES: frozenset[str] = frozenset({"info", "warning", "critical"})

MAX_RULES = 50
MAX_HISTORY = 100

# ===================================================================
# インメモリストレージ
# ===================================================================

_alert_rules: dict[str, dict] = {}
_alert_history: deque[dict] = deque(maxlen=MAX_HISTORY)

# ===================================================================
# デフォルトルール登録
# ===================================================================


def _register_default_rules() -> None:
    """モジュール初期化時にデフォルトアラートルールを登録する。"""
    defaults = [
        {
            "name": "high_cpu_critical",
            "metric": "cpu_percent",
            "threshold": 90.0,
            "operator": "gt",
            "severity": "critical",
        },
        {
            "name": "high_memory_warning",
            "metric": "memory_percent",
            "threshold": 85.0,
            "operator": "gt",
            "severity": "warning",
        },
        {
            "name": "high_disk_warning",
            "metric": "disk_percent",
            "threshold": 80.0,
            "operator": "gt",
            "severity": "warning",
        },
    ]
    for d in defaults:
        rule_id = str(uuid.uuid4())
        _alert_rules[rule_id] = {
            "id": rule_id,
            "name": d["name"],
            "metric": d["metric"],
            "threshold": d["threshold"],
            "operator": d["operator"],
            "severity": d["severity"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }


_register_default_rules()

# ===================================================================
# Pydantic モデル
# ===================================================================


class AlertRuleCreate(BaseModel):
    """アラートルール作成リクエスト"""

    name: str
    metric: str
    threshold: float
    operator: str
    severity: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """ルール名のバリデーション"""
        if not v or not v.strip():
            raise ValueError("name must not be empty")
        if len(v) > 64:
            raise ValueError("name must be 64 characters or less")
        forbidden = {";", "|", "&", "$", "(", ")", "`", ">", "<", "*", "?", "{", "}", "[", "]"}
        for ch in forbidden:
            if ch in v:
                raise ValueError(f"forbidden character in name: {ch}")
        return v.strip()

    @field_validator("metric")
    @classmethod
    def validate_metric(cls, v: str) -> str:
        """メトリクス名のバリデーション（許可リスト）"""
        if v not in ALLOWED_METRICS:
            raise ValueError(f"metric must be one of {sorted(ALLOWED_METRICS)}")
        return v

    @field_validator("threshold")
    @classmethod
    def validate_threshold(cls, v: float) -> float:
        """閾値のバリデーション"""
        if v < 0:
            raise ValueError("threshold must be >= 0")
        if v > 1_000_000:
            raise ValueError("threshold is too large")
        return v

    @field_validator("operator")
    @classmethod
    def validate_operator(cls, v: str) -> str:
        """演算子のバリデーション（許可リスト）"""
        if v not in ALLOWED_OPERATORS:
            raise ValueError(f"operator must be one of {sorted(ALLOWED_OPERATORS)}")
        return v

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str) -> str:
        """重要度のバリデーション（許可リスト）"""
        if v not in ALLOWED_SEVERITIES:
            raise ValueError(f"severity must be one of {sorted(ALLOWED_SEVERITIES)}")
        return v


# ===================================================================
# 内部ヘルパー
# ===================================================================


def _check_rule(rule: dict, metrics: dict[str, float]) -> bool:
    """メトリクス値とルールを照合し、発火するか判定する。"""
    value = metrics.get(rule["metric"])
    if value is None:
        return False
    threshold = rule["threshold"]
    op = rule["operator"]
    if op == "gt":
        return value > threshold
    if op == "lt":
        return value < threshold
    if op == "gte":
        return value >= threshold
    if op == "lte":
        return value <= threshold
    return False


def _collect_metrics() -> dict[str, float]:
    """psutil を使用して現在のシステムメトリクスを収集する。"""
    return {
        "cpu_percent": psutil.cpu_percent(interval=1),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage("/").percent,
        "load1": psutil.getloadavg()[0],
    }


def _validate_ws_token(token: str) -> Optional[dict]:
    """
    WebSocket 接続用 JWT トークン検証。

    Args:
        token: JWT トークン文字列

    Returns:
        検証成功時はペイロード dict、失敗時は None
    """
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        if payload.get("sub") is None:
            return None
        return payload
    except JWTError as exc:
        logger.warning("realtime-alerts WS JWT validation failed: %s", exc)
        return None


def _utcnow_iso() -> str:
    """現在の UTC 時刻を ISO 8601 文字列で返す。"""
    return datetime.now(timezone.utc).isoformat()


# ===================================================================
# HTTP エンドポイント
# ===================================================================


@router.get("/rules")
async def list_rules(
    current_user: TokenData = Depends(require_permission("read:alerts")),
) -> dict:
    """
    登録済みアラートルール一覧を返す。

    Args:
        current_user: 認証済みユーザー (read:alerts 権限必須)

    Returns:
        ルール一覧と件数を含む dict
    """
    audit_log.record(
        operation="realtime_alerts_list_rules",
        user_id=current_user.user_id,
        target="alert_rules",
        status="success",
    )
    return {"rules": list(_alert_rules.values()), "count": len(_alert_rules)}


@router.post("/rules", status_code=status.HTTP_201_CREATED)
async def create_rule(
    body: AlertRuleCreate,
    current_user: TokenData = Depends(require_permission("write:alerts")),
) -> dict:
    """
    アラートルールを作成する。

    Args:
        body: ルール作成リクエスト
        current_user: 認証済みユーザー (write:alerts 権限必須)

    Returns:
        作成したルールの dict

    Raises:
        HTTPException 409: ルール上限 (50件) 超過
    """
    if len(_alert_rules) >= MAX_RULES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Alert rule limit reached (max {MAX_RULES})",
        )

    rule_id = str(uuid.uuid4())
    rule = {
        "id": rule_id,
        "name": body.name,
        "metric": body.metric,
        "threshold": body.threshold,
        "operator": body.operator,
        "severity": body.severity,
        "created_at": _utcnow_iso(),
    }
    _alert_rules[rule_id] = rule

    audit_log.record(
        operation="realtime_alerts_create_rule",
        user_id=current_user.user_id,
        target=f"rule:{rule_id}",
        status="success",
        details={"name": body.name, "metric": body.metric, "threshold": body.threshold},
    )
    return rule


@router.delete("/rules/{rule_id}", status_code=status.HTTP_200_OK)
async def delete_rule(
    rule_id: str,
    current_user: TokenData = Depends(require_permission("write:alerts")),
) -> dict:
    """
    指定 ID のアラートルールを削除する。

    Args:
        rule_id: 削除対象ルールの UUID
        current_user: 認証済みユーザー (write:alerts 権限必須)

    Returns:
        削除結果メッセージ

    Raises:
        HTTPException 404: 該当ルールが存在しない場合
    """
    if rule_id not in _alert_rules:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")

    del _alert_rules[rule_id]

    audit_log.record(
        operation="realtime_alerts_delete_rule",
        user_id=current_user.user_id,
        target=f"rule:{rule_id}",
        status="success",
    )
    return {"status": "deleted", "rule_id": rule_id}


@router.get("/history")
async def get_history(
    current_user: TokenData = Depends(require_permission("read:alerts")),
) -> dict:
    """
    アラート発火履歴を返す（最新 100 件、インメモリ）。

    Args:
        current_user: 認証済みユーザー (read:alerts 権限必須)

    Returns:
        発火履歴一覧と件数を含む dict
    """
    audit_log.record(
        operation="realtime_alerts_get_history",
        user_id=current_user.user_id,
        target="alert_history",
        status="success",
    )
    return {"history": list(_alert_history), "count": len(_alert_history)}


# ===================================================================
# WebSocket エンドポイント
# ===================================================================


@router.websocket("/ws")
async def alerts_websocket(
    websocket: WebSocket,
    token: str = Query(default=""),
) -> None:
    """
    アラート状況をリアルタイム配信する WebSocket エンドポイント。

    クエリパラメータ ?token= に JWT を渡すことで認証する。
    認証失敗時はコード 1008 で切断する。
    5秒間隔でメトリクスと発火アラートを送信する。

    Args:
        websocket: WebSocket 接続
        token: JWT 認証トークン (query parameter)
    """
    payload = _validate_ws_token(token)
    if payload is None:
        await websocket.close(code=1008)
        return

    user_id = payload.get("sub", "unknown")
    username = payload.get("username", "unknown")

    await websocket.accept()
    logger.info("realtime-alerts WS connected: user=%s", username)

    try:
        while True:
            metrics = _collect_metrics()
            triggered = []
            for rule in list(_alert_rules.values()):
                if _check_rule(rule, metrics):
                    fired = {
                        "rule_id": rule["id"],
                        "rule_name": rule["name"],
                        "metric": rule["metric"],
                        "value": metrics[rule["metric"]],
                        "threshold": rule["threshold"],
                        "operator": rule["operator"],
                        "severity": rule["severity"],
                        "fired_at": _utcnow_iso(),
                    }
                    triggered.append(fired)
                    _alert_history.appendleft(fired)

            await websocket.send_json(
                {
                    "type": "metrics",
                    "metrics": metrics,
                    "alerts": triggered,
                    "timestamp": _utcnow_iso(),
                }
            )
            await asyncio.sleep(5)

    except WebSocketDisconnect:
        logger.debug("realtime-alerts WS disconnected: user=%s", username)
    except Exception as exc:
        logger.error("realtime-alerts WS error: user=%s error=%s", username, exc)
    finally:
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close()
            except Exception:
                pass
