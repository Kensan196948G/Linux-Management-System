"""
WebSocket リアルタイム監視モジュール

システム情報・プロセス・アラートのリアルタイム配信を WebSocket で提供する。
JWT トークンによる認証を必須とし、不正接続は 4001 で切断する。
セキュリティ: トークンは最初のメッセージで受信する（URLクエリパラメータは使用しない）。
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import psutil
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState
from jose import JWTError, jwt

from backend.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])

# WebSocket 認証タイムアウト（秒）
WS_AUTH_TIMEOUT = 10.0

# ===================================================================
# 接続マネージャー
# ===================================================================


class ConnectionManager:
    """WebSocket 接続を topic 別に管理するクラス"""

    def __init__(self) -> None:
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, topic: str) -> None:
        """
        WebSocket を topic の接続リストに追加する。
        接続の accept() は呼び出し元で事前に行うこと。

        Args:
            websocket: 接続済みの WebSocket
            topic: 購読する topic 名
        """
        self.active_connections.setdefault(topic, []).append(websocket)
        logger.debug("WS connected: topic=%s total=%d", topic, len(self.active_connections[topic]))

    async def disconnect(self, websocket: WebSocket, topic: str) -> None:
        """
        WebSocket を topic の接続リストから除去する。

        Args:
            websocket: 切断する WebSocket
            topic: 購読していた topic 名
        """
        connections = self.active_connections.get(topic, [])
        if websocket in connections:
            connections.remove(websocket)
        logger.debug("WS disconnected: topic=%s remaining=%d", topic, len(connections))

    async def broadcast(self, topic: str, message: dict) -> None:
        """
        topic に接続している全クライアントにメッセージを送信する。
        送信失敗したクライアントは接続リストから除去する。

        Args:
            topic: 送信先 topic
            message: 送信するメッセージ（dict）
        """
        dead: list[WebSocket] = []
        for ws in list(self.active_connections.get(topic, [])):
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws, topic)

    async def send_personal(self, websocket: WebSocket, message: dict) -> None:
        """
        特定の WebSocket クライアントにメッセージを送信する。

        Args:
            websocket: 送信先 WebSocket
            message: 送信するメッセージ（dict）
        """
        await websocket.send_json(message)


manager = ConnectionManager()

# ===================================================================
# 認証ヘルパー
# ===================================================================


def _validate_token(token: str) -> Optional[dict]:
    """
    JWT トークンを検証し、ペイロードを返す。

    Args:
        token: JWT トークン文字列

    Returns:
        検証成功時はペイロード dict、失敗時は None
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        if payload.get("sub") is None:
            return None
        return payload
    except JWTError as exc:
        logger.warning("WS JWT validation failed: %s", exc)
        return None


async def _ws_authenticate(websocket: WebSocket) -> Optional[dict]:
    """WebSocket 接続を認証する。

    接続後、最初のメッセージから JWT トークンを受信して検証する。
    {"type": "auth", "token": "<JWT>"} 形式のメッセージを期待する。
    タイムアウト（WS_AUTH_TIMEOUT 秒）内に認証メッセージが来ない場合は None を返す。

    Args:
        websocket: 接続済みの WebSocket

    Returns:
        認証成功時はJWTペイロード dict、失敗時は None
    """
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=WS_AUTH_TIMEOUT)
        msg = json.loads(raw)
        if msg.get("type") != "auth":
            logger.warning("WS auth: expected type='auth', got type='%s'", msg.get("type"))
            return None
        token = msg.get("token", "")
        return _validate_token(token)
    except asyncio.TimeoutError:
        logger.warning("WS auth: timeout waiting for auth message")
        return None
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning("WS auth: invalid auth message: %s", exc)
        return None
    except WebSocketDisconnect:
        return None


# ===================================================================
# データ収集ヘルパー
# ===================================================================


def _collect_system_data() -> dict:
    """psutil でシステム情報を収集し dict を返す。"""
    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    load = list(psutil.getloadavg())
    uptime = int(time.time() - psutil.boot_time())

    return {
        "cpu_percent": cpu,
        "memory_percent": mem.percent,
        "memory_used_gb": round(mem.used / (1024**3), 2),
        "memory_total_gb": round(mem.total / (1024**3), 2),
        "disk_percent": disk.percent,
        "disk_used_gb": round(disk.used / (1024**3), 2),
        "disk_total_gb": round(disk.total / (1024**3), 2),
        "load_avg": load,
        "uptime_seconds": uptime,
    }


def _collect_processes_data() -> dict:
    """psutil で CPU 使用率上位 10 プロセスを収集し dict を返す。"""
    procs = []
    total = 0
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
        try:
            info = proc.info
            procs.append(
                {
                    "pid": info["pid"],
                    "name": info["name"] or "",
                    "cpu_percent": round(info["cpu_percent"] or 0.0, 2),
                    "memory_percent": round(info["memory_percent"] or 0.0, 2),
                    "status": info["status"] or "unknown",
                }
            )
            total += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    top10 = sorted(procs, key=lambda p: p["cpu_percent"], reverse=True)[:10]
    return {"processes": top10, "total_count": total}


