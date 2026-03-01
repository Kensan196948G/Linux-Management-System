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
