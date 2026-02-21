"""
サービス操作 API エンドポイント
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ...core import get_current_user, require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.sudo_wrapper import SudoWrapperError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/services", tags=["services"])


# ===================================================================
# リクエスト・レスポンスモデル
# ===================================================================


class ServiceRestartRequest(BaseModel):
    """サービス再起動リクエスト"""

    service_name: str = Field(
        ..., min_length=1, max_length=64, pattern="^[a-zA-Z0-9_-]+$"
    )


class ServiceRestartResponse(BaseModel):
    """サービス再起動レスポンス"""

    status: str
    service: str
    before: str
    after: str


# ===================================================================
# エンドポイント
# ===================================================================


@router.post("/restart", response_model=ServiceRestartResponse)
async def restart_service(
    request: ServiceRestartRequest,
    current_user: TokenData = Depends(require_permission("execute:service_restart")),
):
    """
    サービスを再起動

    Args:
        request: サービス再起動リクエスト
        current_user: 現在のユーザー（execute:service_restart 権限必須）

    Returns:
        再起動結果

    Raises:
        HTTPException: 再起動失敗時
    """
    service_name = request.service_name

    logger.info(
        f"Service restart requested: service={service_name}, user={current_user.username}"
    )

    # 監査ログ記録（試行）
    audit_log.record(
        operation="service_restart",
        user_id=current_user.user_id,
        target=service_name,
        status="attempt",
    )

    try:
        # sudo ラッパー経由でサービスを再起動
        result = sudo_wrapper.restart_service(service_name)

        # ラッパーがエラーを返した場合
        if result.get("status") == "error":
            # 監査ログ記録（拒否）
            audit_log.record(
                operation="service_restart",
                user_id=current_user.user_id,
                target=service_name,
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=result.get("message", "Service restart denied"),
            )

        # 監査ログ記録（成功）
        audit_log.record(
            operation="service_restart",
            user_id=current_user.user_id,
            target=service_name,
            status="success",
            details={"before": result.get("before"), "after": result.get("after")},
        )

        logger.info(f"Service restart successful: {service_name}")

        return ServiceRestartResponse(**result)

    except SudoWrapperError as e:
        # 監査ログ記録（失敗）
        audit_log.record(
            operation="service_restart",
            user_id=current_user.user_id,
            target=service_name,
            status="failure",
            details={"error": str(e)},
        )

        logger.error(f"Service restart failed: {service_name}, error={e}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Service restart failed: {str(e)}",
        )
