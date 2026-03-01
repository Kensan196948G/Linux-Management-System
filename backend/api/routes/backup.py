"""バックアップ管理APIルーター (読み取り専用)"""
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from backend.core.auth import TokenData, require_permission
from backend.core.sudo_wrapper import sudo_wrapper

router = APIRouter()


@router.get("/list")
async def get_backup_list(
    current_user: Annotated[TokenData, Depends(require_permission("read:backup"))] = None,
):
    """バックアップファイル一覧 (read:backup権限)"""
    try:
        result = sudo_wrapper.get_backup_list()
        lines = [l for l in result["stdout"].splitlines() if l]
        return {"backups": lines, "count": len(lines), "timestamp": datetime.now(timezone.utc).isoformat()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/status")
async def get_backup_status(
    current_user: Annotated[TokenData, Depends(require_permission("read:backup"))] = None,
):
    """バックアップステータス (read:backup権限)"""
    try:
        result = sudo_wrapper.get_backup_status()
        return {"status": result["stdout"], "returncode": result["returncode"]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/disk-usage")
async def get_backup_disk_usage(
    current_user: Annotated[TokenData, Depends(require_permission("read:backup"))] = None,
):
    """バックアップディスク使用量 (read:backup権限)"""
    try:
        result = sudo_wrapper.get_backup_disk_usage()
        return {"usage": result["stdout"].strip(), "timestamp": datetime.now(timezone.utc).isoformat()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/recent-logs")
async def get_backup_recent_logs(
    current_user: Annotated[TokenData, Depends(require_permission("read:backup"))] = None,
):
    """バックアップ関連ログ (read:backup権限)"""
    try:
        result = sudo_wrapper.get_backup_recent_logs()
        lines = [l for l in result["stdout"].splitlines() if l]
        return {"logs": lines, "count": len(lines)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

