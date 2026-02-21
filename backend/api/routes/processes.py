"""
プロセス管理 API エンドポイント
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ...core import get_current_user, require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import TokenData
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
    filter_user: Optional[str] = Query(
        None, min_length=1, max_length=32, pattern="^[a-zA-Z0-9_-]+$"
    ),
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

        logger.info(
            f"Process list retrieved: {result.get('returned_processes', 0)} processes"
        )

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
