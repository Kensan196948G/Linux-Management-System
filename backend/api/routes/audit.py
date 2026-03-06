"""
監査ログ API エンドポイント

提供エンドポイント:
  GET /api/audit/logs           - 監査ログ一覧（ページネーション付き）
  GET /api/audit/logs/export    - CSV/JSONエクスポート

アクセス制限:
  - Viewer: アクセス不可（403）
  - Operator/Approver: 自分のログのみ閲覧可
  - Admin: 全ログ閲覧可
"""

import csv
import io
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ...core import require_permission
from ...core.audit_log import audit_log
from ...core.auth import TokenData

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit", tags=["audit"])


# ===================================================================
# レスポンスモデル
# ===================================================================


class AuditLogEntry(BaseModel):
    """監査ログエントリ"""

    timestamp: str
    operation: str
    user_id: str
    target: str
    status: str
    details: dict = Field(default_factory=dict)


class AuditLogsResponse(BaseModel):
    """監査ログ一覧レスポンス"""

    entries: List[AuditLogEntry]
    total: int
    page: int
    per_page: int
    has_next: bool


# ===================================================================
# エンドポイント
# ===================================================================


@router.get(
    "/logs",
    response_model=AuditLogsResponse,
    summary="監査ログ一覧",
    description="操作ログを取得します。AdminはすべてのログをOperator/Approverは自分のログのみ閲覧可能。",
)
async def list_audit_logs(
    page: int = Query(default=1, ge=1, description="ページ番号"),
    per_page: int = Query(default=50, ge=1, le=200, description="1ページあたり件数"),
    user_id_filter: Optional[str] = Query(default=None, alias="user_id", description="ユーザーIDフィルタ"),
    operation_filter: Optional[str] = Query(default=None, alias="operation", description="操作種別フィルタ"),
    status_filter: Optional[str] = Query(default=None, alias="status", description="ステータスフィルタ"),
    start_date: Optional[str] = Query(default=None, description="開始日時 (ISO 8601)"),
    end_date: Optional[str] = Query(default=None, description="終了日時 (ISO 8601)"),
    current_user: TokenData = Depends(require_permission("read:audit")),
) -> AuditLogsResponse:
    """監査ログを取得する（RBAC適用）"""
    try:
        start_dt: Optional[datetime] = None
        end_dt: Optional[datetime] = None
        if start_date:
            start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        if end_date:
            end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))

        # page * per_page 分取得してページネーション
        fetch_limit = page * per_page
        all_entries = audit_log.query(
            user_role=current_user.role,
            requesting_user_id=current_user.user_id,
            start_date=start_dt,
            end_date=end_dt,
            user_id=user_id_filter,
            operation=operation_filter,
            status=status_filter,
            limit=fetch_limit + 1,  # has_next 判定用に+1
        )

        total_fetched = len(all_entries)
        has_next = total_fetched > fetch_limit
        if has_next:
            all_entries = all_entries[:fetch_limit]

        # ページスライス
        offset = (page - 1) * per_page
        page_entries = all_entries[offset : offset + per_page]

        return AuditLogsResponse(
            entries=[AuditLogEntry(**e) for e in page_entries],
            total=total_fetched if not has_next else fetch_limit,
            page=page,
            per_page=per_page,
            has_next=has_next,
        )

    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="監査ログへのアクセス権限がありません",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"日時フォーマットエラー: {e}",
        )
    except Exception as e:
        logger.error("Unexpected error in list_audit_logs: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内部エラー: {e}",
        )


@router.get(
    "/operations",
    summary="監査ログ操作種別一覧",
    description="監査ログに記録されている操作種別の一覧を返します。",
)
async def list_audit_operations(
    current_user: TokenData = Depends(require_permission("read:audit")),
) -> dict:
    """監査ログに存在する操作種別一覧を返す。"""
    try:
        entries = audit_log.query(
            user_role=current_user.role,
            requesting_user_id=current_user.user_id,
            limit=10000,
        )
        ops = sorted({e.get("operation", "") for e in entries if e.get("operation")})
        return {"status": "success", "operations": ops}
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="監査ログへのアクセス権限がありません",
        )
    except Exception as e:
        logger.error("Unexpected error in list_audit_operations: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"操作種別一覧の取得に失敗しました: {e}",
        )


