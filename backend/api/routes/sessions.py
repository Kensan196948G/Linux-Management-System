"""ユーザーセッション管理APIルーター"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from backend.core.audit_log import audit_log
from backend.core.auth import TokenData, require_permission
from backend.core.rate_limiter import rate_limiter
from backend.core.session_store import session_store
from backend.core.sudo_wrapper import sudo_wrapper

router = APIRouter()


@router.get("/active")
async def get_active_sessions(
    current_user: Annotated[TokenData, Depends(require_permission("read:sessions"))] = None,
):
    """アクティブセッション一覧 (read:sessions権限)"""
    try:
        result = sudo_wrapper.get_active_sessions()
        lines = [ln for ln in result["stdout"].splitlines() if ln]
        return {"sessions": lines, "count": len(lines), "timestamp": datetime.now(timezone.utc).isoformat()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/history")
async def get_session_history(
    current_user: Annotated[TokenData, Depends(require_permission("read:sessions"))] = None,
):
    """ログイン履歴 (read:sessions権限)"""
    try:
        result = sudo_wrapper.get_session_history()
        lines = [ln for ln in result["stdout"].splitlines() if ln]
        return {"history": lines, "count": len(lines), "timestamp": datetime.now(timezone.utc).isoformat()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/failed")
async def get_failed_sessions(
    current_user: Annotated[TokenData, Depends(require_permission("read:sessions"))] = None,
):
    """ログイン失敗一覧 (read:sessions権限)"""
    try:
        result = sudo_wrapper.get_failed_sessions()
        lines = [ln for ln in result["stdout"].splitlines() if ln]
        return {"failed_logins": lines, "count": len(lines)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/wtmp-summary")
async def get_wtmp_summary(
    current_user: Annotated[TokenData, Depends(require_permission("read:sessions"))] = None,
):
    """ログイン統計サマリー (read:sessions権限)"""
    try:
        result = sudo_wrapper.get_wtmp_summary()
        lines = [ln for ln in result["stdout"].splitlines() if ln]
        return {"summary": lines, "count": len(lines)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


# ===================================================================
# JWTセッション管理エンドポイント
# ===================================================================


@router.get("/jwt")
async def get_jwt_sessions(
    current_user: Annotated[TokenData, Depends(require_permission("read:session_mgmt"))] = None,
):
    """
    アクティブJWTセッション一覧 (Admin/Approver only)。

    Returns:
        セッション一覧とカウント
    """
    try:
        sessions = session_store.get_active_sessions()
        audit_log.record(
            operation="list_jwt_sessions",
            user_id=current_user.user_id,
            target="sessions",
            status="success",
            details={"count": len(sessions)},
        )
        return {"sessions": sessions, "count": len(sessions), "timestamp": datetime.now(timezone.utc).isoformat()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.delete("/jwt/user/{user_email}")
async def revoke_user_sessions(
    user_email: str,
    current_user: Annotated[TokenData, Depends(require_permission("manage:sessions"))] = None,
):
    """
    ユーザーの全JWTセッションを強制終了する (Admin only)。

    Args:
        user_email: 対象ユーザーのメールアドレス

    Returns:
        無効化したセッション数
    """
    try:
        count = session_store.revoke_user_sessions(user_email)
        audit_log.record(
            operation="revoke_user_sessions",
            user_id=current_user.user_id,
            target=user_email,
            status="success",
            details={"revoked_count": count},
        )
        return {"status": "success", "revoked_count": count, "user_email": user_email}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.delete("/jwt/{session_id}")
async def revoke_jwt_session(
    session_id: str,
    current_user: Annotated[TokenData, Depends(require_permission("manage:sessions"))] = None,
):
    """
    特定JWTセッションを強制終了する (Admin only)。

    Args:
        session_id: 無効化するセッションID (JTI)

    Returns:
        処理結果
    """
    try:
        revoked = session_store.revoke_session(session_id)
        if not revoked:
            raise HTTPException(status_code=404, detail={"status": "error", "message": "Session not found"})
        audit_log.record(
            operation="revoke_jwt_session",
            user_id=current_user.user_id,
            target=session_id,
            status="success",
            details={},
        )
        return {"status": "success", "session_id": session_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/rate-limit-status")
async def get_rate_limit_status(
    current_user: Annotated[TokenData, Depends(require_permission("manage:sessions"))] = None,
):
    """
    レート制限状況一覧（ロック中のIP/メール）(Admin only)。

    Returns:
        ロック中エントリ一覧
    """
    try:
        locked_entries = rate_limiter.get_all_locked()
        return {
            "locked_entries": locked_entries,
            "count": len(locked_entries),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.delete("/rate-limit/{identifier}")
async def clear_rate_limit(
    identifier: str,
    current_user: Annotated[TokenData, Depends(require_permission("manage:sessions"))] = None,
):
    """
    特定のIP/メールのレート制限を解除する (Admin only)。

    Args:
        identifier: IPアドレスまたはメールアドレス

    Returns:
        処理結果
    """
    try:
        cleared = rate_limiter.clear_lock(identifier)
        if not cleared:
            raise HTTPException(
                status_code=404, detail={"status": "error", "message": "Identifier not found in rate limit records"}
            )
        audit_log.record(
            operation="clear_rate_limit",
            user_id=current_user.user_id,
            target=identifier,
            status="success",
            details={},
        )
        return {"status": "success", "identifier": identifier}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
