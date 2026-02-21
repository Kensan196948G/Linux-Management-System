"""
ログ閲覧 API エンドポイント
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel

from ...core import get_current_user, require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.sudo_wrapper import SudoWrapperError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/logs", tags=["logs"])


# ===================================================================
# レスポンスモデル
# ===================================================================


class LogsResponse(BaseModel):
    """ログレスポンス"""

    status: str
    service: str
    lines_requested: int
    lines_returned: int
    logs: list[str]
    timestamp: str


# ===================================================================
# エンドポイント
# ===================================================================


@router.get("/{service_name}", response_model=LogsResponse)
async def get_service_logs(
    service_name: str = Path(
        ..., min_length=1, max_length=64, pattern="^[a-zA-Z0-9_-]+$"
    ),
    lines: int = Query(100, ge=1, le=1000, description="取得行数（1-1000）"),
    current_user: TokenData = Depends(require_permission("read:logs")),
):
    """
    サービスのログを取得

    Args:
        service_name: サービス名
        lines: 取得行数（1-1000）
        current_user: 現在のユーザー（read:logs 権限必須）

    Returns:
        ログデータ

    Raises:
        HTTPException: ログ取得失敗時
    """
    logger.info(
        f"Log view requested: service={service_name}, lines={lines}, user={current_user.username}"
    )

    # 監査ログ記録（試行）
    audit_log.record(
        operation="log_view",
        user_id=current_user.user_id,
        target=service_name,
        status="attempt",
        details={"lines": lines},
    )

    try:
        # sudo ラッパー経由でログを取得
        result = sudo_wrapper.get_logs(service_name, lines)

        # ラッパーがエラーを返した場合
        if result.get("status") == "error":
            # 監査ログ記録（拒否）
            audit_log.record(
                operation="log_view",
                user_id=current_user.user_id,
                target=service_name,
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=result.get("message", "Log view denied"),
            )

        # 監査ログ記録（成功）
        audit_log.record(
            operation="log_view",
            user_id=current_user.user_id,
            target=service_name,
            status="success",
            details={"lines_returned": result.get("lines_returned", 0)},
        )

        logger.info(f"Log view successful: {service_name}")

        return LogsResponse(**result)

    except SudoWrapperError as e:
        # 監査ログ記録（失敗）
        audit_log.record(
            operation="log_view",
            user_id=current_user.user_id,
            target=service_name,
            status="failure",
            details={"error": str(e)},
        )

        logger.error(f"Log view failed: {service_name}, error={e}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Log retrieval failed: {str(e)}",
        )