def _collect_alerts_data() -> dict:
    """システムリソースのしきい値チェックに基づくアラートを生成し dict を返す。"""
    alerts = []
    try:
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        if cpu > 90:
            alerts.append({"level": "critical", "resource": "cpu", "value": cpu, "message": f"CPU使用率が危険水準: {cpu:.1f}%"})
        elif cpu > 75:
            alerts.append({"level": "warning", "resource": "cpu", "value": cpu, "message": f"CPU使用率が高い: {cpu:.1f}%"})

        if mem.percent > 90:
            alerts.append(
                {
                    "level": "critical",
                    "resource": "memory",
                    "value": mem.percent,
                    "message": f"メモリ使用率が危険水準: {mem.percent:.1f}%",
                }
            )
        elif mem.percent > 80:
            alerts.append(
                {
                    "level": "warning",
                    "resource": "memory",
                    "value": mem.percent,
                    "message": f"メモリ使用率が高い: {mem.percent:.1f}%",
                }
            )

        if disk.percent > 90:
            alerts.append(
                {
                    "level": "critical",
                    "resource": "disk",
                    "value": disk.percent,
                    "message": f"ディスク使用率が危険水準: {disk.percent:.1f}%",
                }
            )
        elif disk.percent > 80:
            alerts.append(
                {
                    "level": "warning",
                    "resource": "disk",
                    "value": disk.percent,
                    "message": f"ディスク使用率が高い: {disk.percent:.1f}%",
                }
            )
    except Exception as exc:
        logger.error("Alert collection error: %s", exc)

    return {"alerts": alerts, "count": len(alerts)}


def _utcnow_iso() -> str:
    """現在の UTC 時刻を ISO 8601 文字列で返す。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ===================================================================
# WebSocket エンドポイント
# ===================================================================


@router.websocket("/ws/system")
async def ws_system(
    websocket: WebSocket,
    interval: int = 5,
) -> None:
    """
    システム情報 (CPU/メモリ/ディスク/ロード) をリアルタイム配信する WebSocket エンドポイント。

    認証: 接続後、最初のメッセージで {"type": "auth", "token": "<JWT>"} を送信すること。

    Args:
        websocket: WebSocket 接続
        interval: 送信間隔秒数 (デフォルト 5)
    """
    await websocket.accept()
    user = await _ws_authenticate(websocket)
    if not user:
        await websocket.close(code=4001)
        return

    # interval をクライアントから送信された設定で上書き可能（2〜60秒）
    interval = max(2, min(60, interval))

    await manager.connect(websocket, "system")
    try:
        # 初回データを即時送信
        await manager.send_personal(
            websocket,
            {"type": "system_update", "data": _collect_system_data(), "timestamp": _utcnow_iso()},
        )

        while True:
            await asyncio.sleep(interval)
            if websocket.client_state != WebSocketState.CONNECTED:
                break
            await manager.send_personal(
                websocket,
                {"type": "system_update", "data": _collect_system_data(), "timestamp": _utcnow_iso()},
            )
    except WebSocketDisconnect:
        logger.debug("WS system: client disconnected")
    except Exception as exc:
        logger.error("WS system error: %s", exc)
    finally:
        await manager.disconnect(websocket, "system")


@router.websocket("/ws/processes")
async def ws_processes(
    websocket: WebSocket,
    interval: int = 5,
) -> None:
    """
    CPU 使用率上位 10 プロセスをリアルタイム配信する WebSocket エンドポイント。

    認証: 接続後、最初のメッセージで {"type": "auth", "token": "<JWT>"} を送信すること。

    Args:
        websocket: WebSocket 接続
        interval: 送信間隔秒数 (デフォルト 5)
    """
    await websocket.accept()
    user = await _ws_authenticate(websocket)
    if not user:
        await websocket.close(code=4001)
        return

    interval = max(2, min(60, interval))

    await manager.connect(websocket, "processes")
    try:
        await manager.send_personal(
            websocket,
            {"type": "processes_update", "data": _collect_processes_data(), "timestamp": _utcnow_iso()},
        )

        while True:
            await asyncio.sleep(interval)
            if websocket.client_state != WebSocketState.CONNECTED:
                break
            await manager.send_personal(
                websocket,
                {"type": "processes_update", "data": _collect_processes_data(), "timestamp": _utcnow_iso()},
            )
    except WebSocketDisconnect:
        logger.debug("WS processes: client disconnected")
    except Exception as exc:
        logger.error("WS processes error: %s", exc)
    finally:
        await manager.disconnect(websocket, "processes")


@router.websocket("/ws/alerts")
async def ws_alerts(
    websocket: WebSocket,
    interval: int = 5,
) -> None:
    """
    システムリソースアラートをリアルタイム配信する WebSocket エンドポイント。

    認証: 接続後、最初のメッセージで {"type": "auth", "token": "<JWT>"} を送信すること。

    Args:
        websocket: WebSocket 接続
        interval: 送信間隔秒数 (デフォルト 5)
    """
    await websocket.accept()
    user = await _ws_authenticate(websocket)
    if not user:
        await websocket.close(code=4001)
        return

    interval = max(2, min(60, interval))

    await manager.connect(websocket, "alerts")
    try:
        await manager.send_personal(
            websocket,
            {"type": "alerts_update", "data": _collect_alerts_data(), "timestamp": _utcnow_iso()},
        )

        while True:
            await asyncio.sleep(interval)
            if websocket.client_state != WebSocketState.CONNECTED:
                break
            await manager.send_personal(
                websocket,
                {"type": "alerts_update", "data": _collect_alerts_data(), "timestamp": _utcnow_iso()},
            )
    except WebSocketDisconnect:
        logger.debug("WS alerts: client disconnected")
    except Exception as exc:
        logger.error("WS alerts error: %s", exc)
    finally:
        await manager.disconnect(websocket, "alerts")
