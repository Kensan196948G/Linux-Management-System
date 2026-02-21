"""
承認ワークフローサービス

承認リクエストの作成・承認・拒否・実行を管理するビジネスロジック層
"""

import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import aiosqlite

from .audit_log import AuditLog
from .config import settings

logger = logging.getLogger(__name__)


# ===================================================================
# 定数・設定
# ===================================================================

# HMAC 署名用秘密鍵（環境変数から取得、デフォルトは開発環境用）
HMAC_SECRET_KEY = getattr(
    settings, "APPROVAL_HMAC_SECRET", "dev-approval-secret-key-change-in-production"
)

# 承認履歴の許可アクション
ALLOWED_ACTIONS = {
    "created",
    "approved",
    "rejected",
    "expired",
    "executed",
    "execution_failed",
    "cancelled",
}

# ステータスの許可値
ALLOWED_STATUSES = {
    "pending",
    "approved",
    "rejected",
    "expired",
    "executed",
    "execution_failed",
    "cancelled",
}

# 特殊文字検証（CLAUDE.md のセキュリティ原則準拠）
FORBIDDEN_CHARS = [
    ";",
    "|",
    "&",
    "$",
    "(",
    ")",
    "`",
    ">",
    "<",
    "*",
    "?",
    "{",
    "}",
    "[",
    "]",
]


# ===================================================================
# セキュリティユーティリティ
# ===================================================================


