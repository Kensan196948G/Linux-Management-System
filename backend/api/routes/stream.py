"""
SSE (Server-Sent Events) ストリーミング API

ダッシュボードへのリアルタイムシステム情報配信
EventSource API は Authorization ヘッダー非対応のため、
クエリパラメータでトークンを受け取る。
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import AsyncGenerator

import psutil
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from ...core.auth import decode_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stream", tags=["stream"])


async def _get_cpu_percent() -> float:
    """CPU使用率を非同期で取得（ブロッキング回避）"""
    return await asyncio.to_thread(psutil.cpu_percent, 1)


async def system_event_generator(token: str) -> AsyncGenerator[str, None]:
    """5秒間隔でシステム情報をSSEイベントとして送信

    Args:
        token: 検証済みJWTトークン（接続前に検証済み）

    Yields:
        SSE形式の文字列 "data: {json}\n\n"
    """
    try:
        while True:
            cpu_percent = await _get_cpu_percent()
            mem = psutil.virtual_memory()

            data = {
                "cpu_percent": cpu_percent,
                "mem_percent": mem.percent,
                "mem_used": _format_bytes(mem.used),
                "mem_total": _format_bytes(mem.total),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            yield f"data: {json.dumps(data)}\n\n"

            # cpu_percent(interval=1) で1秒経過済み + 4秒 = 5秒間隔
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        logger.info("SSE stream cancelled (client disconnected)")


def _format_bytes(b: int) -> str:
    """バイト数を人間可読な形式に変換"""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(b) < 1024.0:
            return f"{b:.1f} {unit}"
        b /= 1024.0
    return f"{b:.1f} PB"


def _read_cpu_times() -> dict:
    """``/proc/stat`` から CPU タイム (user, nice, system, idle, ...) を読み込む"""
    with open("/proc/stat") as f:
        line = f.readline()
    fields = line.split()
    # fields[0] == "cpu"
    values = list(map(int, fields[1:]))
    keys = ["user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal"]
    return dict(zip(keys, values + [0] * max(0, len(keys) - len(values))))


def _calc_cpu_percent(prev: dict, curr: dict) -> float:
    """2回のスナップショット差分から CPU 使用率を計算"""
    prev_idle = prev.get("idle", 0) + prev.get("iowait", 0)
    curr_idle = curr.get("idle", 0) + curr.get("iowait", 0)
    prev_total = sum(prev.values())
    curr_total = sum(curr.values())
    total_diff = curr_total - prev_total
    idle_diff = curr_idle - prev_idle
    if total_diff == 0:
        return 0.0
    return round((1.0 - idle_diff / total_diff) * 100, 1)


def _read_mem_percent() -> float:
    """``/proc/meminfo`` からメモリ使用率 (%) を返す"""
    info: dict = {}
    with open("/proc/meminfo") as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 2:
                info[parts[0].rstrip(":")] = int(parts[1])
    total = info.get("MemTotal", 0)
    available = info.get("MemAvailable", 0)
    if total == 0:
        return 0.0
    return round((total - available) / total * 100, 1)


def _read_net_bytes() -> tuple[int, int]:
    """``/proc/net/dev`` から全インターフェース合計の受信・送信バイト数を返す"""
    rx_total = 0
    tx_total = 0
    with open("/proc/net/dev") as f:
        lines = f.readlines()[2:]  # 先頭2行はヘッダ
    for line in lines:
        parts = line.split()
        if len(parts) < 10:
            continue
        iface = parts[0].rstrip(":")
        if iface == "lo":
            continue
        rx_total += int(parts[1])
        tx_total += int(parts[9])
    return rx_total, tx_total


async def dashboard_event_generator(token: str) -> AsyncGenerator[str, None]:
    """1秒間隔で CPU/MEM/NET メトリクスを SSE として送信

    Args:
        token: 検証済み JWT トークン

    Yields:
        SSE 形式の文字列 ``data: {json}\\n\\n``
    """
    try:
        prev_cpu = _read_cpu_times()
        prev_rx, prev_tx = _read_net_bytes()
        await asyncio.sleep(1)

        while True:
            curr_cpu = _read_cpu_times()
            cpu_percent = _calc_cpu_percent(prev_cpu, curr_cpu)
            prev_cpu = curr_cpu

            mem_percent = _read_mem_percent()

            curr_rx, curr_tx = _read_net_bytes()
            net_in = max(0, curr_rx - prev_rx)
            net_out = max(0, curr_tx - prev_tx)
            prev_rx, prev_tx = curr_rx, curr_tx

            metrics = {
                "cpu": cpu_percent,
                "mem": mem_percent,
                "net_in": net_in,
                "net_out": net_out,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            yield f"data: {json.dumps(metrics)}\n\n"
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        logger.info("SSE dashboard stream cancelled (client disconnected)")
    except OSError as exc:
        logger.error(f"SSE dashboard stream /proc read error: {exc}")


@router.get("/dashboard")
async def stream_dashboard(token: str = Query(..., description="JWT認証トークン")):
    """統合ダッシュボード用 SSE ストリーム

    CPU 使用率・メモリ使用率・ネットワーク転送量を 1 秒ごとに送信。
    ``/proc/stat``, ``/proc/meminfo``, ``/proc/net/dev`` を直接読み取るため
    sudo 不要。

    Args:
        token: JWT トークン（クエリパラメータ）

    Returns:
        StreamingResponse (text/event-stream)
        各イベント: ``{"cpu": 12.5, "mem": 45.2, "net_in": 1024, "net_out": 512}``
    """
    try:
        user_data = decode_token(token)
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    logger.info(f"SSE dashboard stream started for user: {user_data.username}")

    return StreamingResponse(
        dashboard_event_generator(token),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/system")
async def stream_system(token: str = Query(..., description="JWT認証トークン")):
    """システム情報のSSEストリーム

    EventSource APIはAuthorizationヘッダーを設定できないため、
    クエリパラメータでJWTトークンを受け取る。

    Args:
        token: JWTトークン（クエリパラメータ）

    Returns:
        StreamingResponse (text/event-stream)
    """
    # トークンを検証（無効ならHTTPExceptionが発生）
    try:
        user_data = decode_token(token)
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    logger.info(f"SSE stream started for user: {user_data.username}")

    return StreamingResponse(
        system_event_generator(token),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
