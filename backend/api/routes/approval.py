"""
承認ワークフローAPIルーター

承認リクエストの作成・承認・拒否・一覧取得等のエンドポイント
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.core.approval_service import ApprovalService
from backend.core.auth import TokenData, get_current_user, require_permission
from backend.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/approval", tags=["Approval Workflow"])

# ApprovalService インスタンス
approval_service = ApprovalService(db_path=settings.database.path)


# ===================================================================
# Pydantic モデル定義
# ===================================================================


class CreateApprovalRequest(BaseModel):
    """承認リクエスト作成"""

    request_type: str = Field(
        ...,
        description="操作種別",
        examples=["user_add", "cron_add"],
    )
    payload: dict = Field(
        ...,
        description="操作パラメータ",
    )
    reason: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="申請理由",
    )


class ApproveAction(BaseModel):
    """承認アクション"""

    comment: Optional[str] = Field(
        None,
        max_length=500,
        description="承認コメント",
    )


class RejectAction(BaseModel):
    """拒否アクション"""

    reason: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="拒否理由",
    )


class CancelAction(BaseModel):
    """キャンセルアクション"""

    reason: Optional[str] = Field(
        None,
        max_length=500,
        description="キャンセル理由",
    )


# ===================================================================
# エンドポイント
# ===================================================================


@router.post("/request", status_code=status.HTTP_201_CREATED)
async def create_approval_request(
    request: CreateApprovalRequest,
    current_user: TokenData = Depends(require_permission("request:approval")),
):
    """
    承認リクエストを新規作成

    - **必要権限**: `request:approval` (Operator, Approver, Admin)
    - **リクエストボディ**:
      - `request_type`: 操作種別（policies に定義済みの値）
      - `payload`: 操作パラメータ
      - `reason`: 申請理由（1-1000文字）
    """
    try:
        result = await approval_service.create_request(
            request_type=request.request_type,
            payload=request.payload,
            reason=request.reason,
            requester_id=current_user.user_id,
            requester_name=current_user.username,
            requester_role=current_user.role,
        )

        # result に含まれる "status" (DB上の "pending") と
        # API レスポンスの "status": "success" が衝突するため、
        # result の "status" を "request_status" にリネームして返す
        request_status = result.pop("status", None)
        return {
            "status": "success",
            "message": "承認リクエストを作成しました。Approver/Admin の承認をお待ちください。",
            **result,
            "request_status": request_status,
        }

    except ValueError as e:
        # バリデーションエラー（特殊文字検出等）
        logger.warning(f"Validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Security violation: {str(e)}",
        )

    except LookupError as e:
        # operation_type が存在しない
        logger.warning(f"Invalid request_type: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    except Exception as e:
        logger.error(f"Failed to create approval request: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create approval request",
        )


@router.post("/{request_id}/approve", status_code=status.HTTP_200_OK)
async def approve_request(
    request_id: str,
    action: ApproveAction,
    current_user: TokenData = Depends(require_permission("execute:approval")),
):
    """
    承認リクエストを承認

    - **必要権限**: `execute:approval` (Approver, Admin)
    - **制約**: 自己承認禁止（requester_id != current_user.user_id）
    - **リクエストボディ**:
      - `comment`: 承認コメント（任意、0-500文字）
    """
    try:
        result = await approval_service.approve_request(
            request_id=request_id,
            approver_id=current_user.user_id,
            approver_name=current_user.username,
            approver_role=current_user.role,
            comment=action.comment,
        )

        return {
            "status": "success",
            "message": "承認しました。",
            **result,
        }

    except LookupError as e:
        # リクエストが存在しない
        logger.warning(f"Approval request not found: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    except ValueError as e:
        # 自己承認、ステータス不正、期限切れ等
        error_msg = str(e)
        logger.warning(f"Approval validation error: {error_msg}")

        if "Self-approval is prohibited" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=error_msg,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=error_msg,
            )

    except Exception as e:
        logger.error(f"Failed to approve request: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to approve request",
        )


@router.post("/{request_id}/reject", status_code=status.HTTP_200_OK)
async def reject_request(
    request_id: str,
    action: RejectAction,
    current_user: TokenData = Depends(require_permission("execute:approval")),
):
    """
    承認リクエストを拒否

    - **必要権限**: `execute:approval` (Approver, Admin)
    - **リクエストボディ**:
      - `reason`: 拒否理由（必須、1-1000文字）
    """
    try:
        result = await approval_service.reject_request(
            request_id=request_id,
            approver_id=current_user.user_id,
            approver_name=current_user.username,
            approver_role=current_user.role,
            rejection_reason=action.reason,
        )

        return {
            "status": "success",
            "message": "リクエストを拒否しました。",
            **result,
        }

    except LookupError as e:
        logger.warning(f"Approval request not found: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    except ValueError as e:
        # ステータス不正等
        logger.warning(f"Rejection validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    except Exception as e:
        logger.error(f"Failed to reject request: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reject request",
        )


@router.get("/pending", status_code=status.HTTP_200_OK)
async def list_pending_requests(
    request_type: Optional[str] = None,
    requester_id: Optional[str] = None,
    sort_by: str = "created_at",
    sort_order: str = "asc",
    page: int = 1,
    per_page: int = 20,
    current_user: TokenData = Depends(require_permission("view:approval_pending")),
):
    """
    承認待ちリクエストの一覧を取得（Approver/Admin 向け）

    - **必要権限**: `view:approval_pending` (Approver, Admin)
    - **クエリパラメータ**:
      - `request_type`: 操作種別フィルタ（任意）
      - `requester_id`: 申請者IDフィルタ（任意）
      - `sort_by`: ソートキー（created_at, expires_at, request_type）
      - `sort_order`: ソート順（asc, desc）
      - `page`: ページ番号（デフォルト: 1）
      - `per_page`: 1ページあたり件数（デフォルト: 20、最大100）
    """
    try:
        # per_page の上限チェック
        if per_page > 100:
            per_page = 100

        result = await approval_service.list_pending_requests(
            request_type=request_type,
            requester_id=requester_id,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            per_page=per_page,
        )

        return {
            "status": "success",
            **result,
        }

    except Exception as e:
        logger.error(f"Failed to list pending requests: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list pending requests",
        )


@router.get("/my-requests", status_code=status.HTTP_200_OK)
async def list_my_requests(
    status_filter: Optional[str] = None,
    request_type: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
    current_user: TokenData = Depends(require_permission("request:approval")),
):
    """
    自分の承認リクエストの一覧を取得

    - **必要権限**: `request:approval` (Operator, Approver, Admin)
    - **クエリパラメータ**:
      - `status_filter`: ステータスフィルタ（任意）
      - `request_type`: 操作種別フィルタ（任意）
      - `page`: ページ番号（デフォルト: 1）
      - `per_page`: 1ページあたり件数（デフォルト: 20、最大100）
    """
    try:
        # per_page の上限チェック
        if per_page > 100:
            per_page = 100

        result = await approval_service.list_my_requests(
            requester_id=current_user.user_id,
            status=status_filter,
            request_type=request_type,
            page=page,
            per_page=per_page,
        )

        return {
            "status": "success",
            **result,
        }

    except Exception as e:
        logger.error(f"Failed to list my requests: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list my requests",
        )


@router.get("/policies", status_code=status.HTTP_200_OK)
async def get_approval_policies(
    current_user: TokenData = Depends(require_permission("view:approval_policies")),
):
    """
    承認ポリシーの一覧を取得

    - **必要権限**: `view:approval_policies` (Operator, Approver, Admin)
    """
    try:
        policies = await approval_service.list_policies()

        return {
            "status": "success",
            "policies": policies,
        }

    except Exception as e:
        logger.error(f"Failed to get policies: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get policies",
        )


@router.get("/history", status_code=status.HTTP_200_OK)
async def get_approval_history(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    request_type: Optional[str] = None,
    action: Optional[str] = None,
    actor_id: Optional[str] = None,
    page: int = 1,
    per_page: int = 50,
    current_user: TokenData = Depends(require_permission("view:approval_history")),
):
    """
    承認履歴を取得（監査証跡）（v0.4 実装予定）

    - **必要権限**: `view:approval_history` (Admin)
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Approval history viewing will be implemented in v0.4",
    )


