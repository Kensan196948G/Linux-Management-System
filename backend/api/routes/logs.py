"""
ログ閲覧 API エンドポイント
"""

import logging
from typing import Any, Dict, List

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


# ===================================================================
# ログ検索エンドポイント (Step 25)
# ===================================================================

FORBIDDEN_CHARS_LOG = [";", "|", "&", "$", "(", ")", "`", ">", "<", "*", "?"]


def _validate_query(value: str) -> None:
    """検索クエリの禁止文字チェック。

    Args:
        value: 検証する文字列

    Raises:
        HTTPException: 禁止文字が含まれる場合
    """
    for char in FORBIDDEN_CHARS_LOG:
        if char in value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Forbidden character in query: {char}",
            )


@router.get("/search")
async def search_logs(
    q: str = Query(..., min_length=1, max_length=100, description="検索キーワード"),
    file: str = Query(default="syslog", description="検索対象ログファイル"),
    lines: int = Query(default=50, ge=1, le=200),
    current_user: TokenData = Depends(require_permission("read:logs")),
) -> Dict[str, Any]:
    """ログファイルを全文検索

    Args:
        q: 検索キーワード（1-100文字）
        file: 検索対象ログファイル名
        lines: 返却最大行数（1-200）
        current_user: 現在のユーザー（read:logs 権限必須）

    Returns:
        検索結果の辞書

    Raises:
        HTTPException: 禁止文字または検索失敗時
    """
    _validate_query(q)
    _validate_query(file)

    logger.info(f"Log search requested: q={q!r}, file={file}, lines={lines}, user={current_user.username}")

    audit_log.record(
        operation="log_search",
        user_id=current_user.user_id,
        target=file,
        status="attempt",
        details={"query": q, "lines": lines},
    )

    try:
        result = sudo_wrapper.search_logs(q, file, lines)

        if result.get("status") == "error":
            audit_log.record(
                operation="log_search",
                user_id=current_user.user_id,
                target=file,
                status="denied",
                details={"reason": result.get("message", "unknown")},
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "Log search denied"),
            )

        audit_log.record(
            operation="log_search",
            user_id=current_user.user_id,
            target=file,
            status="success",
            details={"lines_returned": result.get("lines_returned", 0)},
        )

        return result

    except SudoWrapperError as e:
        if "Forbidden character" in str(e):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )
        audit_log.record(
            operation="log_search",
            user_id=current_user.user_id,
            target=file,
            status="failure",
            details={"error": str(e)},
        )
        logger.error(f"Log search failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Log search failed: {str(e)}",
        )


@router.get("/files")
async def list_log_files(
    current_user: TokenData = Depends(require_permission("read:logs")),
) -> Dict[str, Any]:
    """利用可能なログファイル一覧

    Args:
        current_user: 現在のユーザー（read:logs 権限必須）

    Returns:
        ログファイル一覧の辞書

    Raises:
        HTTPException: 取得失敗時
    """
    logger.info(f"Log files list requested: user={current_user.username}")

    audit_log.record(
        operation="log_files_list",
        user_id=current_user.user_id,
        target="log_files",
        status="attempt",
        details={},
    )

    try:
        result = sudo_wrapper.list_log_files()

        if result.get("status") == "error":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("message", "Failed to list log files"),
            )

        audit_log.record(
            operation="log_files_list",
            user_id=current_user.user_id,
            target="log_files",
            status="success",
            details={"file_count": result.get("file_count", 0)},
        )

        return result

    except SudoWrapperError as e:
        logger.error(f"Log files list failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Log files list failed: {str(e)}",
        )


@router.get("/recent-errors")
async def get_recent_errors(
    current_user: TokenData = Depends(require_permission("read:logs")),
) -> Dict[str, Any]:
    """直近のエラーログ集約

    Args:
        current_user: 現在のユーザー（read:logs 権限必須）

    Returns:
        直近エラーログの辞書

    Raises:
        HTTPException: 取得失敗時
    """
    logger.info(f"Recent errors requested: user={current_user.username}")

    audit_log.record(
        operation="log_recent_errors",
        user_id=current_user.user_id,
        target="recent_errors",
        status="attempt",
        details={},
    )

    try:
        result = sudo_wrapper.get_recent_errors()

        if result.get("status") == "error":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("message", "Failed to get recent errors"),
            )

        audit_log.record(
            operation="log_recent_errors",
            user_id=current_user.user_id,
            target="recent_errors",
            status="success",
            details={"error_count": result.get("error_count", 0)},
        )

        return result

    except SudoWrapperError as e:
        logger.error(f"Recent errors fetch failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Recent errors fetch failed: {str(e)}",
        )
