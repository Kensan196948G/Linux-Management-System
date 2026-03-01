"""DHCP Server 管理 API ルーター"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query

from ...core import require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.sudo_wrapper import SudoWrapperError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dhcp", tags=["dhcp"])


@router.get("/status", response_model=Dict[str, Any])
async def get_dhcp_status(
    current_user: TokenData = Depends(require_permission("read:dhcp")),
) -> Dict[str, Any]:
    """DHCP サービス状態を取得"""
    try:
        data = sudo_wrapper.get_dhcp_status()
        audit_log.record("dhcp_status_view", current_user.user_id, "dhcp", "success")
        if data.get("status") == "unavailable":
            raise HTTPException(status_code=503, detail="isc-dhcp-server はインストールされていません")
        return {"success": True, "data": data}
    except HTTPException:
        raise
    except SudoWrapperError as e:
        logger.error("Failed to get dhcp status: %s", e)
        audit_log.record("dhcp_status_view", current_user.user_id, "dhcp", "failure")
        raise HTTPException(status_code=503, detail=f"DHCP ステータス取得エラー: {e}") from e


@router.get("/leases", response_model=Dict[str, Any])
async def get_dhcp_leases(
    current_user: TokenData = Depends(require_permission("read:dhcp")),
) -> Dict[str, Any]:
    """DHCP アクティブリース一覧を取得"""
    try:
        data = sudo_wrapper.get_dhcp_leases()
        audit_log.record("dhcp_leases_view", current_user.user_id, "dhcp", "success")
        if data.get("status") == "unavailable":
            raise HTTPException(status_code=503, detail="isc-dhcp-server はインストールされていません")
        return {"success": True, "data": data}
    except HTTPException:
        raise
    except SudoWrapperError as e:
        logger.error("Failed to get dhcp leases: %s", e)
        audit_log.record("dhcp_leases_view", current_user.user_id, "dhcp", "failure")
        raise HTTPException(status_code=503, detail=f"DHCP リース取得エラー: {e}") from e


@router.get("/config", response_model=Dict[str, Any])
async def get_dhcp_config(
    current_user: TokenData = Depends(require_permission("read:dhcp")),
) -> Dict[str, Any]:
    """DHCP 設定サマリを取得"""
    try:
        data = sudo_wrapper.get_dhcp_config()
        audit_log.record("dhcp_config_view", current_user.user_id, "dhcp", "success")
        if data.get("status") == "unavailable":
            raise HTTPException(status_code=503, detail="isc-dhcp-server はインストールされていません")
        return {"success": True, "data": data}
    except HTTPException:
        raise
    except SudoWrapperError as e:
        logger.error("Failed to get dhcp config: %s", e)
        audit_log.record("dhcp_config_view", current_user.user_id, "dhcp", "failure")
        raise HTTPException(status_code=503, detail=f"DHCP 設定取得エラー: {e}") from e


@router.get("/pools", response_model=Dict[str, Any])
async def get_dhcp_pools(
    current_user: TokenData = Depends(require_permission("read:dhcp")),
) -> Dict[str, Any]:
    """DHCP アドレスプール情報を取得"""
    try:
        data = sudo_wrapper.get_dhcp_pools()
        audit_log.record("dhcp_pools_view", current_user.user_id, "dhcp", "success")
        if data.get("status") == "unavailable":
            raise HTTPException(status_code=503, detail="isc-dhcp-server はインストールされていません")
        return {"success": True, "data": data}
    except HTTPException:
        raise
    except SudoWrapperError as e:
        logger.error("Failed to get dhcp pools: %s", e)
        audit_log.record("dhcp_pools_view", current_user.user_id, "dhcp", "failure")
        raise HTTPException(status_code=503, detail=f"DHCP プール取得エラー: {e}") from e


@router.get("/logs", response_model=Dict[str, Any])
async def get_dhcp_logs(
    lines: int = Query(default=50, ge=1, le=200, description="取得行数"),
    current_user: TokenData = Depends(require_permission("read:dhcp")),
) -> Dict[str, Any]:
    """DHCP ログを取得"""
    try:
        data = sudo_wrapper.get_dhcp_logs(lines=lines)
        audit_log.record("dhcp_logs_view", current_user.user_id, "dhcp", "success")
        if data.get("status") == "unavailable":
            raise HTTPException(status_code=503, detail="isc-dhcp-server はインストールされていません")
        return {"success": True, "data": data}
    except HTTPException:
        raise
    except SudoWrapperError as e:
        logger.error("Failed to get dhcp logs: %s", e)
        audit_log.record("dhcp_logs_view", current_user.user_id, "dhcp", "failure")
        raise HTTPException(status_code=503, detail=f"DHCP ログ取得エラー: {e}") from e
