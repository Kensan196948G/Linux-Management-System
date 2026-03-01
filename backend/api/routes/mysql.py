"""MySQL/MariaDB 管理 API ルーター"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query

from ...core import require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.sudo_wrapper import SudoWrapperError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mysql", tags=["mysql"])


@router.get("/status", response_model=Dict[str, Any])
async def get_mysql_status(
    current_user: TokenData = Depends(require_permission("read:mysql")),
) -> Dict[str, Any]:
    """MySQL/MariaDB サービス状態・バージョンを取得"""
    try:
        data = sudo_wrapper.get_mysql_status()
        audit_log.record("mysql_status_view", current_user.user_id, "mysql", "success")
        return {"success": True, "data": data}
    except SudoWrapperError as e:
        logger.error("Failed to get mysql status: %s", e)
        audit_log.record("mysql_status_view", current_user.user_id, "mysql", "failure")
        raise HTTPException(status_code=503, detail=f"MySQL ステータス取得エラー: {e}") from e


@router.get("/databases", response_model=Dict[str, Any])
async def get_mysql_databases(
    current_user: TokenData = Depends(require_permission("read:mysql")),
) -> Dict[str, Any]:
    """データベース一覧を取得"""
    try:
        data = sudo_wrapper.get_mysql_databases()
        audit_log.record("mysql_databases_view", current_user.user_id, "mysql", "success")
        return {"success": True, "data": data}
    except SudoWrapperError as e:
        logger.error("Failed to get mysql databases: %s", e)
        audit_log.record("mysql_databases_view", current_user.user_id, "mysql", "failure")
        raise HTTPException(status_code=503, detail=f"MySQL データベース一覧取得エラー: {e}") from e


@router.get("/users", response_model=Dict[str, Any])
async def get_mysql_users(
    current_user: TokenData = Depends(require_permission("read:mysql")),
) -> Dict[str, Any]:
    """ユーザー一覧を取得（パスワードハッシュは除外）"""
    try:
        data = sudo_wrapper.get_mysql_users()
        audit_log.record("mysql_users_view", current_user.user_id, "mysql", "success")
        return {"success": True, "data": data}
    except SudoWrapperError as e:
        logger.error("Failed to get mysql users: %s", e)
        audit_log.record("mysql_users_view", current_user.user_id, "mysql", "failure")
        raise HTTPException(status_code=503, detail=f"MySQL ユーザー一覧取得エラー: {e}") from e


@router.get("/processes", response_model=Dict[str, Any])
async def get_mysql_processes(
    current_user: TokenData = Depends(require_permission("read:mysql")),
) -> Dict[str, Any]:
    """プロセスリストを取得"""
    try:
        data = sudo_wrapper.get_mysql_processes()
        audit_log.record("mysql_processes_view", current_user.user_id, "mysql", "success")
        return {"success": True, "data": data}
    except SudoWrapperError as e:
        logger.error("Failed to get mysql processes: %s", e)
        audit_log.record("mysql_processes_view", current_user.user_id, "mysql", "failure")
        raise HTTPException(status_code=503, detail=f"MySQL プロセスリスト取得エラー: {e}") from e


@router.get("/variables", response_model=Dict[str, Any])
async def get_mysql_variables(
    current_user: TokenData = Depends(require_permission("read:mysql")),
) -> Dict[str, Any]:
    """システム変数（重要なもの）を取得"""
    try:
        data = sudo_wrapper.get_mysql_variables()
        audit_log.record("mysql_variables_view", current_user.user_id, "mysql", "success")
        return {"success": True, "data": data}
    except SudoWrapperError as e:
        logger.error("Failed to get mysql variables: %s", e)
        audit_log.record("mysql_variables_view", current_user.user_id, "mysql", "failure")
        raise HTTPException(status_code=503, detail=f"MySQL 変数取得エラー: {e}") from e


@router.get("/logs", response_model=Dict[str, Any])
async def get_mysql_logs(
    lines: int = Query(default=50, ge=1, le=200, description="取得行数"),
    current_user: TokenData = Depends(require_permission("read:mysql")),
) -> Dict[str, Any]:
    """MySQL エラーログを取得"""
    try:
        data = sudo_wrapper.get_mysql_logs(lines=lines)
        audit_log.record("mysql_logs_view", current_user.user_id, "mysql", "success")
        return {"success": True, "data": data}
    except SudoWrapperError as e:
        logger.error("Failed to get mysql logs: %s", e)
        audit_log.record("mysql_logs_view", current_user.user_id, "mysql", "failure")
        raise HTTPException(status_code=503, detail=f"MySQL ログ取得エラー: {e}") from e
