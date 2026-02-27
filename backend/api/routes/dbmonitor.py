"""
データベース監視 API エンドポイント

提供エンドポイント:
  GET /api/dbmonitor/{db_type}/status      - DBサービス状態
  GET /api/dbmonitor/{db_type}/processes   - プロセス/アクティビティ一覧
  GET /api/dbmonitor/{db_type}/databases   - データベース一覧
  GET /api/dbmonitor/{db_type}/connections - 接続一覧（PostgreSQL）
  GET /api/dbmonitor/{db_type}/variables   - 変数・設定（MySQL）
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field

from ...core import require_permission, sudo_wrapper
from ...core.audit_log import audit_log
from ...core.auth import TokenData
from ...core.sudo_wrapper import SudoWrapperError
from ._utils import parse_wrapper_result

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dbmonitor", tags=["dbmonitor"])

# 許可するDBタイプ
_ALLOWED_DB_TYPES = ("mysql", "postgresql")


def _validate_db_type(db_type: str) -> str:
    """DBタイプのバリデーション"""
    if db_type not in _ALLOWED_DB_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"DB type not allowed: {db_type}. Must be one of: {', '.join(_ALLOWED_DB_TYPES)}",
        )
    return db_type


# ===================================================================
# レスポンスモデル
# ===================================================================


class DBStatusResponse(BaseModel):
    """DB 状態レスポンス"""

    status: str
    db_type: str = ""
    running: bool = False
    version: str = ""
    message: Optional[str] = None
    data: Any = None
    timestamp: str = ""


class DBListResponse(BaseModel):
    """DB リスト系レスポンス（プロセス・DB一覧・接続など）"""

    status: str
    db_type: str = ""
    data: Any = None
    count: int = 0
    message: Optional[str] = None
    timestamp: str = ""


# ===================================================================
# エンドポイント
# ===================================================================


@router.get(
    "/{db_type}/status",
    response_model=DBStatusResponse,
    summary="DBサービス状態",
    description="MySQL または PostgreSQL のサービス状態・バージョン・接続数を取得します",
)
async def get_db_status(
    db_type: str = Path(..., pattern="^(mysql|postgresql)$"),
    current_user: TokenData = Depends(require_permission("read:servers")),
) -> DBStatusResponse:
    """DB サービス状態を取得する"""
    try:
        result = sudo_wrapper.get_db_status(db_type)
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="dbmonitor_status_read",
            user_id=current_user.user_id,
            target=db_type,
            status="success",
        )
        return DBStatusResponse(
            status=parsed.get("status", "ok"),
            db_type=parsed.get("db_type", db_type),
            running=parsed.get("running", False),
            version=parsed.get("version", ""),
            message=parsed.get("message"),
            data=parsed,
            timestamp=parsed.get("timestamp", ""),
        )
    except (SudoWrapperError, ValueError) as e:
        logger.error("DB status error for %s: %s", db_type, e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"DB状態取得エラー ({db_type}): {e}",
        )


@router.get(
    "/{db_type}/processes",
    response_model=DBListResponse,
    summary="DBプロセス/アクティビティ一覧",
    description="MySQL の SHOW PROCESSLIST / PostgreSQL の pg_stat_activity を取得します",
)
async def get_db_processes(
    db_type: str = Path(..., pattern="^(mysql|postgresql)$"),
    current_user: TokenData = Depends(require_permission("read:servers")),
) -> DBListResponse:
    """DB プロセス一覧を取得する"""
    try:
        result = sudo_wrapper.get_db_processlist(db_type)
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="dbmonitor_processes_read",
            user_id=current_user.user_id,
            target=db_type,
            status="success",
        )
        data_key = "activity" if db_type == "postgresql" else "processes"
        items = parsed.get(data_key, parsed.get("processes", []))
        return DBListResponse(
            status=parsed.get("status", "ok"),
            db_type=db_type,
            data=items,
            count=parsed.get("count", len(items) if isinstance(items, list) else 0),
            message=parsed.get("message"),
            timestamp=parsed.get("timestamp", ""),
        )
    except (SudoWrapperError, ValueError) as e:
        logger.error("DB processlist error for %s: %s", db_type, e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"DBプロセス取得エラー ({db_type}): {e}",
        )


@router.get(
    "/{db_type}/databases",
    response_model=DBListResponse,
    summary="データベース一覧",
    description="MySQL/PostgreSQL のデータベース一覧を取得します",
)
async def get_db_databases(
    db_type: str = Path(..., pattern="^(mysql|postgresql)$"),
    current_user: TokenData = Depends(require_permission("read:servers")),
) -> DBListResponse:
    """データベース一覧を取得する"""
    try:
        result = sudo_wrapper.get_db_databases(db_type)
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="dbmonitor_databases_read",
            user_id=current_user.user_id,
            target=db_type,
            status="success",
        )
        dbs = parsed.get("databases", [])
        return DBListResponse(
            status=parsed.get("status", "ok"),
            db_type=db_type,
            data=dbs,
            count=parsed.get("count", len(dbs) if isinstance(dbs, list) else 0),
            message=parsed.get("message"),
            timestamp=parsed.get("timestamp", ""),
        )
    except (SudoWrapperError, ValueError) as e:
        logger.error("DB databases error for %s: %s", db_type, e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"データベース一覧取得エラー ({db_type}): {e}",
        )


@router.get(
    "/{db_type}/connections",
    response_model=DBListResponse,
    summary="DB接続一覧",
    description="PostgreSQL の pg_stat_activity からアクティブ接続一覧を取得します（MySQL では processlist を返します）",
)
async def get_db_connections(
    db_type: str = Path(..., pattern="^(mysql|postgresql)$"),
    current_user: TokenData = Depends(require_permission("read:servers")),
) -> DBListResponse:
    """DB 接続一覧を取得する"""
    try:
        result = sudo_wrapper.get_db_connections(db_type)
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="dbmonitor_connections_read",
            user_id=current_user.user_id,
            target=db_type,
            status="success",
        )
        conns = parsed.get("connections", parsed.get("processes", []))
        return DBListResponse(
            status=parsed.get("status", "ok"),
            db_type=db_type,
            data=conns,
            count=parsed.get("count", len(conns) if isinstance(conns, list) else 0),
            message=parsed.get("message"),
            timestamp=parsed.get("timestamp", ""),
        )
    except (SudoWrapperError, ValueError) as e:
        logger.error("DB connections error for %s: %s", db_type, e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"DB接続一覧取得エラー ({db_type}): {e}",
        )


@router.get(
    "/{db_type}/variables",
    response_model=DBListResponse,
    summary="DB変数・設定",
    description="MySQL の SHOW VARIABLES / PostgreSQL の状態情報を取得します",
)
async def get_db_variables(
    db_type: str = Path(..., pattern="^(mysql|postgresql)$"),
    current_user: TokenData = Depends(require_permission("read:servers")),
) -> DBListResponse:
    """DB 変数・設定を取得する"""
    try:
        result = sudo_wrapper.get_db_variables(db_type)
        parsed = parse_wrapper_result(result)
        audit_log.record(
            operation="dbmonitor_variables_read",
            user_id=current_user.user_id,
            target=db_type,
            status="success",
        )
        return DBListResponse(
            status=parsed.get("status", "ok"),
            db_type=db_type,
            data=parsed.get("variables", parsed),
            count=0,
            message=parsed.get("message"),
            timestamp=parsed.get("timestamp", ""),
        )
    except (SudoWrapperError, ValueError) as e:
        logger.error("DB variables error for %s: %s", db_type, e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"DB変数取得エラー ({db_type}): {e}",
        )
