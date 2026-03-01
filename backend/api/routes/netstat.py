"""Netstat / ネットワーク統計 API ルーター"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from ...core import require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.sudo_wrapper import SudoWrapperError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/netstat", tags=["netstat"])


@router.get("/connections", response_model=Dict[str, Any])
async def get_netstat_connections(
    current_user: TokenData = Depends(require_permission("read:netstat")),
) -> Dict[str, Any]:
    """アクティブ接続一覧を取得 (ss -tnp / netstat -tnp)"""
    try:
        data = sudo_wrapper.get_netstat_connections()
        audit_log.record("netstat_connections_view", current_user.user_id, "netstat", "success")
        return {"success": True, "data": data}
    except SudoWrapperError as e:
        logger.error("Failed to get netstat connections: %s", e)
        audit_log.record("netstat_connections_view", current_user.user_id, "netstat", "failure")
        raise HTTPException(status_code=503, detail=f"ネットワーク接続情報取得エラー: {e}") from e


@router.get("/listening", response_model=Dict[str, Any])
async def get_netstat_listening(
    current_user: TokenData = Depends(require_permission("read:netstat")),
) -> Dict[str, Any]:
    """リスニングポート一覧を取得 (ss -tlnp)"""
    try:
        data = sudo_wrapper.get_netstat_listening()
        audit_log.record("netstat_listening_view", current_user.user_id, "netstat", "success")
        return {"success": True, "data": data}
    except SudoWrapperError as e:
        logger.error("Failed to get netstat listening: %s", e)
        audit_log.record("netstat_listening_view", current_user.user_id, "netstat", "failure")
        raise HTTPException(status_code=503, detail=f"リスニングポート取得エラー: {e}") from e


@router.get("/stats", response_model=Dict[str, Any])
async def get_netstat_stats(
    current_user: TokenData = Depends(require_permission("read:netstat")),
) -> Dict[str, Any]:
    """ネットワーク統計サマリを取得 (ss -s)"""
    try:
        data = sudo_wrapper.get_netstat_stats()
        audit_log.record("netstat_stats_view", current_user.user_id, "netstat", "success")
        return {"success": True, "data": data}
    except SudoWrapperError as e:
        logger.error("Failed to get netstat stats: %s", e)
        audit_log.record("netstat_stats_view", current_user.user_id, "netstat", "failure")
        raise HTTPException(status_code=503, detail=f"ネットワーク統計取得エラー: {e}") from e


@router.get("/routes", response_model=Dict[str, Any])
async def get_netstat_routes(
    current_user: TokenData = Depends(require_permission("read:netstat")),
) -> Dict[str, Any]:
    """ルーティングテーブルを取得 (ip route)"""
    try:
        data = sudo_wrapper.get_netstat_routes()
        audit_log.record("netstat_routes_view", current_user.user_id, "netstat", "success")
        return {"success": True, "data": data}
    except SudoWrapperError as e:
        logger.error("Failed to get netstat routes: %s", e)
        audit_log.record("netstat_routes_view", current_user.user_id, "netstat", "failure")
        raise HTTPException(status_code=503, detail=f"ルーティングテーブル取得エラー: {e}") from e