def compute_history_signature(
    approval_request_id: str,
    action: str,
    actor_id: str,
    timestamp: str,
    details: Optional[dict],
) -> str:
    """
    承認履歴レコードの HMAC-SHA256 署名を計算

    Args:
        approval_request_id: リクエストID
        action: アクション種別
        actor_id: 実行者ID
        timestamp: タイムスタンプ (ISO 8601)
        details: 追加情報

    Returns:
        HMAC-SHA256 署名（16進数文字列、64文字）
    """
    # 署名対象データを正規化
    sign_data = {
        "approval_request_id": approval_request_id,
        "action": action,
        "actor_id": actor_id,
        "timestamp": timestamp,
        "details": details or {},
    }

    # JSON の正規化（キーソート、ASCII エスケープなし）
    canonical = json.dumps(sign_data, sort_keys=True, ensure_ascii=False)

    # HMAC-SHA256 署名の計算
    signature = hmac.new(
        HMAC_SECRET_KEY.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return signature


def verify_history_signature(record: dict) -> bool:
    """
    承認履歴レコードの署名を検証

    Args:
        record: 承認履歴レコード

    Returns:
        署名が正しい場合 True
    """
    stored_signature = record.get("signature", "")

    computed = compute_history_signature(
        approval_request_id=record["approval_request_id"],
        action=record["action"],
        actor_id=record["actor_id"],
        timestamp=record["timestamp"],
        details=record.get("details"),
    )

    return hmac.compare_digest(stored_signature, computed)


def validate_payload_values(payload: dict) -> None:
    """
    ペイロード内の全文字列値に対して特殊文字チェックを実行

    Args:
        payload: 検証対象のペイロード

    Raises:
        ValueError: 禁止文字が含まれる場合
    """
    for key, value in payload.items():
        if isinstance(value, str):
            for char in FORBIDDEN_CHARS:
                if char in value:
                    raise ValueError(
                        f"Forbidden character '{char}' detected in payload field '{key}'"
                    )


# ===================================================================
# ApprovalService クラス
# ===================================================================


class ApprovalService:
    """承認ワークフローサービス"""

    def __init__(self, db_path: str):
        """
        Args:
            db_path: SQLite データベースファイルパス
        """
        self.db_path = db_path
        self.audit_log = AuditLog()  # デフォルトのログディレクトリを使用

    # ===============================================================
    # 0. データベース初期化
    # ===============================================================

    async def initialize_db(self) -> None:
        """
        承認ワークフロー用テーブルを作成（DDL実行）

        approval-schema.sql の CREATE TABLE / INDEX / VIEW を実行する。
        INSERT OR IGNORE のため既存データは影響を受けない。
        """
        schema_path = (
            Path(__file__).parent.parent.parent
            / "docs"
            / "database"
            / "approval-schema.sql"
        )

        if not schema_path.exists():
            logger.error(f"Schema file not found: {schema_path}")
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        schema_sql = schema_path.read_text(encoding="utf-8")

        # DB ファイルの親ディレクトリが存在しない場合は自動作成
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(schema_sql)
            await db.commit()

        logger.info("Approval workflow database initialized successfully")

    # ===============================================================
    # 1. 承認リクエスト作成
    # ===============================================================

    async def create_request(
        self,
        request_type: str,
        payload: dict,
        reason: str,
        requester_id: str,
        requester_name: str,
        requester_role: str,
    ) -> dict:
        """
        承認リクエストを作成

        Args:
            request_type: 操作種別（policies に定義済みの値）
            payload: 操作パラメータ
            reason: 申請理由
            requester_id: 申請者ユーザーID
            requester_name: 申請者表示名
            requester_role: 申請者ロール

        Returns:
            作成された承認リクエスト

        Raises:
            ValueError: バリデーションエラー
            LookupError: operation_type が policies に存在しない
        """
        # 1. ペイロードのバリデーション
        validate_payload_values(payload)

        # 2. operation_type が policies に存在することを確認
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM approval_policies WHERE operation_type = ?",
                (request_type,),
            ) as cursor:
                policy = await cursor.fetchone()

            if not policy:
                raise LookupError(
                    f"Invalid request_type: {request_type}. "
                    "Operation type must be defined in approval_policies."
                )

            # 3. 承認リクエスト作成
            request_id = str(uuid.uuid4())
            created_at = datetime.utcnow()
            expires_at = created_at + timedelta(hours=policy["timeout_hours"])

            await db.execute(
                """
                INSERT INTO approval_requests (
                    id, request_type, requester_id, requester_name,
                    request_payload, reason, status, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    request_type,
                    requester_id,
                    requester_name,
                    json.dumps(payload, ensure_ascii=False),
                    reason,
                    "pending",
                    created_at.isoformat(),
                    expires_at.isoformat(),
                ),
            )
            await db.commit()

            # 4. 承認履歴に "created" を記録
            await self._add_history(
                db=db,
                approval_request_id=request_id,
                action="created",
                actor_id=requester_id,
                actor_name=requester_name,
                actor_role=requester_role,
                previous_status=None,
                new_status="pending",
                details=None,
            )
            await db.commit()

            # 5. 監査ログ記録
            self.audit_log.record(
                operation="approval_request_created",
                user_id=requester_id,
                target=f"{request_type}:{request_id}",
                status="success",
                details={
                    "request_id": request_id,
                    "request_type": request_type,
                    "reason": reason,
                },
            )

            return {
                "request_id": request_id,
                "request_type": request_type,
                "status": "pending",
                "created_at": created_at.isoformat(),
                "expires_at": expires_at.isoformat(),
                "timeout_hours": policy["timeout_hours"],
                "risk_level": policy["risk_level"],
            }

    # ===============================================================
    # 2. 承認実行
    # ===============================================================

    async def approve_request(
        self,
        request_id: str,
        approver_id: str,
        approver_name: str,
        approver_role: str,
        comment: Optional[str] = None,
    ) -> dict:
        """
        承認リクエストを承認

        Args:
            request_id: リクエストID
            approver_id: 承認者ユーザーID
            approver_name: 承認者表示名
            approver_role: 承認者ロール
            comment: 承認コメント（任意）

        Returns:
            承認結果

        Raises:
            LookupError: リクエストが存在しない
            ValueError: 承認不可（自己承認、ステータス不正、期限切れ等）
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # 1. リクエスト取得
            async with db.execute(
                "SELECT * FROM approval_requests WHERE id = ?",
                (request_id,),
            ) as cursor:
                request = await cursor.fetchone()

            if not request:
                raise LookupError(f"Approval request not found: {request_id}")

            # 2. 自己承認禁止チェック
            if request["requester_id"] == approver_id:
                raise ValueError(
                    "Self-approval is prohibited. "
                    "A different Approver/Admin must approve this request."
                )

            # 3. ステータスチェック（pending のみ承認可能）
            if request["status"] != "pending":
                raise ValueError(
                    f"Cannot approve: request status is '{request['status']}'. "
                    "Only 'pending' requests can be approved."
                )

            # 4. 期限切れチェック
            expires_at = datetime.fromisoformat(request["expires_at"])
            if datetime.utcnow() > expires_at:
                # 期限切れの場合、自動的に expired に変更
                await self._expire_request(db, request, request_id)
                await db.commit()
                raise ValueError(
                    f"Cannot approve: request has expired at {request['expires_at']}"
                )

            # 5. 承認実行
            approved_at = datetime.utcnow()
            await db.execute(
                """
                UPDATE approval_requests
                SET status = 'approved',
                    approved_by = ?,
                    approved_by_name = ?,
                    approved_at = ?
                WHERE id = ?
                """,
                (approver_id, approver_name, approved_at.isoformat(), request_id),
            )
            await db.commit()

            # 6. 承認履歴に "approved" を記録
            details = {"comment": comment} if comment else None
            await self._add_history(
                db=db,
                approval_request_id=request_id,
                action="approved",
                actor_id=approver_id,
                actor_name=approver_name,
                actor_role=approver_role,
                previous_status="pending",
                new_status="approved",
                details=details,
            )
            await db.commit()

            # 7. 監査ログ記録
            self.audit_log.record(
                operation="approval_approved",
                user_id=approver_id,
                target=f"{request['request_type']}:{request_id}",
                status="success",
                details={
                    "request_id": request_id,
                    "requester_id": request["requester_id"],
                    "comment": comment,
                },
            )

            # 8. auto_execute チェック
            async with db.execute(
                "SELECT auto_execute FROM approval_policies WHERE operation_type = ?",
                (request["request_type"],),
            ) as cursor:
                policy = await cursor.fetchone()

            auto_execute = bool(policy["auto_execute"]) if policy else False

            result = {
                "request_id": request_id,
                "approved_by": approver_id,
                "approved_by_name": approver_name,
                "approved_at": approved_at.isoformat(),
                "auto_executed": False,
            }

            # 9. 自動実行（v0.4 予定 - 今回はスタブ）
            if auto_execute:
                # TODO: 自動実行ロジック実装（v0.4）
                logger.info(
                    f"Auto-execute is enabled for {request_id}, but not implemented yet (v0.4)"
                )

            return result

    # ===============================================================
    # 3. 拒否実行
    # ===============================================================

    async def reject_request(
        self,
        request_id: str,
        approver_id: str,
        approver_name: str,
        approver_role: str,
        rejection_reason: str,
    ) -> dict:
        """
        承認リクエストを拒否

        Args:
            request_id: リクエストID
            approver_id: 承認者ユーザーID
            approver_name: 承認者表示名
            approver_role: 承認者ロール
            rejection_reason: 拒否理由

        Returns:
            拒否結果

        Raises:
            LookupError: リクエストが存在しない
            ValueError: 拒否不可（ステータス不正等）
        """
        # 拒否理由の FORBIDDEN_CHARS チェック
        for char in FORBIDDEN_CHARS:
            if char in rejection_reason:
                raise ValueError(
                    f"Forbidden character '{char}' detected in rejection_reason"
                )

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # 1. リクエスト取得
            async with db.execute(
                "SELECT * FROM approval_requests WHERE id = ?",
                (request_id,),
            ) as cursor:
                request = await cursor.fetchone()

            if not request:
                raise LookupError(f"Approval request not found: {request_id}")

            # 2. ステータスチェック（pending のみ拒否可能）
            if request["status"] != "pending":
                raise ValueError(
                    f"Cannot reject: request status is '{request['status']}'. "
                    "Only 'pending' requests can be rejected."
                )

            # 3. 拒否実行
            rejected_at = datetime.utcnow()
            await db.execute(
                """
                UPDATE approval_requests
                SET status = 'rejected',
                    approved_by = ?,
                    approved_by_name = ?,
                    approved_at = ?,
                    rejection_reason = ?
                WHERE id = ?
                """,
                (
                    approver_id,
                    approver_name,
                    rejected_at.isoformat(),
                    rejection_reason,
                    request_id,
                ),
            )
            await db.commit()

            # 4. 承認履歴に "rejected" を記録
            await self._add_history(
                db=db,
                approval_request_id=request_id,
                action="rejected",
                actor_id=approver_id,
                actor_name=approver_name,
                actor_role=approver_role,
                previous_status="pending",
                new_status="rejected",
                details={"reason": rejection_reason},
            )
            await db.commit()

            # 5. 監査ログ記録
            self.audit_log.record(
                operation="approval_rejected",
                user_id=approver_id,
                target=f"{request['request_type']}:{request_id}",
                status="success",
                details={
                    "request_id": request_id,
                    "requester_id": request["requester_id"],
                    "rejection_reason": rejection_reason,
                },
            )

            return {
                "request_id": request_id,
                "rejected_by": approver_id,
                "rejected_by_name": approver_name,
                "rejected_at": rejected_at.isoformat(),
                "rejection_reason": rejection_reason,
            }

    # ===============================================================
    # 4. リクエスト詳細取得
    # ===============================================================

    async def get_request(self, request_id: str) -> dict:
        """
        承認リクエストの詳細を取得

        Args:
            request_id: リクエストID

        Returns:
            リクエスト詳細（履歴を含む）

        Raises:
            LookupError: リクエストが存在しない
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # 1. リクエスト取得
            async with db.execute(
                """
                SELECT r.*, p.description AS request_type_description, p.risk_level
                FROM approval_requests r
                JOIN approval_policies p ON r.request_type = p.operation_type
                WHERE r.id = ?
                """,
                (request_id,),
            ) as cursor:
                request = await cursor.fetchone()

            if not request:
                raise LookupError(f"Approval request not found: {request_id}")

            # 2. 承認履歴取得
            async with db.execute(
                """
                SELECT * FROM approval_history
                WHERE approval_request_id = ?
                ORDER BY timestamp ASC
                """,
                (request_id,),
            ) as cursor:
                history_rows = await cursor.fetchall()

            history = []
            for row in history_rows:
                history.append(
                    {
                        "action": row["action"],
                        "actor_id": row["actor_id"],
                        "actor_name": row["actor_name"],
                        "actor_role": row["actor_role"],
                        "timestamp": row["timestamp"],
                        "details": (
                            json.loads(row["details"]) if row["details"] else None
                        ),
                    }
                )

            # 3. 結果組み立て
            return {
                "id": request["id"],
                "request_type": request["request_type"],
                "request_type_description": request["request_type_description"],
                "risk_level": request["risk_level"],
                "requester_id": request["requester_id"],
                "requester_name": request["requester_name"],
                "request_payload": json.loads(request["request_payload"]),
                "reason": request["reason"],
                "status": request["status"],
                "created_at": request["created_at"],
                "expires_at": request["expires_at"],
                "approved_by": request["approved_by"],
                "approved_by_name": request["approved_by_name"],
                "approved_at": request["approved_at"],
                "rejection_reason": request["rejection_reason"],
                "execution_result": (
                    json.loads(request["execution_result"])
                    if request["execution_result"]
                    else None
                ),
                "executed_at": request["executed_at"],
                "history": history,
            }

    # ===============================================================
    # 5. 承認待ちリクエスト一覧取得
    # ===============================================================

    async def list_pending_requests(
        self,
        request_type: Optional[str] = None,
        requester_id: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "asc",
        page: int = 1,
        per_page: int = 20,
    ) -> dict:
        """
        承認待ちリクエストの一覧を取得

        Args:
            request_type: 操作種別フィルタ（任意）
            requester_id: 申請者IDフィルタ（任意）
            sort_by: ソートキー
            sort_order: ソート順（asc/desc）
            page: ページ番号
            per_page: 1ページあたり件数

        Returns:
            承認待ちリクエスト一覧
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # 1. WHERE 句の構築
            where_clauses = ["r.status = 'pending'", "r.expires_at > datetime('now')"]
            params = []

            if request_type:
                where_clauses.append("r.request_type = ?")
                params.append(request_type)

            if requester_id:
                where_clauses.append("r.requester_id = ?")
                params.append(requester_id)

            where_sql = " AND ".join(where_clauses)

            # 2. ソート順の検証
            allowed_sort_keys = {"created_at", "expires_at", "request_type"}
            if sort_by not in allowed_sort_keys:
                sort_by = "created_at"

            if sort_order.lower() not in {"asc", "desc"}:
                sort_order = "asc"

            # 3. 総件数取得
            count_query = (
                f"SELECT COUNT(*) as total FROM approval_requests r WHERE {where_sql}"
            )
            async with db.execute(count_query, params) as cursor:
                total = (await cursor.fetchone())["total"]

            # 4. リクエスト一覧取得
            offset = (page - 1) * per_page
            query = f"""
                SELECT
                    r.*,
                    p.description AS request_type_description,
                    p.risk_level,
                    ROUND((JULIANDAY(r.expires_at) - JULIANDAY('now')) * 24, 1) AS remaining_hours
                FROM approval_requests r
                JOIN approval_policies p ON r.request_type = p.operation_type
                WHERE {where_sql}
                ORDER BY r.{sort_by} {sort_order}
                LIMIT ? OFFSET ?
            """

            async with db.execute(query, params + [per_page, offset]) as cursor:
                rows = await cursor.fetchall()

            requests = []
            for row in rows:
                payload = json.loads(row["request_payload"])
                # ペイロードのサマリー作成（最大3フィールド）
                payload_summary = ", ".join(
                    f"{k}={v}" for k, v in list(payload.items())[:3]
                )

                requests.append(
                    {
                        "id": row["id"],
                        "request_type": row["request_type"],
                        "request_type_description": row["request_type_description"],
                        "risk_level": row["risk_level"],
                        "requester_id": row["requester_id"],
                        "requester_name": row["requester_name"],
                        "reason": row["reason"],
                        "created_at": row["created_at"],
                        "expires_at": row["expires_at"],
                        "remaining_hours": row["remaining_hours"],
                        "payload_summary": payload_summary,
                    }
                )

            return {
                "total": total,
                "page": page,
                "per_page": per_page,
                "requests": requests,
            }

    # ===============================================================
    # 6. 自分の申請一覧取得
    # ===============================================================

    async def list_my_requests(
        self,
        requester_id: str,
        status: Optional[str] = None,
        request_type: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> dict:
        """
        自分の承認リクエストの一覧を取得

        Args:
            requester_id: 申請者ユーザーID
            status: ステータスフィルタ（任意）
            request_type: 操作種別フィルタ（任意）
            page: ページ番号
            per_page: 1ページあたり件数

        Returns:
            自分の申請一覧
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # 1. WHERE 句の構築
            where_clauses = ["r.requester_id = ?"]
            params = [requester_id]

            if status:
                where_clauses.append("r.status = ?")
                params.append(status)

            if request_type:
                where_clauses.append("r.request_type = ?")
                params.append(request_type)

            where_sql = " AND ".join(where_clauses)

            # 2. 総件数取得
            count_query = (
                f"SELECT COUNT(*) as total FROM approval_requests r WHERE {where_sql}"
            )
            async with db.execute(count_query, params) as cursor:
                total = (await cursor.fetchone())["total"]

            # 3. リクエスト一覧取得
            offset = (page - 1) * per_page
            query = f"""
                SELECT
                    r.*,
                    p.description AS request_type_description,
                    p.risk_level
                FROM approval_requests r
                JOIN approval_policies p ON r.request_type = p.operation_type
                WHERE {where_sql}
                ORDER BY r.created_at DESC
                LIMIT ? OFFSET ?
            """

            async with db.execute(query, params + [per_page, offset]) as cursor:
                rows = await cursor.fetchall()

            requests = []
            for row in rows:
                requests.append(
                    {
                        "id": row["id"],
                        "request_type": row["request_type"],
                        "request_type_description": row["request_type_description"],
                        "risk_level": row["risk_level"],
                        "status": row["status"],
                        "reason": row["reason"],
                        "created_at": row["created_at"],
                        "expires_at": row["expires_at"],
                        "approved_by_name": row["approved_by_name"],
                        "approved_at": row["approved_at"],
                        "rejection_reason": row["rejection_reason"],
                    }
                )

            return {
                "total": total,
                "page": page,
                "per_page": per_page,
                "requests": requests,
            }

    # ===============================================================
    # 7. キャンセル
    # ===============================================================

    async def cancel_request(
        self,
        request_id: str,
        requester_id: str,
        requester_name: str,
        requester_role: str,
        reason: Optional[str] = None,
    ) -> dict:
        """
        承認リクエストをキャンセル

        Args:
            request_id: リクエストID
            requester_id: 申請者ユーザーID
            requester_name: 申請者表示名
            requester_role: 申請者ロール
            reason: キャンセル理由（任意）

        Returns:
            キャンセル結果

        Raises:
            LookupError: リクエストが存在しない
            ValueError: キャンセル不可（他者のリクエスト、ステータス不正等）
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # 1. リクエスト取得
            async with db.execute(
                "SELECT * FROM approval_requests WHERE id = ?",
                (request_id,),
            ) as cursor:
                request = await cursor.fetchone()

            if not request:
                raise LookupError(f"Approval request not found: {request_id}")

            # 2. 申請者本人チェック
            if request["requester_id"] != requester_id:
                raise ValueError("Only the requester can cancel this request.")

            # 3. ステータスチェック（pending のみキャンセル可能）
            if request["status"] != "pending":
                raise ValueError(
                    f"Cannot cancel: request status is '{request['status']}'. "
                    "Only 'pending' requests can be cancelled."
                )

            # 4. キャンセル実行
            cancelled_at = datetime.utcnow()
            await db.execute(
                "UPDATE approval_requests SET status = 'cancelled' WHERE id = ?",
                (request_id,),
            )
            await db.commit()

            # 5. 承認履歴に "cancelled" を記録
            details = {"reason": reason} if reason else None
            await self._add_history(
                db=db,
                approval_request_id=request_id,
                action="cancelled",
                actor_id=requester_id,
                actor_name=requester_name,
                actor_role=requester_role,
                previous_status="pending",
                new_status="cancelled",
                details=details,
            )
            await db.commit()

            # 6. 監査ログ記録
            self.audit_log.record(
                operation="approval_cancelled",
                user_id=requester_id,
                target=f"{request['request_type']}:{request_id}",
                status="success",
                details={"request_id": request_id, "reason": reason},
            )

            return {
                "request_id": request_id,
                "cancelled_at": cancelled_at.isoformat(),
            }

    # ===============================================================
    # 8. 期限切れリクエストの自動処理
    # ===============================================================

    async def expire_old_requests(self) -> int:
        """
        期限切れリクエストを自動的に expired に変更

        Returns:
            処理件数
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # 1. 期限切れリクエスト取得
            # Python isoformat() (T区切り) と SQLite datetime() (空白区切り) の
            # 形式差異を回避するため、Python 側で現在時刻を生成して渡す
            now_iso = datetime.utcnow().isoformat()
            async with db.execute(
                """
                SELECT * FROM approval_requests
                WHERE status = 'pending'
                AND expires_at < ?
                """,
                (now_iso,),
            ) as cursor:
                expired_requests = await cursor.fetchall()

            count = 0
            for request in expired_requests:
                await self._expire_request(db, request, request["id"])
                count += 1

            await db.commit()

            if count > 0:
                logger.info(f"Expired {count} approval requests")

            return count

    # ===============================================================
    # 内部メソッド
    # ===============================================================

    async def _add_history(
        self,
        db: aiosqlite.Connection,
        approval_request_id: str,
        action: str,
        actor_id: str,
        actor_name: str,
        actor_role: str,
        previous_status: Optional[str],
        new_status: Optional[str],
        details: Optional[dict],
    ) -> None:
        """
        承認履歴を追加（HMAC署名付き）

        Args:
            db: データベース接続
            approval_request_id: リクエストID
            action: アクション種別
            actor_id: 実行者ID
            actor_name: 実行者表示名
            actor_role: 実行者ロール
            previous_status: 変更前ステータス
            new_status: 変更後ステータス
            details: 追加情報
        """
        timestamp = datetime.utcnow().isoformat()

        # HMAC 署名の計算
        signature = compute_history_signature(
            approval_request_id=approval_request_id,
            action=action,
            actor_id=actor_id,
            timestamp=timestamp,
            details=details,
        )

        await db.execute(
            """
            INSERT INTO approval_history (
                approval_request_id, action, actor_id, actor_name, actor_role,
                timestamp, details, previous_status, new_status, signature
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                approval_request_id,
                action,
                actor_id,
                actor_name,
                actor_role,
                timestamp,
                json.dumps(details, ensure_ascii=False) if details else None,
                previous_status,
                new_status,
                signature,
            ),
        )

    # ===============================================================
    # 9. 汎用リクエスト一覧取得
    # ===============================================================

    async def list_requests(
        self,
        status: Optional[str] = None,
        requester_id: Optional[str] = None,
        request_type: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        page: int = 1,
        per_page: int = 20,
    ) -> dict:
        """
        承認リクエストの汎用一覧取得（Admin/Approver向け全件、その他は自分のみ）

        Args:
            status: ステータスフィルタ（任意）
            requester_id: 申請者IDフィルタ（任意）
            request_type: 操作種別フィルタ（任意）
            sort_by: ソートキー（created_at, expires_at, request_type, status）
            sort_order: ソート順（asc/desc）
            page: ページ番号
            per_page: 1ページあたり件数

        Returns:
            リクエスト一覧（ページネーション付き）
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            where_clauses = []
            params = []

            if status:
                if status not in ALLOWED_STATUSES:
                    raise ValueError(f"Invalid status filter: {status}")
                where_clauses.append("r.status = ?")
                params.append(status)

            if requester_id:
                where_clauses.append("r.requester_id = ?")
                params.append(requester_id)

            if request_type:
                where_clauses.append("r.request_type = ?")
                params.append(request_type)

            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

            # ソート順の検証
            allowed_sort_keys = {"created_at", "expires_at", "request_type", "status"}
            if sort_by not in allowed_sort_keys:
                sort_by = "created_at"
            if sort_order.lower() not in {"asc", "desc"}:
                sort_order = "desc"

            # 総件数取得
            count_query = (
                f"SELECT COUNT(*) as total FROM approval_requests r WHERE {where_sql}"
            )
            async with db.execute(count_query, params) as cursor:
                total = (await cursor.fetchone())["total"]

            # リクエスト一覧取得
            offset = (page - 1) * per_page
            query = f"""
                SELECT
                    r.*,
                    p.description AS request_type_description,
                    p.risk_level
                FROM approval_requests r
                JOIN approval_policies p ON r.request_type = p.operation_type
                WHERE {where_sql}
                ORDER BY r.{sort_by} {sort_order}
                LIMIT ? OFFSET ?
            """

            async with db.execute(query, params + [per_page, offset]) as cursor:
                rows = await cursor.fetchall()

            requests = []
            for row in rows:
                requests.append(
                    {
                        "id": row["id"],
                        "request_type": row["request_type"],
                        "request_type_description": row["request_type_description"],
                        "risk_level": row["risk_level"],
                        "requester_id": row["requester_id"],
                        "requester_name": row["requester_name"],
                        "reason": row["reason"],
                        "status": row["status"],
                        "created_at": row["created_at"],
                        "expires_at": row["expires_at"],
                        "approved_by_name": row["approved_by_name"],
                        "approved_at": row["approved_at"],
                        "rejection_reason": row["rejection_reason"],
                    }
                )

            return {
                "total": total,
                "page": page,
                "per_page": per_page,
                "requests": requests,
            }

    # ===============================================================
    # 10. ポリシー取得
    # ===============================================================

    async def get_policy(self, operation_type: str) -> dict:
        """
        承認ポリシーを取得

        Args:
            operation_type: 操作種別

        Returns:
            ポリシー情報

        Raises:
            LookupError: ポリシーが存在しない
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM approval_policies WHERE operation_type = ?",
                (operation_type,),
            ) as cursor:
                policy = await cursor.fetchone()

            if not policy:
                raise LookupError(f"Approval policy not found: {operation_type}")

            return {
                "id": policy["id"],
                "operation_type": policy["operation_type"],
                "description": policy["description"],
                "approval_required": bool(policy["approval_required"]),
                "approver_roles": json.loads(policy["approver_roles"]),
                "approval_count": policy["approval_count"],
                "timeout_hours": policy["timeout_hours"],
                "auto_execute": bool(policy["auto_execute"]),
                "risk_level": policy["risk_level"],
            }

    async def list_policies(self) -> list[dict]:
        """
        全承認ポリシーの一覧を取得

        Returns:
            ポリシー一覧
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM approval_policies ORDER BY id"
            ) as cursor:
                policies = await cursor.fetchall()

            result = []
            for policy in policies:
                result.append(
                    {
                        "id": policy["id"],
                        "operation_type": policy["operation_type"],
                        "description": policy["description"],
                        "approval_required": bool(policy["approval_required"]),
                        "approver_roles": json.loads(policy["approver_roles"]),
                        "approval_count": policy["approval_count"],
                        "timeout_hours": policy["timeout_hours"],
                        "auto_execute": bool(policy["auto_execute"]),
                        "risk_level": policy["risk_level"],
                    }
                )

            return result

    # ===============================================================
    # 内部メソッド
    # ===============================================================

    async def _expire_request(
        self,
        db: aiosqlite.Connection,
        request: aiosqlite.Row,
        request_id: str,
    ) -> None:
        """
        リクエストを期限切れに変更

        Args:
            db: データベース接続
            request: リクエストレコード
            request_id: リクエストID
        """
        await db.execute(
            "UPDATE approval_requests SET status = 'expired' WHERE id = ?",
            (request_id,),
        )

        await self._add_history(
            db=db,
            approval_request_id=request_id,
            action="expired",
            actor_id="system",
            actor_name="system",
            actor_role="System",
            previous_status="pending",
            new_status="expired",
            details={"reason": "Approval request timed out"},
        )
