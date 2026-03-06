"""
プロセス管理 API エンドポイント
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ...core import require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import ROLES, TokenData, decode_token
from ...core.sudo_wrapper import SudoWrapperError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/processes", tags=["processes"])


# ===================================================================
# レスポンスモデル
# ===================================================================


class ProcessInfo(BaseModel):
    """プロセス情報"""

    pid: int
    user: str
    cpu_percent: float
    mem_percent: float
    vsz: int
    rss: int
    tty: str
    stat: str
    start: str
    time: str
    command: str


class ProcessListResponse(BaseModel):
    """プロセス一覧レスポンス"""

    status: str
    total_processes: int
    returned_processes: int
    sort_by: str
    filters: dict
    processes: list[ProcessInfo]
    timestamp: str


# ===================================================================
# エンドポイント
# ===================================================================


@router.get("", response_model=ProcessListResponse)
async def list_processes(
    sort_by: str = Query("cpu", pattern="^(cpu|mem|pid|time)$"),
    limit: int = Query(100, ge=1, le=1000),
    filter_user: Optional[str] = Query(None, min_length=1, max_length=32, pattern="^[a-zA-Z0-9_-]+$"),
    min_cpu: float = Query(0.0, ge=0.0, le=100.0),
    min_mem: float = Query(0.0, ge=0.0, le=100.0),
    current_user: TokenData = Depends(require_permission("read:processes")),
):
    """
    プロセス一覧を取得

    Args:
        sort_by: ソートキー (cpu/mem/pid/time)
        limit: 取得件数 (1-1000)
        filter_user: ユーザー名フィルタ
        min_cpu: 最小CPU使用率 (0.0-100.0)
        min_mem: 最小メモリ使用率 (0.0-100.0)
        current_user: 現在のユーザー (read:processes 権限必須)

    Returns:
        プロセス一覧

    Raises:
        HTTPException: 取得失敗時
    """
    logger.info(
        f"Process list requested: sort={sort_by}, limit={limit}, "
        f"user={filter_user}, min_cpu={min_cpu}, min_mem={min_mem}, "
        f"by={current_user.username}"
    )

    # 監査ログ記録（試行）
    audit_log.record(
        operation="process_list",
        user_id=current_user.user_id,
        target="system",
        status="attempt",
        details={
            "sort_by": sort_by,
            "limit": limit,
            "filter_user": filter_user,
            "min_cpu": min_cpu,
            "min_mem": min_mem,
        },
    )

    try:
        # sudo ラッパー経由でプロセス一覧を取得
        result = sudo_wrapper.get_processes(
            sort_by=sort_by,
            limit=limit,
            filter_user=filter_user,
            min_cpu=min_cpu,
            min_mem=min_mem,
        )

        # ラッパーがエラーを返した場合
        if result.get("status") == "error":
            # 監査ログ記録（拒否）
            audit_log.record(
                operation="process_list",
                user_id=current_user.user_id,
                target="system",
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=result.get("message", "Process list denied"),
            )

        # 監査ログ記録（成功）
        audit_log.record(
            operation="process_list",
            user_id=current_user.user_id,
            target="system",
            status="success",
            details={"returned_processes": result.get("returned_processes", 0)},
        )

        logger.info(f"Process list retrieved: {result.get('returned_processes', 0)} processes")

        return ProcessListResponse(**result)

    except SudoWrapperError as e:
        # 監査ログ記録（失敗）
        audit_log.record(
            operation="process_list",
            user_id=current_user.user_id,
            target="system",
            status="failure",
            details={"error": str(e)},
        )

        logger.error(f"Process list failed: error={e}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Process list retrieval failed: {str(e)}",
        )


@router.get(
    "/stream",
    summary="プロセス一覧SSEストリーム",
    description="プロセス一覧をServer-Sent Eventsでリアルタイム配信します（EventSource用）。",
)
async def stream_processes(
    interval: float = Query(default=3.0, ge=1.0, le=30.0, description="更新間隔（秒）"),
    token: str = Query(..., description="JWT認証トークン"),
    sort_by: str = Query("cpu", pattern="^(cpu|mem|pid|time)$"),
    limit: int = Query(50, ge=1, le=500),
) -> StreamingResponse:
    """プロセス一覧をSSEでリアルタイム配信する（EventSource用）。

    Args:
        interval: 更新間隔（秒、1-30）
        token: JWT認証トークン（クエリパラメータ経由）
        sort_by: ソートキー (cpu/mem/pid/time)
        limit: 取得件数 (1-500)

    Returns:
        StreamingResponse (text/event-stream)

    Raises:
        HTTPException: トークン不正時
    """
    try:
        user_data = decode_token(token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # read:processes 権限チェック
    required_perm = "read:processes"
    role_obj = ROLES.get(user_data.role)
    user_perms = role_obj.permissions if role_obj else []
    if required_perm not in user_perms:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")

    async def event_generator():
        try:
            yield f"data: {json.dumps({'type': 'connected', 'interval': interval})}\n\n"
            while True:
                try:
                    result = await asyncio.to_thread(
                        sudo_wrapper.get_processes,
                        sort_by=sort_by,
                        limit=limit,
                        filter_user=None,
                        min_cpu=0.0,
                        min_mem=0.0,
                    )
                    payload = json.dumps(
                        {
                            "type": "update",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "data": result,
                        }
                    )
                    yield f"data: {payload}\n\n"
                except Exception as e:
                    yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
