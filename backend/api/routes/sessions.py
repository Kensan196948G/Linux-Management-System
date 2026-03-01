"""ユーザーセッション管理APIルーター"""
from fastapi import APIRouter, Depends, HTTPException
from backend.core.auth import get_current_user, require_permission
from backend.core.sudo_wrapper import sudo_wrapper
from datetime import datetime, timezone

router = APIRouter()


@router.get("/active")
async def get_active_sessions(current_user: dict = Depends(get_current_user)):
    """アクティブセッション一覧 (read:sessions権限)"""
    require_permission(current_user, "read:sessions")
    try:
        result = sudo_wrapper.get_active_sessions()
        lines = [l for l in result["stdout"].splitlines() if l]
        return {"sessions": lines, "count": len(lines), "timestamp": datetime.now(timezone.utc).isoformat()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/history")
async def get_session_history(current_user: dict = Depends(get_current_user)):
    """ログイン履歴 (read:sessions権限)"""
    require_permission(current_user, "read:sessions")
    try:
        result = sudo_wrapper.get_session_history()
        lines = [l for l in result["stdout"].splitlines() if l]
        return {"history": lines, "count": len(lines), "timestamp": datetime.now(timezone.utc).isoformat()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/failed")
async def get_failed_sessions(current_user: dict = Depends(get_current_user)):
    """ログイン失敗一覧 (read:sessions権限)"""
    require_permission(current_user, "read:sessions")
    try:
        result = sudo_wrapper.get_failed_sessions()
        lines = [l for l in result["stdout"].splitlines() if l]
        return {"failed_logins": lines, "count": len(lines)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/wtmp-summary")
async def get_wtmp_summary(current_user: dict = Depends(get_current_user)):
    """ログイン統計サマリー (read:sessions権限)"""
    require_permission(current_user, "read:sessions")
    try:
        result = sudo_wrapper.get_wtmp_summary()
        lines = [l for l in result["stdout"].splitlines() if l]
        return {"summary": lines, "count": len(lines)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