@router.get(
    "/stats",
    summary="監査ログ統計",
    description="監査ログの統計情報（総件数・操作別件数・ユーザー別件数）を返します。",
)
async def get_audit_stats(
    current_user: TokenData = Depends(require_permission("read:audit")),
) -> dict:
    """監査ログの統計情報を返す（総件数・操作別件数・ユーザー別件数）。"""
    try:
        entries = audit_log.query(
            user_role=current_user.role,
            requesting_user_id=current_user.user_id,
            limit=10000,
        )
        op_counts: dict = {}
        user_counts: dict = {}
        status_counts: dict = {}
        for entry in entries:
            op = entry.get("operation", "unknown")
            uid = entry.get("user_id", "unknown")
            st = entry.get("status", "unknown")
            op_counts[op] = op_counts.get(op, 0) + 1
            user_counts[uid] = user_counts.get(uid, 0) + 1
            status_counts[st] = status_counts.get(st, 0) + 1

        # Operator/Approverはユーザー別件数を自分のみに制限
        if current_user.role in ("Operator", "Approver"):
            user_counts = {k: v for k, v in user_counts.items() if k == current_user.user_id}

        return {
            "status": "success",
            "total": len(entries),
            "by_operation": op_counts,
            "by_status": status_counts,
            "by_user": user_counts if current_user.role in ("Admin", "Operator", "Approver") else {},
        }
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="監査ログへのアクセス権限がありません",
        )
    except Exception as e:
        logger.error("Unexpected error in get_audit_stats: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"統計情報の取得に失敗しました: {e}",
        )


@router.get(
    "/logs/export",
    summary="監査ログエクスポート",
    description="監査ログをCSVまたはJSONでエクスポートします。Adminのみ使用可能。",
    responses={
        200: {
            "content": {
                "text/csv": {},
                "application/json": {},
            }
        }
    },
)
async def export_audit_logs(
    format: str = Query(default="csv", description="エクスポート形式 (csv または json)"),
    user_id_filter: Optional[str] = Query(default=None, alias="user_id"),
    operation_filter: Optional[str] = Query(default=None, alias="operation"),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    start_date: Optional[str] = Query(default=None, description="開始日時 (ISO 8601)"),
    end_date: Optional[str] = Query(default=None, description="終了日時 (ISO 8601)"),
    current_user: TokenData = Depends(require_permission("export:audit")),
) -> Response:
    """監査ログをCSV/JSONでエクスポート（Adminのみ）"""
    if format not in ("csv", "json"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="format は 'csv' または 'json' を指定してください",
        )
    try:
        start_dt: Optional[datetime] = None
        end_dt: Optional[datetime] = None
        if start_date:
            start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        if end_date:
            end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))

        entries = audit_log.query(
            user_role=current_user.role,
            requesting_user_id=current_user.user_id,
            start_date=start_dt,
            end_date=end_dt,
            user_id=user_id_filter,
            operation=operation_filter,
            status=status_filter,
            limit=10000,
        )

        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        if format == "json":
            content = json.dumps(entries, ensure_ascii=False, indent=2)
            return Response(
                content=content,
                media_type="application/json",
                headers={
                    "Content-Disposition": f"attachment; filename=audit_export_{timestamp_str}.json"
                },
            )
        else:
            # CSV
            output = io.StringIO()
            fieldnames = ["timestamp", "operation", "user_id", "target", "status", "details"]
            writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for entry in entries:
                row = {**entry}
                if isinstance(row.get("details"), dict):
                    row["details"] = json.dumps(row["details"], ensure_ascii=False)
                writer.writerow(row)

            return Response(
                content=output.getvalue(),
                media_type="text/csv; charset=utf-8",
                headers={
                    "Content-Disposition": f"attachment; filename=audit_export_{timestamp_str}.csv"
                },
            )

    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="エクスポート権限がありません",
        )
    except Exception as e:
        logger.error("Unexpected error in export_audit_logs: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"エクスポートエラー: {e}",
        )