@router.get("/history/export", status_code=status.HTTP_200_OK)
async def export_approval_history(
    format: str = "json",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    request_type: Optional[str] = None,
    current_user: TokenData = Depends(require_permission("export:approval_history")),
):
    """
    承認履歴をエクスポート（CSV/JSON）（v0.4 実装予定）

    - **必要権限**: `export:approval_history` (Admin)
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Approval history export will be implemented in v0.4",
    )


@router.get("/stats", status_code=status.HTTP_200_OK)
async def get_approval_stats(
    period: str = "30d",
    current_user: TokenData = Depends(require_permission("view:approval_stats")),
):
    """
    承認ワークフローの統計情報を取得（v0.4 実装予定）

    - **必要権限**: `view:approval_stats` (Admin)
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Approval statistics will be implemented in v0.4",
    )


# ===================================================================
# パラメータ化ルート（固定パスの後に配置すること）
# ===================================================================


@router.get("/{request_id}", status_code=status.HTTP_200_OK)
async def get_request_detail(
    request_id: str,
    current_user: TokenData = Depends(require_permission("request:approval")),
):
    """
    承認リクエストの詳細を取得

    - **認可**:
      - 申請者本人: Operator, Approver, Admin
      - 他者の申請: Approver, Admin のみ（execute:approval 権限が必要）
    """
    try:
        request_detail = await approval_service.get_request(request_id)

        # 権限チェック: 自分の申請、または Approver/Admin
        is_requester = request_detail["requester_id"] == current_user.user_id
        has_approval_permission = current_user.role in {"Approver", "Admin"}

        if not (is_requester or has_approval_permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only view your own requests or you must have Approver/Admin role",
            )

        return {
            "status": "success",
            "request": request_detail,
        }

    except LookupError as e:
        logger.warning(f"Approval request not found: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    except HTTPException:
        # 権限エラーはそのまま再送出
        raise

    except Exception as e:
        logger.error(f"Failed to get request detail: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get request detail",
        )


@router.post("/{request_id}/cancel", status_code=status.HTTP_200_OK)
async def cancel_request(
    request_id: str,
    action: CancelAction,
    current_user: TokenData = Depends(require_permission("request:approval")),
):
    """
    申請者が自分の承認リクエストをキャンセル

    - **必要権限**: `request:approval` (Operator, Approver, Admin)
    - **制約**: 申請者本人のみ
    - **リクエストボディ**:
      - `reason`: キャンセル理由（任意、0-500文字）
    """
    try:
        result = await approval_service.cancel_request(
            request_id=request_id,
            requester_id=current_user.user_id,
            requester_name=current_user.username,
            requester_role=current_user.role,
            reason=action.reason,
        )

        return {
            "status": "success",
            "message": "リクエストをキャンセルしました。",
            **result,
        }

    except LookupError as e:
        logger.warning(f"Approval request not found: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    except ValueError as e:
        error_msg = str(e)
        logger.warning(f"Cancel validation error: {error_msg}")

        if "Only the requester can cancel" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=error_msg,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=error_msg,
            )

    except Exception as e:
        logger.error(f"Failed to cancel request: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel request",
        )


@router.post("/expire", status_code=status.HTTP_200_OK)
async def expire_old_requests(
    current_user: TokenData = Depends(require_permission("execute:approved_action")),
):
    """
    期限切れリクエストを一括処理（手動トリガー）

    - **必要権限**: `execute:approved_action` (Admin)
    """
    try:
        count = await approval_service.expire_old_requests()

        return {
            "status": "success",
            "message": f"{count} 件のリクエストを期限切れに更新しました。",
            "expired_count": count,
        }

    except Exception as e:
        logger.error(f"Failed to expire old requests: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to expire old requests",
        )


@router.post("/{request_id}/execute", status_code=status.HTTP_200_OK)
async def execute_approved_action(
    request_id: str,
    current_user: TokenData = Depends(require_permission("execute:approved_action")),
):
    """
    承認済みリクエストの操作を手動実行

    - **必要権限**: `execute:approved_action` (Admin)
    - **前提条件**: リクエストのステータスが `approved` であること
    """
    try:
        result = await approval_service.execute_request(
            request_id=request_id,
            executor_id=current_user.user_id,
            executor_name=current_user.username,
            executor_role=current_user.role,
        )

        return {
            "status": "success",
            "message": "操作を実行しました。",
            **result,
        }

    except LookupError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    except NotImplementedError as e:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=str(e),
        )

    except Exception as e:
        logger.error(f"Failed to execute approved action {request_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to execute approved action",
        )
