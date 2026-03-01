"""BIND DNS サーバー管理 API ルーター"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query

from ...core import require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.sudo_wrapper import SudoWrapperError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bind", tags=["bind"])


@router.get("/status", response_model=Dict[str, Any])
async def get_bind_status(
    current_user: TokenData = Depends(require_permission("read:bind")),
) -> Dict[str, Any]:
    """BIND DNS サービス状態を取得"""
    try:
        data = sudo_wrapper.get_bind_status()
        audit_log.record("bind_status_view", current_user.user_id, "bind", "success")
        return {"success": True, "data": data}
    except SudoWrapperError as e:
        logger.error("Failed to get bind status: %s", e)
        audit_log.record("bind_status_view", current_user.user_id, "bind", "failure")
        raise HTTPException(status_code=503, detail=f"BIND ステータス取得エラー: {e}") from e


@router.get("/zones", response_model=Dict[str, Any])
async def get_bind_zones(
    current_user: TokenData = Depends(require_permission("read:bind")),
) -> Dict[str, Any]:
    """BIND ゾーン一覧を取得"""
    try:
        data = sudo_wrapper.get_bind_zones()
        audit_log.record("bind_zones_view", current_user.user_id, "bind", "success")
        return {"success": True, "data": data}
    except SudoWrapperError as e:
        logger.error("Failed to get bind zones: %s", e)
        audit_log.record("bind_zones_view", current_user.user_id, "bind", "failure")
        raise HTTPException(status_code=503, detail=f"BIND ゾーン取得エラー: {e}") from e


@router.get("/config", response_model=Dict[str, Any])
async def get_bind_config(
    current_user: TokenData = Depends(require_permission("read:bind")),
) -> Dict[str, Any]:
    """BIND 設定確認 (named-checkconf)"""
    try:
        data = sudo_wrapper.get_bind_config()
        audit_log.record("bind_config_view", current_user.user_id, "bind", "success")
        return {"success": True, "data": data}
    except SudoWrapperError as e:
        logger.error("Failed to get bind config: %s", e)
        audit_log.record("bind_config_view", current_user.user_id, "bind", "failure")
        raise HTTPException(status_code=503, detail=f"BIND 設定確認エラー: {e}") from e


@router.get("/logs", response_model=Dict[str, Any])
async def get_bind_logs(
    lines: int = Query(default=50, ge=1, le=200, description="取得行数"),
    current_user: TokenData = Depends(require_permission("read:bind")),
) -> Dict[str, Any]:
    """BIND DNS ログを取得"""
    try:
        data = sudo_wrapper.get_bind_logs(lines=lines)
        audit_log.record("bind_logs_view", current_user.user_id, "bind", "success")
        return {"success": True, "data": data}
    except SudoWrapperError as e:
        logger.error("Failed to get bind logs: %s", e)
        audit_log.record("bind_logs_view", current_user.user_id, "bind", "failure")
        raise HTTPException(status_code=503, detail=f"BIND ログ取得エラー: {e}") from e
