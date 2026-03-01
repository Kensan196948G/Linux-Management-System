"""systemdジャーナルログ管理APIルーター"""
import re
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.core.auth import TokenData, require_permission
from backend.core.sudo_wrapper import sudo_wrapper

router = APIRouter()


@router.get("/list")
async def get_journal_list(
    lines: int = Query(default=100, ge=1, le=1000),
    current_user: Annotated[TokenData, Depends(require_permission("read:journal"))] = None,
):
    """ジャーナルログ一覧を取得"""
    try:
        result = sudo_wrapper.get_journal_list(lines)
        log_lines = [l for l in result["stdout"].splitlines() if l]
        return {"logs": log_lines, "count": len(log_lines), "timestamp": datetime.now(timezone.utc).isoformat()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/units")
async def get_journal_units(
    current_user: Annotated[TokenData, Depends(require_permission("read:journal"))] = None,
):
    """systemdユニット一覧を取得"""
    try:
        result = sudo_wrapper.get_journal_units()
        units = [l for l in result["stdout"].splitlines() if l]
        return {"units": units, "count": len(units)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/unit-logs/{unit_name}")
async def get_unit_logs(
    unit_name: str,
    current_user: Annotated[TokenData, Depends(require_permission("read:journal"))] = None,
):
    """特定ユニットのログを取得"""
    if not re.match(r'^[a-zA-Z0-9._@:-]+$', unit_name):
        raise HTTPException(status_code=400, detail="Invalid unit name")
    try:
        result = sudo_wrapper.get_journal_unit_logs(unit_name)
        log_lines = [l for l in result["stdout"].splitlines() if l]
        return {"unit": unit_name, "logs": log_lines, "count": len(log_lines)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/boot-logs")
async def get_boot_logs(
    current_user: Annotated[TokenData, Depends(require_permission("read:journal"))] = None,
):
    """ブートログを取得"""
    try:
        result = sudo_wrapper.get_journal_boot_logs()
        log_lines = [l for l in result["stdout"].splitlines() if l]
        return {"logs": log_lines, "count": len(log_lines)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/kernel-logs")
async def get_kernel_logs(
    current_user: Annotated[TokenData, Depends(require_permission("read:journal"))] = None,
):
    """カーネルログを取得"""
    try:
        result = sudo_wrapper.get_journal_kernel_logs()
        log_lines = [l for l in result["stdout"].splitlines() if l]
        return {"logs": log_lines, "count": len(log_lines)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/priority-logs")
async def get_priority_logs(
    priority: str = Query(default="err"),
    current_user: Annotated[TokenData, Depends(require_permission("read:journal"))] = None,
):
    """優先度別ログを取得"""
    ALLOWED = ["emerg", "alert", "crit", "err", "warning", "notice", "info", "debug"]
    if priority not in ALLOWED:
        raise HTTPException(status_code=400, detail=f"Invalid priority. Allowed: {ALLOWED}")
    try:
        result = sudo_wrapper.get_journal_priority_logs(priority)
        log_lines = [l for l in result["stdout"].splitlines() if l]
        return {"priority": priority, "logs": log_lines, "count": len(log_lines)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
