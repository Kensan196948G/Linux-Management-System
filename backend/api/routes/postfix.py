"""Postfix / SMTP 管理 API ルーター"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query

from ...core import require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.sudo_wrapper import SudoWrapperError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/postfix", tags=["postfix"])


@router.get("/status", response_model=Dict[str, Any])
async def get_postfix_status(
    current_user: TokenData = Depends(require_permission("read:servers")),
) -> Dict[str, Any]:
    """Postfix サービス状態を取得"""
    try:
        data = sudo_wrapper.get_postfix_status()
        audit_log.record("postfix_status_view", current_user.user_id, "postfix", "success")
        return {"success": True, "data": data}
    except SudoWrapperError as e:
        logger.error("Failed to get postfix status: %s", e)
        audit_log.record("postfix_status_view", current_user.user_id, "postfix", "failure")
        raise HTTPException(status_code=503, detail=f"Postfix ステータス取得エラー: {e}") from e


@router.get("/queue", response_model=Dict[str, Any])
async def get_postfix_queue(
    current_user: TokenData = Depends(require_permission("read:servers")),
) -> Dict[str, Any]:
    """Postfix メールキューを取得"""
    try:
        data = sudo_wrapper.get_postfix_queue()
        audit_log.record("postfix_queue_view", current_user.user_id, "postfix", "success")
        return {"success": True, "data": data}
    except SudoWrapperError as e:
        logger.error("Failed to get postfix queue: %s", e)
        audit_log.record("postfix_queue_view", current_user.user_id, "postfix", "failure")
        raise HTTPException(status_code=503, detail=f"Postfix キュー取得エラー: {e}") from e


@router.get("/logs", response_model=Dict[str, Any])
async def get_postfix_logs(
    lines: int = Query(default=50, ge=1, le=200, description="取得行数"),
    current_user: TokenData = Depends(require_permission("read:servers")),
) -> Dict[str, Any]:
    """Postfix ログを取得"""
    try:
        data = sudo_wrapper.get_postfix_logs(lines=lines)
        audit_log.record("postfix_logs_view", current_user.user_id, "postfix", "success")
        return {"success": True, "data": data}
    except SudoWrapperError as e:
        logger.error("Failed to get postfix logs: %s", e)
        audit_log.record("postfix_logs_view", current_user.user_id, "postfix", "failure")
        raise HTTPException(status_code=503, detail=f"Postfix ログ取得エラー: {e}") from e


@router.get("/queue-detail", response_model=Dict[str, Any])
async def get_postfix_queue_detail(
    current_user: TokenData = Depends(require_permission("read:servers")),
) -> Dict[str, Any]:
    """Postfix キュー詳細を取得 (postqueue -p)"""
    try:
        data = sudo_wrapper.get_postfix_queue_detail()
        audit_log.record("postfix_queue_detail_view", current_user.user_id, "postfix", "success")
        return {"success": True, "data": data}
    except SudoWrapperError as e:
        logger.error("Failed to get postfix queue detail: %s", e)
        audit_log.record("postfix_queue_detail_view", current_user.user_id, "postfix", "failure")
        raise HTTPException(status_code=503, detail=f"Postfix キュー詳細取得エラー: {e}") from e


@router.get("/config", response_model=Dict[str, Any])
async def get_postfix_config(
    current_user: TokenData = Depends(require_permission("read:servers")),
) -> Dict[str, Any]:
    """Postfix 本番設定を取得 (postconf -n)"""
    try:
        data = sudo_wrapper.get_postfix_config()
        audit_log.record("postfix_config_view", current_user.user_id, "postfix", "success")
        return {"success": True, "data": data}
    except SudoWrapperError as e:
        logger.error("Failed to get postfix config: %s", e)
        audit_log.record("postfix_config_view", current_user.user_id, "postfix", "failure")
        raise HTTPException(status_code=503, detail=f"Postfix 設定取得エラー: {e}") from e


@router.get("/stats", response_model=Dict[str, Any])
async def get_postfix_stats(
    current_user: TokenData = Depends(require_permission("read:servers")),
) -> Dict[str, Any]:
    """Postfix 送受信統計を取得"""
    try:
        data = sudo_wrapper.get_postfix_stats()
        audit_log.record("postfix_stats_view", current_user.user_id, "postfix", "success")
        return {"success": True, "data": data}
    except SudoWrapperError as e:
        logger.error("Failed to get postfix stats: %s", e)
        audit_log.record("postfix_stats_view", current_user.user_id, "postfix", "failure")
        raise HTTPException(status_code=503, detail=f"Postfix 統計取得エラー: {e}") from e
