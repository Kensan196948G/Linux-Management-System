"""
監査ログモジュール

全操作を追記専用ログとして記録し、改ざん防止を実現
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .config import settings

logger = logging.getLogger(__name__)


class AuditLog:
    """監査ログ管理クラス"""

    def __init__(self, log_dir: Optional[Path] = None):
        """
        初期化

        Args:
            log_dir: ログディレクトリ（None の場合は設定から取得）
        """
        if log_dir is None:
            log_file = Path(settings.logging.file)
            log_dir = log_file.parent / "audit"

        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # 日別のログファイル
        today = datetime.now().strftime("%Y%m%d")
        self.log_file = self.log_dir / f"audit_{today}.json"

    def record(
        self,
        operation: str,
        user_id: str,
        target: str,
        status: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        監査ログを記録

        Args:
            operation: 操作種別（例: service_restart, log_view）
            user_id: 実行ユーザーID
            target: 操作対象（例: nginx, system）
            status: 実行結果（success, failure, denied）
            details: 追加詳細情報
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "operation": operation,
            "user_id": user_id,
            "target": target,
            "status": status,
            "details": details or {},
        }

        try:
            # 追記モードで書き込み（改ざん防止）
            with open(self.log_file, "a", encoding="utf-8") as f:
                json.dump(log_entry, f, ensure_ascii=False)
                f.write("\n")

            logger.info(
                f"Audit log recorded: operation={operation}, user={user_id}, "
                f"target={target}, status={status}"
            )

        except Exception as e:
            logger.error(f"Failed to record audit log: {e}")
            # 監査ログの記録失敗は重大なため、再 raise
            raise

    def query(
        self,
        user_role: str,
        requesting_user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        user_id: Optional[str] = None,
        operation: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[Dict[str, Any]]:
        """
        監査ログを検索（RBAC適用）

        Args:
            user_role: リクエストユーザーのロール（Admin/Operator/Approver/Viewer）
            requesting_user_id: リクエストユーザーのID
            start_date: 開始日時
            end_date: 終了日時
            user_id: ユーザーID（フィルタ）
            operation: 操作種別（フィルタ）
            status: ステータス（フィルタ）
            limit: 最大取得件数

        Returns:
            監査ログエントリのリスト

        Raises:
            PermissionError: Viewerロールの場合（監査ログアクセス不可）
        """
        # RBAC: Viewerは監査ログにアクセス不可
        if user_role == "Viewer":
            raise PermissionError("Viewer role cannot access audit logs")

        results = []

        # 全ログファイルを走査
        for log_file in sorted(self.log_dir.glob("audit_*.json")):
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        entry = json.loads(line.strip())

                        # RBAC: Operator/Approverは自分のログのみ閲覧可能
                        if user_role in ["Operator", "Approver"]:
                            if entry.get("user_id") != requesting_user_id:
                                continue

                        # Admin は全てのログを閲覧可能（RBACフィルタなし）

                        # フィルタ適用
                        if user_id and entry.get("user_id") != user_id:
                            continue
                        if operation and entry.get("operation") != operation:
                            continue
                        if status and entry.get("status") != status:
                            continue

                        entry_time = datetime.fromisoformat(entry["timestamp"])
                        if start_date and entry_time < start_date:
                            continue
                        if end_date and entry_time > end_date:
                            continue

                        results.append(entry)

                        if len(results) >= limit:
                            return results

            except Exception as e:
                logger.error(f"Failed to read audit log {log_file}: {e}")
                continue

        return results


# グローバルインスタンス
audit_log = AuditLog()
