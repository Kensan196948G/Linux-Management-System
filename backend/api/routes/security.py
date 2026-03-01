"""
セキュリティ監査 API エンドポイント

提供エンドポイント:
  GET /api/security/audit-report      - 監査ログ統計
  GET /api/security/failed-logins     - ログイン失敗一覧
  GET /api/security/sudo-logs         - sudo使用ログ
  GET /api/security/open-ports        - 開放ポート一覧
  GET /api/security/bandit-status     - bandit スキャン結果サマリ
"""

import json
import logging
import subprocess
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ...core import require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.sudo_wrapper import SudoWrapperError
from ._utils import parse_wrapper_result

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/security", tags=["security"])


# ===================================================================
# レスポンスモデル
# ===================================================================


class AuditReportResponse(BaseModel):
    """監査ログ統計レスポンス"""

    status: str
    auth_log_lines: int = 0
    accepted_logins: int = 0
    failed_logins: int = 0
    sudo_count: int = 0
    last_login: str = ""
    timestamp: str


class LogEntriesResponse(BaseModel):
    """ログエントリ一覧レスポンス"""

    status: str
    entries: List[str] = Field(default_factory=list)
    timestamp: str


class OpenPortsResponse(BaseModel):
    """開放ポート一覧レスポンス"""

    status: str
    output: str = ""
    timestamp: str


class BanditStatusResponse(BaseModel):
    """bandit スキャン結果サマリ"""

    status: str
    high: int = 0
    medium: int = 0
    low: int = 0
    total_issues: int = 0
    scanned: bool = False
    error: Optional[str] = None


# ===================================================================
# エンドポイント
# ===================================================================


@router.get(
    "/audit-report",
    response_model=AuditReportResponse,
    summary="監査ログ統計",
)
async def get_audit_report(
    current_user: TokenData = Depends(require_permission("read:security")),
) -> AuditReportResponse:
    """監査ログの統計情報（認証成功/失敗件数、sudo使用件数、最終ログイン）を返す"""
    try:
        result = sudo_wrapper.get_security_audit_report()
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="security_audit_report_read",
            user_id=current_user.user_id,
            target="auth.log",
            status="success",
            details={},
        )
        return AuditReportResponse(**parsed)
    except SudoWrapperError as e:
        logger.error("Security audit-report error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"監査レポート取得エラー: {e}",
        )
    except Exception as e:
        logger.error("Unexpected error in get_audit_report: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )


@router.get(
    "/failed-logins",
    response_model=LogEntriesResponse,
    summary="ログイン失敗一覧",
)
async def get_failed_logins(
    current_user: TokenData = Depends(require_permission("read:security")),
) -> LogEntriesResponse:
    """auth.log から失敗ログイン一覧（最大50件）を返す"""
    try:
        result = sudo_wrapper.get_failed_logins()
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="security_failed_logins_read",
            user_id=current_user.user_id,
            target="auth.log",
            status="success",
            details={"count": len(parsed.get("entries", []))},
        )
        return LogEntriesResponse(**parsed)
    except SudoWrapperError as e:
        logger.error("Security failed-logins error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"失敗ログイン取得エラー: {e}",
        )
    except Exception as e:
        logger.error("Unexpected error in get_failed_logins: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )


@router.get(
    "/sudo-logs",
    response_model=LogEntriesResponse,
    summary="sudo使用ログ",
)
async def get_sudo_logs(
    current_user: TokenData = Depends(require_permission("read:security")),
) -> LogEntriesResponse:
    """auth.log から sudo 使用ログ（最大50件）を返す"""
    try:
        result = sudo_wrapper.get_sudo_logs()
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="security_sudo_logs_read",
            user_id=current_user.user_id,
            target="auth.log",
            status="success",
            details={"count": len(parsed.get("entries", []))},
        )
        return LogEntriesResponse(**parsed)
    except SudoWrapperError as e:
        logger.error("Security sudo-logs error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"sudoログ取得エラー: {e}",
        )
    except Exception as e:
        logger.error("Unexpected error in get_sudo_logs: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )


@router.get(
    "/open-ports",
    response_model=OpenPortsResponse,
    summary="開放ポート一覧",
)
async def get_open_ports(
    current_user: TokenData = Depends(require_permission("read:security")),
) -> OpenPortsResponse:
    """ss -tlnp で TCP リスニングポート一覧を返す"""
    try:
        result = sudo_wrapper.get_open_ports()
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="security_open_ports_read",
            user_id=current_user.user_id,
            target="open_ports",
            status="success",
            details={},
        )
        return OpenPortsResponse(**parsed)
    except SudoWrapperError as e:
        logger.error("Security open-ports error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"開放ポート取得エラー: {e}",
        )
    except Exception as e:
        logger.error("Unexpected error in get_open_ports: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )


@router.get(
    "/bandit-status",
    response_model=BanditStatusResponse,
    summary="bandit スキャン結果サマリ",
)
async def get_bandit_status(
    current_user: TokenData = Depends(require_permission("read:security")),
) -> BanditStatusResponse:
    """bandit -r backend/ -ll -f json を実行し High/Medium 件数を返す（sudo なし）"""
    try:
        # shell=True 禁止 — 配列渡しで実行
        proc = subprocess.run(
            ["bandit", "-r", "backend/", "-ll", "-f", "json"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        # bandit は問題あり=1, なし=0, エラー=2 を返す
        raw = proc.stdout or proc.stderr or "{}"
        data = json.loads(raw)

        results = data.get("results", [])
        high = sum(1 for r in results if r.get("issue_severity") == "HIGH")
        medium = sum(1 for r in results if r.get("issue_severity") == "MEDIUM")
        low = sum(1 for r in results if r.get("issue_severity") == "LOW")

        audit_log.record(
            operation="security_bandit_scan",
            user_id=current_user.user_id,
            target="backend/",
            status="success",
            details={"high": high, "medium": medium, "low": low},
        )
        return BanditStatusResponse(
            status="success",
            high=high,
            medium=medium,
            low=low,
            total_issues=len(results),
            scanned=True,
        )
    except subprocess.TimeoutExpired:
        logger.error("bandit scan timed out")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="bandit スキャンがタイムアウトしました",
        )
    except FileNotFoundError:
        # bandit がインストールされていない場合
        return BanditStatusResponse(
            status="unavailable",
            scanned=False,
            error="bandit がインストールされていません",
        )
    except json.JSONDecodeError as e:
        logger.error("bandit JSON parse error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"bandit 出力解析エラー: {e}",
        )
    except Exception as e:
        logger.error("Unexpected error in get_bandit_status: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )
