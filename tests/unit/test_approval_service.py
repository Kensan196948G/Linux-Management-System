"""
承認サービス（ApprovalService）のユニットテスト

テスト対象: backend/core/approval_service.py
テスト項目: 30ケース（ビジネスロジック層）
"""

import asyncio
import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest

from backend.core.approval_service import (
    ALLOWED_ACTIONS,
    ALLOWED_STATUSES,
    FORBIDDEN_CHARS,
    ApprovalService,
    compute_history_signature,
    validate_payload_values,
    verify_history_signature,
)


# ============================================================================
# ヘルパー関数
# ============================================================================


def run_async(coro):
    """asyncio コルーチンを同期的に実行（running loop対応）"""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        # 既にrunning loopがある場合は新しいスレッドで実行
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    except RuntimeError:
        return asyncio.run(coro)


# ============================================================================
# Test Case 1-10: 承認リクエスト作成
# ============================================================================


class TestCreateApprovalRequest:
    """承認リクエスト作成のテスト"""

    def test_create_request_success(self, approval_service_with_mock_audit):
        """TC001: 承認リクエスト作成成功"""
        service = approval_service_with_mock_audit
        result = run_async(
            service.create_request(
                request_type="user_add",
                payload={
                    "username": "newuser",
                    "group": "developers",
                    "home": "/home/newuser",
                    "shell": "/bin/bash",
                },
                reason="新規メンバーのアカウント作成",
                requester_id="user_002",
                requester_name="operator",
                requester_role="Operator",
            )
        )

        assert "request_id" in result
        assert result["request_type"] == "user_add"
        assert result["status"] == "pending"
        assert "created_at" in result
        assert "expires_at" in result

    def test_create_request_invalid_operation_type(self, approval_service_with_mock_audit):
        """TC002: 不正な操作種別でリクエスト作成失敗"""
        service = approval_service_with_mock_audit
        with pytest.raises(LookupError, match="Invalid request_type"):
            run_async(
                service.create_request(
                    request_type="nonexistent_operation",
                    payload={"key": "value"},
                    reason="テスト",
                    requester_id="user_002",
                    requester_name="operator",
                    requester_role="Operator",
                )
            )

    def test_create_request_forbidden_chars_in_payload(self, approval_service_with_mock_audit):
        """TC003: ペイロードに特殊文字が含まれる場合は拒否"""
        service = approval_service_with_mock_audit
        with pytest.raises(ValueError, match="Forbidden character"):
            run_async(
                service.create_request(
                    request_type="user_add",
                    payload={"username": "user; rm -rf /"},
                    reason="テスト",
                    requester_id="user_002",
                    requester_name="operator",
                    requester_role="Operator",
                )
            )

    def test_create_request_empty_reason(self, approval_service_with_mock_audit):
        """TC004: 申請理由が空の場合は拒否（APIレイヤーでバリデーション）"""
        # ApprovalService 自体は reason の空文字を拒否しない（APIレイヤーが Pydantic で検証）
        # サービスレイヤーでは空文字でも受け付ける仕様（ただしAPIは min_length=1）
        service = approval_service_with_mock_audit
        # サービスレイヤーでは通過する（API層がバリデーション担当）
        result = run_async(
            service.create_request(
                request_type="user_add",
                payload={"username": "testuser", "group": "dev"},
                reason="",  # 空文字列
                requester_id="user_002",
                requester_name="operator",
                requester_role="Operator",
            )
        )
        assert result["status"] == "pending"

    def test_create_request_reason_too_long(self, approval_service_with_mock_audit):
        """TC005: 申請理由が1000文字を超える場合（APIレイヤーでバリデーション）"""
        # ApprovalService 自体は reason 長をチェックしない（APIレイヤーが Pydantic で検証）
        service = approval_service_with_mock_audit
        long_reason = "a" * 1001
        result = run_async(
            service.create_request(
                request_type="user_add",
                payload={"username": "testuser", "group": "dev"},
                reason=long_reason,
                requester_id="user_002",
                requester_name="operator",
                requester_role="Operator",
            )
        )
        # サービスレイヤーでは通過
        assert result["status"] == "pending"

    def test_create_request_generates_uuid(self, approval_service_with_mock_audit):
        """TC006: リクエストIDとしてUUID v4が生成されること"""
        service = approval_service_with_mock_audit
        result = run_async(
            service.create_request(
                request_type="user_add",
                payload={"username": "uuidtest", "group": "dev"},
                reason="UUID検証テスト",
                requester_id="user_002",
                requester_name="operator",
                requester_role="Operator",
            )
        )

        request_id = result["request_id"]
        # UUID v4 形式の検証
        parsed = uuid.UUID(request_id, version=4)
        assert str(parsed) == request_id

    def test_create_request_sets_expires_at(self, approval_service_with_mock_audit):
        """TC007: 承認期限がポリシーのtimeout_hoursに基づいて設定されること"""
        service = approval_service_with_mock_audit
        before = datetime.utcnow()
        result = run_async(
            service.create_request(
                request_type="user_add",
                payload={"username": "expirytest", "group": "dev"},
                reason="期限検証テスト",
                requester_id="user_002",
                requester_name="operator",
                requester_role="Operator",
            )
        )

        created_at = datetime.fromisoformat(result["created_at"])
        expires_at = datetime.fromisoformat(result["expires_at"])
        timeout_hours = result["timeout_hours"]

        # expires_at は created_at + timeout_hours であること
        expected_expiry = created_at + timedelta(hours=timeout_hours)
        # 数秒の差は許容
        assert abs((expires_at - expected_expiry).total_seconds()) < 5

    def test_create_request_logs_to_audit(self, approval_service_with_mock_audit, audit_log):
        """TC008: リクエスト作成が監査ログに記録されること"""
        service = approval_service_with_mock_audit
        run_async(
            service.create_request(
                request_type="user_add",
                payload={"username": "auditlog", "group": "dev"},
                reason="監査ログテスト",
                requester_id="user_002",
                requester_name="operator",
                requester_role="Operator",
            )
        )

        # 監査ログが記録されたことを検証
        assert audit_log.record.called
        call_kwargs = audit_log.record.call_args
        assert call_kwargs is not None

    def test_create_request_adds_history_entry(self, approval_service_with_mock_audit):
        """TC009: approval_historyに'created'アクションが記録されること"""
        service = approval_service_with_mock_audit
        result = run_async(
            service.create_request(
                request_type="user_add",
                payload={"username": "histtest", "group": "dev"},
                reason="履歴テスト",
                requester_id="user_002",
                requester_name="operator",
                requester_role="Operator",
            )
        )

        # get_request で詳細を取得し、履歴を確認
        detail = run_async(service.get_request(result["request_id"]))
        assert len(detail["history"]) >= 1
        assert detail["history"][0]["action"] == "created"
        assert detail["history"][0]["actor_id"] == "user_002"

    def test_create_request_hmac_signature(self, approval_service_with_mock_audit):
        """TC010: 履歴エントリにHMAC-SHA256署名が付与されること"""
        service = approval_service_with_mock_audit
        result = run_async(
            service.create_request(
                request_type="user_add",
                payload={"username": "hmactest", "group": "dev"},
                reason="HMAC署名テスト",
                requester_id="user_002",
                requester_name="operator",
                requester_role="Operator",
            )
        )

        # 直接DBにアクセスして署名を確認
        import aiosqlite

        async def check_signature():
            async with aiosqlite.connect(service.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT * FROM approval_history WHERE approval_request_id = ?",
                    (result["request_id"],),
                ) as cursor:
                    row = await cursor.fetchone()
                assert row is not None
                assert row["signature"] is not None
                assert len(row["signature"]) == 64  # SHA256 は64文字の16進数
                # 署名検証
                record = dict(row)
                if record["details"]:
                    record["details"] = json.loads(record["details"])
                assert verify_history_signature(record)

        run_async(check_signature())


# ============================================================================
# Test Case 11-20: 承認/拒否
# ============================================================================


class TestApprovalActions:
    """承認・拒否のテスト"""

    def _create_test_request(self, service):
        """テスト用リクエストを作成するヘルパー"""
        return run_async(
            service.create_request(
                request_type="user_add",
                payload={"username": "approvaltest", "group": "dev"},
                reason="承認テスト用リクエスト",
                requester_id="user_002",
                requester_name="operator",
                requester_role="Operator",
            )
        )

    def test_approve_request_success(self, approval_service_with_mock_audit):
        """TC011: 承認成功"""
        service = approval_service_with_mock_audit
        req = self._create_test_request(service)

        result = run_async(
            service.approve_request(
                request_id=req["request_id"],
                approver_id="user_003",
                approver_name="admin",
                approver_role="Admin",
                comment="承認します",
            )
        )

        assert result["request_id"] == req["request_id"]
        assert result["approved_by"] == "user_003"
        assert "approved_at" in result

    def test_approve_request_self_approval_prohibited(
        self, approval_service_with_mock_audit
    ):
        """TC012: 自己承認は禁止（requester_id == approver_id）"""
        service = approval_service_with_mock_audit
        req = self._create_test_request(service)

        with pytest.raises(ValueError, match="Self-approval is prohibited"):
            run_async(
                service.approve_request(
                    request_id=req["request_id"],
                    approver_id="user_002",  # 申請者と同じ
                    approver_name="operator",
                    approver_role="Operator",
                )
            )

    def test_approve_request_insufficient_role(
        self, approval_service_with_mock_audit
    ):
        """TC013: 権限不足（Operatorは承認不可）- サービス層ではロールチェックなし（API層が担当）"""
        # ApprovalService はロールベースの権限チェックを行わない
        # （API層の require_permission で実施）
        # サービス層では自己承認禁止のみチェック
        service = approval_service_with_mock_audit
        req = self._create_test_request(service)

        # user_005 (別のOperator) なら自己承認にならないため成功する
        result = run_async(
            service.approve_request(
                request_id=req["request_id"],
                approver_id="user_005",
                approver_name="other_operator",
                approver_role="Operator",
            )
        )
        assert result["approved_by"] == "user_005"

    def test_approve_request_already_approved(
        self, approval_service_with_mock_audit
    ):
        """TC014: 既に承認済みのリクエストは承認不可"""
        service = approval_service_with_mock_audit
        req = self._create_test_request(service)

        # 1回目の承認
        run_async(
            service.approve_request(
                request_id=req["request_id"],
                approver_id="user_003",
                approver_name="admin",
                approver_role="Admin",
            )
        )

        # 2回目の承認は失敗
        with pytest.raises(ValueError, match="Cannot approve"):
            run_async(
                service.approve_request(
                    request_id=req["request_id"],
                    approver_id="user_004",
                    approver_name="approver",
                    approver_role="Approver",
                )
            )

    def test_approve_request_expired(
        self, approval_service_with_mock_audit
    ):
        """TC015: 期限切れリクエストは承認不可"""
        service = approval_service_with_mock_audit
        req = self._create_test_request(service)

        # DBの expires_at を過去に変更
        import aiosqlite

        async def set_expired():
            past = (datetime.utcnow() - timedelta(hours=1)).isoformat()
            async with aiosqlite.connect(service.db_path) as db:
                await db.execute(
                    "UPDATE approval_requests SET expires_at = ? WHERE id = ?",
                    (past, req["request_id"]),
                )
                await db.commit()

        run_async(set_expired())

        with pytest.raises(ValueError, match="expired"):
            run_async(
                service.approve_request(
                    request_id=req["request_id"],
                    approver_id="user_003",
                    approver_name="admin",
                    approver_role="Admin",
                )
            )

    def test_reject_request_success(self, approval_service_with_mock_audit):
        """TC016: 拒否成功"""
        service = approval_service_with_mock_audit
        req = self._create_test_request(service)

        result = run_async(
            service.reject_request(
                request_id=req["request_id"],
                approver_id="user_003",
                approver_name="admin",
                approver_role="Admin",
                rejection_reason="テスト拒否",
            )
        )

        assert result["request_id"] == req["request_id"]
        assert result["rejected_by"] == "user_003"
        assert result["rejection_reason"] == "テスト拒否"

    def test_reject_request_empty_reason(
        self, approval_service_with_mock_audit
    ):
        """TC017: 拒否理由が空の場合（APIレイヤーでバリデーション）"""
        # サービス層は空文字でもFORBIDDEN_CHARS チェックのみ
        # API層の Pydantic (min_length=1) が空文字を拒否
        service = approval_service_with_mock_audit
        req = self._create_test_request(service)

        # 空文字列は FORBIDDEN_CHARS に含まれないので通過する
        result = run_async(
            service.reject_request(
                request_id=req["request_id"],
                approver_id="user_003",
                approver_name="admin",
                approver_role="Admin",
                rejection_reason="",
            )
        )
        assert result["rejection_reason"] == ""

    def test_reject_request_already_rejected(
        self, approval_service_with_mock_audit
    ):
        """TC018: 既に拒否済みのリクエストは拒否不可"""
        service = approval_service_with_mock_audit
        req = self._create_test_request(service)

        # 1回目の拒否
        run_async(
            service.reject_request(
                request_id=req["request_id"],
                approver_id="user_003",
                approver_name="admin",
                approver_role="Admin",
                rejection_reason="初回拒否",
            )
        )

        # 2回目の拒否は失敗
        with pytest.raises(ValueError, match="Cannot reject"):
            run_async(
                service.reject_request(
                    request_id=req["request_id"],
                    approver_id="user_004",
                    approver_name="approver",
                    approver_role="Approver",
                    rejection_reason="2回目拒否",
                )
            )

    def test_approve_logs_to_audit(self, approval_service_with_mock_audit, audit_log):
        """TC019: 承認操作が監査ログに記録されること"""
        service = approval_service_with_mock_audit
        req = self._create_test_request(service)

        # audit_log のレコード数を記録
        initial_count = len(audit_log.records)

        run_async(
            service.approve_request(
                request_id=req["request_id"],
                approver_id="user_003",
                approver_name="admin",
                approver_role="Admin",
            )
        )

        # 承認で監査ログが1件追加されていること
        assert len(audit_log.records) > initial_count
        latest = audit_log.records[-1]
        assert latest["operation"] == "approval_approved"

    def test_reject_logs_to_audit(self, approval_service_with_mock_audit, audit_log):
        """TC020: 拒否操作が監査ログに記録されること"""
        service = approval_service_with_mock_audit
        req = self._create_test_request(service)

        initial_count = len(audit_log.records)

        run_async(
            service.reject_request(
                request_id=req["request_id"],
                approver_id="user_003",
                approver_name="admin",
                approver_role="Admin",
                rejection_reason="監査ログテスト",
            )
        )

        assert len(audit_log.records) > initial_count
        latest = audit_log.records[-1]
        assert latest["operation"] == "approval_rejected"


# ============================================================================
# Test Case 21-30: その他の操作
# ============================================================================


class TestOtherOperations:
    """キャンセル・実行・タイムアウト処理のテスト"""

    def _create_test_request(self, service, requester_id="user_002"):
        """テスト用リクエストを作成するヘルパー"""
        return run_async(
            service.create_request(
                request_type="user_add",
                payload={"username": "othertest", "group": "dev"},
                reason="その他操作テスト",
                requester_id=requester_id,
                requester_name="operator" if requester_id == "user_002" else "admin",
                requester_role="Operator" if requester_id == "user_002" else "Admin",
            )
        )

    def test_cancel_request_success(self, approval_service_with_mock_audit):
        """TC021: キャンセル成功（申請者本人のみ）"""
        service = approval_service_with_mock_audit
        req = self._create_test_request(service)

        result = run_async(
            service.cancel_request(
                request_id=req["request_id"],
                requester_id="user_002",
                requester_name="operator",
                requester_role="Operator",
                reason="不要になったため",
            )
        )

        assert result["request_id"] == req["request_id"]
        assert "cancelled_at" in result

    def test_cancel_request_not_requester(
        self, approval_service_with_mock_audit
    ):
        """TC022: 申請者以外はキャンセル不可"""
        service = approval_service_with_mock_audit
        req = self._create_test_request(service)

        with pytest.raises(ValueError, match="Only the requester can cancel"):
            run_async(
                service.cancel_request(
                    request_id=req["request_id"],
                    requester_id="user_003",  # 申請者ではない
                    requester_name="admin",
                    requester_role="Admin",
                )
            )

    def test_cancel_request_not_pending(self, approval_service_with_mock_audit):
        """TC023: pending以外のステータスはキャンセル不可"""
        service = approval_service_with_mock_audit
        req = self._create_test_request(service)

        # まず承認する
        run_async(
            service.approve_request(
                request_id=req["request_id"],
                approver_id="user_003",
                approver_name="admin",
                approver_role="Admin",
            )
        )

        # 承認済みのキャンセルは失敗
        with pytest.raises(ValueError, match="Cannot cancel"):
            run_async(
                service.cancel_request(
                    request_id=req["request_id"],
                    requester_id="user_002",
                    requester_name="operator",
                    requester_role="Operator",
                )
            )

    def test_execute_approved_request_success(
        self, approval_service_with_mock_audit
    ):
        """TC024: 承認済みリクエストの手動実行成功 - v0.4予定のためスキップ"""
        # execute メソッドは v0.4 で実装予定
        # 現時点では ApprovalService にメソッドが存在しない
        pytest.skip("execute method is planned for v0.4")

    def test_execute_not_approved_request(
        self, approval_service_with_mock_audit
    ):
        """TC025: 承認済み以外のリクエストは実行不可 - v0.4予定のためスキップ"""
        pytest.skip("execute method is planned for v0.4")

    def test_timeout_processing_marks_expired(self, approval_service_with_mock_audit):
        """TC026: タイムアウト処理で期限切れリクエストをexpiredに変更"""
        service = approval_service_with_mock_audit
        req = self._create_test_request(service)

        # expires_at を過去に変更
        import aiosqlite

        async def set_expired():
            past = (datetime.utcnow() - timedelta(hours=1)).isoformat()
            async with aiosqlite.connect(service.db_path) as db:
                await db.execute(
                    "UPDATE approval_requests SET expires_at = ? WHERE id = ?",
                    (past, req["request_id"]),
                )
                await db.commit()

        run_async(set_expired())

        count = run_async(service.expire_old_requests())
        assert count >= 1

        # ステータスが expired になっていること
        detail = run_async(service.get_request(req["request_id"]))
        assert detail["status"] == "expired"

    def test_timeout_processing_logs_to_history(self, approval_service_with_mock_audit):
        """TC027: タイムアウト処理で履歴に'expired'アクションを記録"""
        service = approval_service_with_mock_audit
        req = self._create_test_request(service)

        # expires_at を過去に変更
        import aiosqlite

        async def set_expired():
            past = (datetime.utcnow() - timedelta(hours=1)).isoformat()
            async with aiosqlite.connect(service.db_path) as db:
                await db.execute(
                    "UPDATE approval_requests SET expires_at = ? WHERE id = ?",
                    (past, req["request_id"]),
                )
                await db.commit()

        run_async(set_expired())

        run_async(service.expire_old_requests())

        # 履歴に expired アクションがあること
        detail = run_async(service.get_request(req["request_id"]))
        expired_actions = [h for h in detail["history"] if h["action"] == "expired"]
        assert len(expired_actions) >= 1
        assert expired_actions[0]["actor_id"] == "system"

    def test_auto_execute_on_approval(self, approval_service_with_mock_audit):
        """TC028: auto_execute=trueの場合、承認後に自動実行 - v0.4予定"""
        # auto_execute は v0.4 で実装予定
        # 現時点では承認は成功するが自動実行されない
        service = approval_service_with_mock_audit

        # auto_execute=true のポリシーで作成
        import aiosqlite

        async def set_auto_execute():
            async with aiosqlite.connect(service.db_path) as db:
                await db.execute(
                    "UPDATE approval_policies SET auto_execute = 1 WHERE operation_type = 'user_add'"
                )
                await db.commit()

        run_async(set_auto_execute())

        req = self._create_test_request(service)
        result = run_async(
            service.approve_request(
                request_id=req["request_id"],
                approver_id="user_003",
                approver_name="admin",
                approver_role="Admin",
            )
        )

        # auto_executed は現時点で False (v0.4 予定)
        assert result["auto_executed"] is False

    def test_execution_failure_marks_execution_failed(
        self, approval_service_with_mock_audit
    ):
        """TC029: 実行失敗時、ステータスをexecution_failedに変更 - v0.4予定"""
        pytest.skip("execute method is planned for v0.4")

    def test_hmac_signature_verification(self, approval_service_with_mock_audit):
        """TC030: HMAC署名検証が正しく動作すること"""
        # compute と verify の一致を確認
        details = {"comment": "テスト承認"}
        timestamp = datetime.utcnow().isoformat()
        request_id = str(uuid.uuid4())

        signature = compute_history_signature(
            approval_request_id=request_id,
            action="approved",
            actor_id="user_003",
            timestamp=timestamp,
            details=details,
        )

        # 署名が64文字の16進数
        assert len(signature) == 64

        # 正しいレコードで検証成功
        record = {
            "approval_request_id": request_id,
            "action": "approved",
            "actor_id": "user_003",
            "timestamp": timestamp,
            "details": details,
            "signature": signature,
        }
        assert verify_history_signature(record) is True

        # 改竄したレコードで検証失敗
        tampered_record = record.copy()
        tampered_record["action"] = "rejected"
        assert verify_history_signature(tampered_record) is False


# =====================================================================
# TC031: initialize_db() エラーケース
# =====================================================================


class TestInitializeDb:
    """initialize_db() のエラーパス"""

    def test_schema_file_not_found(self, approval_db_path):
        """TC031: スキーマファイルが存在しない場合 FileNotFoundError を送出"""
        service = ApprovalService(db_path=approval_db_path)
        with patch("pathlib.Path.exists", return_value=False):
            with pytest.raises(FileNotFoundError, match="Schema file not found"):
                run_async(service.initialize_db())


# =====================================================================
# TC032-034: approve_request() auto_execute パス
# =====================================================================


class TestApproveRequestAutoExecute:
    """auto_execute フラグ有効時の approve_request() 分岐"""

    def _create_test_request(self, service):
        """user_add リクエストを作成して返す"""
        return run_async(
            service.create_request(
                request_type="user_add",
                payload={"username": "autoexec_usr", "group": "dev"},
                reason="auto_execute テスト",
                requester_id="user_002",
                requester_name="operator",
                requester_role="Operator",
            )
        )

    def _set_auto_execute(self, service, operation_type, value=1):
        """approval_policies の auto_execute フラグを更新"""

        async def _update():
            async with aiosqlite.connect(service.db_path) as db:
                await db.execute(
                    "UPDATE approval_policies SET auto_execute = ? WHERE operation_type = ?",
                    (value, operation_type),
                )
                await db.commit()

        run_async(_update())

    def test_auto_execute_success(self, approval_service_with_mock_audit):
        """TC032: auto_execute=1 で execute_request 成功 → auto_executed=True"""
        service = approval_service_with_mock_audit
        req = self._create_test_request(service)
        self._set_auto_execute(service, "user_add", 1)

        mock_exec_result = {
            "request_id": req["request_id"],
            "request_type": "user_add",
            "executed_by": "user_003",
            "executed_by_name": "admin",
            "executed_at": "2026-01-01T00:00:00",
            "execution_result": {"status": "success"},
        }
        with patch.object(
            service,
            "execute_request",
            new_callable=AsyncMock,
            return_value=mock_exec_result,
        ):
            result = run_async(
                service.approve_request(
                    request_id=req["request_id"],
                    approver_id="user_003",
                    approver_name="admin",
                    approver_role="Admin",
                )
            )

        assert result["auto_executed"] is True
        assert "execution_result" in result

    def test_auto_execute_not_implemented(self, approval_service_with_mock_audit):
        """TC033: auto_execute=1 で execute_request が NotImplementedError → skipped_reason"""
        service = approval_service_with_mock_audit
        req = self._create_test_request(service)
        self._set_auto_execute(service, "user_add", 1)

        with patch.object(
            service,
            "execute_request",
            new_callable=AsyncMock,
            side_effect=NotImplementedError("未対応操作のため自動実行スキップ"),
        ):
            result = run_async(
                service.approve_request(
                    request_id=req["request_id"],
                    approver_id="user_003",
                    approver_name="admin",
                    approver_role="Admin",
                )
            )

        assert result["auto_executed"] is False
        assert "auto_execute_skipped_reason" in result

    def test_auto_execute_exception(self, approval_service_with_mock_audit):
        """TC034: auto_execute=1 で execute_request が Exception → auto_execute_error"""
        service = approval_service_with_mock_audit
        req = self._create_test_request(service)
        self._set_auto_execute(service, "user_add", 1)

        with patch.object(
            service,
            "execute_request",
            new_callable=AsyncMock,
            side_effect=RuntimeError("予期しない実行エラー"),
        ):
            result = run_async(
                service.approve_request(
                    request_id=req["request_id"],
                    approver_id="user_003",
                    approver_name="admin",
                    approver_role="Admin",
                )
            )

        assert result["auto_executed"] is False
        assert "auto_execute_error" in result


# =====================================================================
# TC035-037: reject_request() エラーケース
# =====================================================================


class TestRejectRequestEdgeCases:
    """reject_request() の未カバーパス"""

    def test_lookup_error(self, approval_service_with_mock_audit):
        """TC035: 存在しない request_id → LookupError"""
        service = approval_service_with_mock_audit
        with pytest.raises(LookupError):
            run_async(
                service.reject_request(
                    request_id=str(uuid.uuid4()),
                    approver_id="user_003",
                    approver_name="admin",
                    approver_role="Admin",
                    rejection_reason="テスト拒否",
                )
            )

    def test_non_pending_request(self, approval_service_with_mock_audit):
        """TC036: pending 以外のリクエスト（approved）→ ValueError"""
        service = approval_service_with_mock_audit
        req = run_async(
            service.create_request(
                request_type="user_add",
                payload={"username": "reject_npend", "group": "dev"},
                reason="拒否テスト",
                requester_id="user_002",
                requester_name="operator",
                requester_role="Operator",
            )
        )
        # まず承認してステータスを approved に変更
        run_async(
            service.approve_request(
                request_id=req["request_id"],
                approver_id="user_003",
                approver_name="admin",
                approver_role="Admin",
            )
        )
        with pytest.raises(ValueError, match="Only 'pending' requests can be rejected"):
            run_async(
                service.reject_request(
                    request_id=req["request_id"],
                    approver_id="user_003",
                    approver_name="admin",
                    approver_role="Admin",
                    rejection_reason="テスト拒否",
                )
            )

    def test_forbidden_char_in_rejection_reason(self, approval_service_with_mock_audit):
        """TC037: rejection_reason に FORBIDDEN_CHARS → ValueError（DB参照前に弾く）"""
        service = approval_service_with_mock_audit
        with pytest.raises(ValueError, match="Forbidden character"):
            run_async(
                service.reject_request(
                    request_id=str(uuid.uuid4()),
                    approver_id="user_003",
                    approver_name="admin",
                    approver_role="Admin",
                    rejection_reason="却下 | malicious",
                )
            )


# =====================================================================
# TC038-060: execute_request() ディスパッチ分岐
# =====================================================================


class TestExecuteRequestDispatch:
    """execute_request() の全ディスパッチ分岐テスト"""

    def _create_and_approve(self, service, request_type, payload):
        """リクエスト作成 → 承認 → (request_id, request_type) を返す"""
        req = run_async(
            service.create_request(
                request_type=request_type,
                payload=payload,
                reason="ディスパッチテスト",
                requester_id="user_002",
                requester_name="operator",
                requester_role="Operator",
            )
        )
        run_async(
            service.approve_request(
                request_id=req["request_id"],
                approver_id="user_003",
                approver_name="admin",
                approver_role="Admin",
            )
        )
        return req["request_id"]

    def _mock_wrapper_success(self):
        """sudo_wrapper をモック（成功レスポンス）"""
        mock = MagicMock()
        mock.add_user.return_value = {"status": "success"}
        mock.delete_user.return_value = {"status": "success"}
        mock.change_user_password.return_value = {"status": "success"}
        mock.modify_user_shell.return_value = {"status": "success"}
        mock.modify_user_gecos.return_value = {"status": "success"}
        mock.modify_user_add_group.return_value = {"status": "success"}
        mock.modify_user_remove_group.return_value = {"status": "success"}
        mock.add_group.return_value = {"status": "success"}
        mock.delete_group.return_value = {"status": "success"}
        mock.modify_group_membership.return_value = {"status": "success"}
        mock.add_cron_job.return_value = {"status": "success"}
        mock.remove_cron_job.return_value = {"status": "success"}
        mock.toggle_cron_job.return_value = {"status": "success"}
        mock.stop_service.return_value = {"status": "success"}
        mock.allow_firewall_port.return_value = {"status": "success"}
        mock.deny_firewall_port.return_value = {"status": "success"}
        mock.delete_firewall_rule.return_value = {"status": "success"}
        return mock

    def test_execute_request_not_found(self, approval_service_with_mock_audit):
        """TC038: 存在しない request_id → LookupError"""
        service = approval_service_with_mock_audit
        with pytest.raises(LookupError):
            run_async(
                service.execute_request(
                    request_id=str(uuid.uuid4()),
                    executor_id="user_003",
                    executor_name="admin",
                    executor_role="Admin",
                )
            )

    def test_execute_request_not_approved(self, approval_service_with_mock_audit):
        """TC039: pending ステータスのリクエスト → ValueError"""
        service = approval_service_with_mock_audit
        req = run_async(
            service.create_request(
                request_type="user_add",
                payload={"username": "exec_notappr", "group": "dev"},
                reason="実行テスト",
                requester_id="user_002",
                requester_name="operator",
                requester_role="Operator",
            )
        )
        with pytest.raises(ValueError, match="cannot be executed"):
            run_async(
                service.execute_request(
                    request_id=req["request_id"],
                    executor_id="user_003",
                    executor_name="admin",
                    executor_role="Admin",
                )
            )

    def test_dispatch_user_add(self, approval_service_with_mock_audit):
        """TC040: user_add ディスパッチ成功"""
        service = approval_service_with_mock_audit
        rid = self._create_and_approve(
            service,
            "user_add",
            {"username": "new_user1", "group": "dev"},
        )
        mock_sw = self._mock_wrapper_success()
        with patch("backend.core.sudo_wrapper.sudo_wrapper", mock_sw):
            result = run_async(
                service.execute_request(
                    request_id=rid,
                    executor_id="user_003",
                    executor_name="admin",
                    executor_role="Admin",
                )
            )
        assert result["request_type"] == "user_add"
        mock_sw.add_user.assert_called_once()

    def test_dispatch_user_delete(self, approval_service_with_mock_audit):
        """TC041: user_delete ディスパッチ成功"""
        service = approval_service_with_mock_audit
        rid = self._create_and_approve(
            service,
            "user_delete",
            {"username": "old_user1"},
        )
        mock_sw = self._mock_wrapper_success()
        with patch("backend.core.sudo_wrapper.sudo_wrapper", mock_sw):
            result = run_async(
                service.execute_request(
                    request_id=rid,
                    executor_id="user_003",
                    executor_name="admin",
                    executor_role="Admin",
                )
            )
        assert result["request_type"] == "user_delete"
        mock_sw.delete_user.assert_called_once()

    def test_dispatch_user_passwd_with_hash(self, approval_service_with_mock_audit):
        """TC042: user_passwd で password_hash あり → 成功"""
        service = approval_service_with_mock_audit
        rid = self._create_and_approve(
            service,
            "user_passwd",
            {"username": "passwd_user1", "password_hash": "sha512crypt_fakehash_nochars"},
        )
        mock_sw = self._mock_wrapper_success()
        with patch("backend.core.sudo_wrapper.sudo_wrapper", mock_sw):
            result = run_async(
                service.execute_request(
                    request_id=rid,
                    executor_id="user_003",
                    executor_name="admin",
                    executor_role="Admin",
                )
            )
        assert result["request_type"] == "user_passwd"
        mock_sw.change_user_password.assert_called_once()

    def test_dispatch_user_passwd_without_hash_raises_value_error(
        self, approval_service_with_mock_audit
    ):
        """TC043: user_passwd で password_hash なし → ValueError（except ブロック外に伝播）"""
        service = approval_service_with_mock_audit
        rid = self._create_and_approve(
            service,
            "user_passwd",
            {"username": "passwd_user2"},
        )
        mock_sw = self._mock_wrapper_success()
        with patch("backend.core.sudo_wrapper.sudo_wrapper", mock_sw):
            with pytest.raises(ValueError, match="password_hash が必要"):
                run_async(
                    service.execute_request(
                        request_id=rid,
                        executor_id="user_003",
                        executor_name="admin",
                        executor_role="Admin",
                    )
                )

    def test_dispatch_user_modify_set_shell(self, approval_service_with_mock_audit):
        """TC044: user_modify action=set-shell → 成功"""
        service = approval_service_with_mock_audit
        rid = self._create_and_approve(
            service,
            "user_modify",
            {"username": "mod_user1", "action": "set-shell", "shell": "/bin/sh"},
        )
        mock_sw = self._mock_wrapper_success()
        with patch("backend.core.sudo_wrapper.sudo_wrapper", mock_sw):
            result = run_async(
                service.execute_request(
                    request_id=rid,
                    executor_id="user_003",
                    executor_name="admin",
                    executor_role="Admin",
                )
            )
        assert result["request_type"] == "user_modify"
        mock_sw.modify_user_shell.assert_called_once()

    def test_dispatch_user_modify_set_gecos(self, approval_service_with_mock_audit):
        """TC045: user_modify action=set-gecos → 成功"""
        service = approval_service_with_mock_audit
        rid = self._create_and_approve(
            service,
            "user_modify",
            {"username": "mod_user2", "action": "set-gecos", "gecos": "Test User"},
        )
        mock_sw = self._mock_wrapper_success()
        with patch("backend.core.sudo_wrapper.sudo_wrapper", mock_sw):
            result = run_async(
                service.execute_request(
                    request_id=rid,
                    executor_id="user_003",
                    executor_name="admin",
                    executor_role="Admin",
                )
            )
        mock_sw.modify_user_gecos.assert_called_once()

    def test_dispatch_user_modify_add_group(self, approval_service_with_mock_audit):
        """TC046: user_modify action=add-group → 成功"""
        service = approval_service_with_mock_audit
        rid = self._create_and_approve(
            service,
            "user_modify",
            {"username": "mod_user3", "action": "add-group", "group": "devops"},
        )
        mock_sw = self._mock_wrapper_success()
        with patch("backend.core.sudo_wrapper.sudo_wrapper", mock_sw):
            run_async(
                service.execute_request(
                    request_id=rid,
                    executor_id="user_003",
                    executor_name="admin",
                    executor_role="Admin",
                )
            )
        mock_sw.modify_user_add_group.assert_called_once()

    def test_dispatch_user_modify_remove_group(self, approval_service_with_mock_audit):
        """TC047: user_modify action=remove-group → 成功"""
        service = approval_service_with_mock_audit
        rid = self._create_and_approve(
            service,
            "user_modify",
            {"username": "mod_user4", "action": "remove-group", "group": "devops"},
        )
        mock_sw = self._mock_wrapper_success()
        with patch("backend.core.sudo_wrapper.sudo_wrapper", mock_sw):
            run_async(
                service.execute_request(
                    request_id=rid,
                    executor_id="user_003",
                    executor_name="admin",
                    executor_role="Admin",
                )
            )
        mock_sw.modify_user_remove_group.assert_called_once()

    def test_dispatch_user_modify_unknown_action(self, approval_service_with_mock_audit):
        """TC048: user_modify 未知 action → NotImplementedError が捕捉され SudoWrapperError"""
        from backend.core.sudo_wrapper import SudoWrapperError

        service = approval_service_with_mock_audit
        rid = self._create_and_approve(
            service,
            "user_modify",
            {"username": "mod_user5", "action": "invalid-action"},
        )
        mock_sw = self._mock_wrapper_success()
        with patch("backend.core.sudo_wrapper.sudo_wrapper", mock_sw):
            with pytest.raises(SudoWrapperError):
                run_async(
                    service.execute_request(
                        request_id=rid,
                        executor_id="user_003",
                        executor_name="admin",
                        executor_role="Admin",
                    )
                )

    def test_dispatch_group_add(self, approval_service_with_mock_audit):
        """TC049: group_add ディスパッチ成功"""
        service = approval_service_with_mock_audit
        rid = self._create_and_approve(
            service,
            "group_add",
            {"name": "newgroup1"},
        )
        mock_sw = self._mock_wrapper_success()
        with patch("backend.core.sudo_wrapper.sudo_wrapper", mock_sw):
            result = run_async(
                service.execute_request(
                    request_id=rid,
                    executor_id="user_003",
                    executor_name="admin",
                    executor_role="Admin",
                )
            )
        assert result["request_type"] == "group_add"
        mock_sw.add_group.assert_called_once()

    def test_dispatch_group_delete(self, approval_service_with_mock_audit):
        """TC050: group_delete ディスパッチ成功"""
        service = approval_service_with_mock_audit
        rid = self._create_and_approve(
            service,
            "group_delete",
            {"name": "oldgroup1"},
        )
        mock_sw = self._mock_wrapper_success()
        with patch("backend.core.sudo_wrapper.sudo_wrapper", mock_sw):
            result = run_async(
                service.execute_request(
                    request_id=rid,
                    executor_id="user_003",
                    executor_name="admin",
                    executor_role="Admin",
                )
            )
        assert result["request_type"] == "group_delete"
        mock_sw.delete_group.assert_called_once()

    def test_dispatch_group_modify(self, approval_service_with_mock_audit):
        """TC051: group_modify ディスパッチ成功"""
        service = approval_service_with_mock_audit
        rid = self._create_and_approve(
            service,
            "group_modify",
            {"group": "devops", "action": "add", "user": "testuser"},
        )
        mock_sw = self._mock_wrapper_success()
        with patch("backend.core.sudo_wrapper.sudo_wrapper", mock_sw):
            result = run_async(
                service.execute_request(
                    request_id=rid,
                    executor_id="user_003",
                    executor_name="admin",
                    executor_role="Admin",
                )
            )
        assert result["request_type"] == "group_modify"
        mock_sw.modify_group_membership.assert_called_once()

    def test_dispatch_cron_add(self, approval_service_with_mock_audit):
        """TC052: cron_add ディスパッチ成功（schedule に * を含めない）"""
        service = approval_service_with_mock_audit
        rid = self._create_and_approve(
            service,
            "cron_add",
            {
                "username": "cronuser1",
                "schedule": "0 5 1 1 0",
                "command": "/usr/bin/backup",
            },
        )
        mock_sw = self._mock_wrapper_success()
        with patch("backend.core.sudo_wrapper.sudo_wrapper", mock_sw):
            result = run_async(
                service.execute_request(
                    request_id=rid,
                    executor_id="user_003",
                    executor_name="admin",
                    executor_role="Admin",
                )
            )
        assert result["request_type"] == "cron_add"
        mock_sw.add_cron_job.assert_called_once()

    def test_dispatch_cron_delete(self, approval_service_with_mock_audit):
        """TC053: cron_delete ディスパッチ成功"""
        service = approval_service_with_mock_audit
        rid = self._create_and_approve(
            service,
            "cron_delete",
            {"username": "cronuser2", "line_number": "3"},
        )
        mock_sw = self._mock_wrapper_success()
        with patch("backend.core.sudo_wrapper.sudo_wrapper", mock_sw):
            result = run_async(
                service.execute_request(
                    request_id=rid,
                    executor_id="user_003",
                    executor_name="admin",
                    executor_role="Admin",
                )
            )
        assert result["request_type"] == "cron_delete"
        mock_sw.remove_cron_job.assert_called_once_with(
            username="cronuser2", line_number=3
        )

    def test_dispatch_cron_modify(self, approval_service_with_mock_audit):
        """TC054: cron_modify ディスパッチ成功"""
        service = approval_service_with_mock_audit
        rid = self._create_and_approve(
            service,
            "cron_modify",
            {"username": "cronuser3", "line_number": "2", "action": "disable"},
        )
        mock_sw = self._mock_wrapper_success()
        with patch("backend.core.sudo_wrapper.sudo_wrapper", mock_sw):
            result = run_async(
                service.execute_request(
                    request_id=rid,
                    executor_id="user_003",
                    executor_name="admin",
                    executor_role="Admin",
                )
            )
        assert result["request_type"] == "cron_modify"
        mock_sw.toggle_cron_job.assert_called_once()

    def test_dispatch_service_stop(self, approval_service_with_mock_audit):
        """TC055: service_stop ディスパッチ成功"""
        service = approval_service_with_mock_audit
        rid = self._create_and_approve(
            service,
            "service_stop",
            {"service_name": "nginx"},
        )
        mock_sw = self._mock_wrapper_success()
        with patch("backend.core.sudo_wrapper.sudo_wrapper", mock_sw):
            result = run_async(
                service.execute_request(
                    request_id=rid,
                    executor_id="user_003",
                    executor_name="admin",
                    executor_role="Admin",
                )
            )
        assert result["request_type"] == "service_stop"
        mock_sw.stop_service.assert_called_once_with(service_name="nginx")

    def test_dispatch_firewall_allow(self, approval_service_with_mock_audit):
        """TC056: firewall_modify action=allow ディスパッチ成功"""
        service = approval_service_with_mock_audit
        rid = self._create_and_approve(
            service,
            "firewall_modify",
            {"action": "allow", "port": "443", "protocol": "tcp"},
        )
        mock_sw = self._mock_wrapper_success()
        with patch("backend.core.sudo_wrapper.sudo_wrapper", mock_sw):
            result = run_async(
                service.execute_request(
                    request_id=rid,
                    executor_id="user_003",
                    executor_name="admin",
                    executor_role="Admin",
                )
            )
        assert result["request_type"] == "firewall_modify"
        mock_sw.allow_firewall_port.assert_called_once()

    def test_dispatch_firewall_deny(self, approval_service_with_mock_audit):
        """TC057: firewall_modify action=deny ディスパッチ成功"""
        service = approval_service_with_mock_audit
        rid = self._create_and_approve(
            service,
            "firewall_modify",
            {"action": "deny", "port": "8080", "protocol": "tcp"},
        )
        mock_sw = self._mock_wrapper_success()
        with patch("backend.core.sudo_wrapper.sudo_wrapper", mock_sw):
            run_async(
                service.execute_request(
                    request_id=rid,
                    executor_id="user_003",
                    executor_name="admin",
                    executor_role="Admin",
                )
            )
        mock_sw.deny_firewall_port.assert_called_once()

    def test_dispatch_firewall_delete(self, approval_service_with_mock_audit):
        """TC058: firewall_modify action=delete ディスパッチ成功"""
        service = approval_service_with_mock_audit
        rid = self._create_and_approve(
            service,
            "firewall_modify",
            {"action": "delete", "rule_num": "5"},
        )
        mock_sw = self._mock_wrapper_success()
        with patch("backend.core.sudo_wrapper.sudo_wrapper", mock_sw):
            run_async(
                service.execute_request(
                    request_id=rid,
                    executor_id="user_003",
                    executor_name="admin",
                    executor_role="Admin",
                )
            )
        mock_sw.delete_firewall_rule.assert_called_once_with(rule_num="5")

    def test_dispatch_firewall_unknown_action_raises_value_error(
        self, approval_service_with_mock_audit
    ):
        """TC059: firewall_modify 未知 action → ValueError（except ブロック外に伝播）"""
        service = approval_service_with_mock_audit
        rid = self._create_and_approve(
            service,
            "firewall_modify",
            {"action": "unknown-action", "port": "80"},
        )
        mock_sw = self._mock_wrapper_success()
        with patch("backend.core.sudo_wrapper.sudo_wrapper", mock_sw):
            with pytest.raises(ValueError, match="Unknown firewall action"):
                run_async(
                    service.execute_request(
                        request_id=rid,
                        executor_id="user_003",
                        executor_name="admin",
                        executor_role="Admin",
                    )
                )

    def test_wrapper_returns_error_status(self, approval_service_with_mock_audit):
        """TC060: wrapper が status=error を返す → SudoWrapperError（execution_failed）"""
        from backend.core.sudo_wrapper import SudoWrapperError

        service = approval_service_with_mock_audit
        rid = self._create_and_approve(
            service,
            "service_stop",
            {"service_name": "nginx"},
        )
        mock_sw = MagicMock()
        mock_sw.stop_service.return_value = {
            "status": "error",
            "message": "Service not found",
        }
        with patch("backend.core.sudo_wrapper.sudo_wrapper", mock_sw):
            with pytest.raises(SudoWrapperError):
                run_async(
                    service.execute_request(
                        request_id=rid,
                        executor_id="user_003",
                        executor_name="admin",
                        executor_role="Admin",
                    )
                )


# =====================================================================
# TC061-062: list_pending_requests() ソートフォールバック
# =====================================================================


class TestListPendingRequestsSortFallback:
    """list_pending_requests() の無効ソートパラメーター処理"""

    def _create_pending(self, service):
        """pending リクエストを1件作成"""
        return run_async(
            service.create_request(
                request_type="user_add",
                payload={"username": "sort_test_usr", "group": "dev"},
                reason="ソートテスト",
                requester_id="user_002",
                requester_name="operator",
                requester_role="Operator",
            )
        )

    def test_invalid_sort_by_falls_back(self, approval_service_with_mock_audit):
        """TC061: 無効な sort_by → created_at フォールバック（エラーなし）"""
        service = approval_service_with_mock_audit
        self._create_pending(service)
        result = run_async(
            service.list_pending_requests(sort_by="invalid_col")
        )
        assert isinstance(result["requests"], list)

    def test_invalid_sort_order_falls_back(self, approval_service_with_mock_audit):
        """TC062: 無効な sort_order → asc フォールバック（エラーなし）"""
        service = approval_service_with_mock_audit
        self._create_pending(service)
        result = run_async(
            service.list_pending_requests(sort_order="invalid_order")
        )
        assert isinstance(result["requests"], list)


# =====================================================================
# TC063: list_my_requests() request_type フィルター
# =====================================================================


class TestListMyRequestsFilter:
    """list_my_requests() の request_type フィルタリング"""

    def test_request_type_filter(self, approval_service_with_mock_audit):
        """TC063: request_type フィルターで対象種別のみ返る"""
        service = approval_service_with_mock_audit
        requester_id = "filter_user_001"

        # user_add と group_add の2件を作成
        for i in range(2):
            run_async(
                service.create_request(
                    request_type="user_add",
                    payload={"username": f"filter_usr{i}", "group": "dev"},
                    reason="フィルターテスト",
                    requester_id=requester_id,
                    requester_name="operator",
                    requester_role="Operator",
                )
            )
        run_async(
            service.create_request(
                request_type="group_add",
                payload={"name": "filter_grp"},
                reason="フィルターテスト",
                requester_id=requester_id,
                requester_name="operator",
                requester_role="Operator",
            )
        )

        result = run_async(
            service.list_my_requests(
                requester_id=requester_id,
                request_type="user_add",
            )
        )

        assert result["total"] == 2
        for req in result["requests"]:
            assert req["request_type"] == "user_add"


# =====================================================================
# TC064-067: cancel_request() エラーケース
# =====================================================================


class TestCancelRequestEdgeCases:
    """cancel_request() の未カバーパス"""

    def test_lookup_error(self, approval_service_with_mock_audit):
        """TC064: 存在しない request_id → LookupError"""
        service = approval_service_with_mock_audit
        with pytest.raises(LookupError):
            run_async(
                service.cancel_request(
                    request_id=str(uuid.uuid4()),
                    requester_id="user_002",
                    requester_name="operator",
                    requester_role="Operator",
                )
            )

    def test_other_user_cannot_cancel(self, approval_service_with_mock_audit):
        """TC065: 申請者以外がキャンセル → ValueError"""
        service = approval_service_with_mock_audit
        req = run_async(
            service.create_request(
                request_type="user_add",
                payload={"username": "cancel_usr1", "group": "dev"},
                reason="キャンセルテスト",
                requester_id="user_002",
                requester_name="operator",
                requester_role="Operator",
            )
        )
        with pytest.raises(ValueError, match="Only the requester"):
            run_async(
                service.cancel_request(
                    request_id=req["request_id"],
                    requester_id="user_999",
                    requester_name="intruder",
                    requester_role="Operator",
                )
            )

    def test_non_pending_request(self, approval_service_with_mock_audit):
        """TC066: pending 以外のリクエスト → ValueError"""
        service = approval_service_with_mock_audit
        req = run_async(
            service.create_request(
                request_type="user_add",
                payload={"username": "cancel_usr2", "group": "dev"},
                reason="キャンセルテスト",
                requester_id="user_002",
                requester_name="operator",
                requester_role="Operator",
            )
        )
        # 承認してステータスを approved に変更
        run_async(
            service.approve_request(
                request_id=req["request_id"],
                approver_id="user_003",
                approver_name="admin",
                approver_role="Admin",
            )
        )
        with pytest.raises(ValueError, match="Only 'pending' requests can be cancelled"):
            run_async(
                service.cancel_request(
                    request_id=req["request_id"],
                    requester_id="user_002",
                    requester_name="operator",
                    requester_role="Operator",
                )
            )

    def test_cancel_success(self, approval_service_with_mock_audit):
        """TC067: pending リクエストのキャンセル成功"""
        service = approval_service_with_mock_audit
        req = run_async(
            service.create_request(
                request_type="user_add",
                payload={"username": "cancel_usr3", "group": "dev"},
                reason="キャンセルテスト",
                requester_id="user_002",
                requester_name="operator",
                requester_role="Operator",
            )
        )
        result = run_async(
            service.cancel_request(
                request_id=req["request_id"],
                requester_id="user_002",
                requester_name="operator",
                requester_role="Operator",
                reason="テストのためキャンセル",
            )
        )
        assert result["request_id"] == req["request_id"]
        assert "cancelled_at" in result


# =====================================================================
# TC068-071: list_requests() 汎用一覧取得
# =====================================================================


class TestListRequests:
    """list_requests() の全パス"""

    def _create_req(self, service, requester_id, request_type="user_add", username="lr_usr"):
        return run_async(
            service.create_request(
                request_type=request_type,
                payload={"username": username, "group": "dev"},
                reason="list_requests テスト",
                requester_id=requester_id,
                requester_name="operator",
                requester_role="Operator",
            )
        )

    def test_basic_list(self, approval_service_with_mock_audit):
        """TC068: フィルターなし一覧取得"""
        service = approval_service_with_mock_audit
        self._create_req(service, "user_001", username="lr_usr1")
        result = run_async(service.list_requests())
        assert "total" in result
        assert "requests" in result
        assert result["total"] >= 1

    def test_status_filter(self, approval_service_with_mock_audit):
        """TC069: status フィルターで pending のみ返る"""
        service = approval_service_with_mock_audit
        self._create_req(service, "user_001", username="lr_usr2")
        result = run_async(service.list_requests(status="pending"))
        assert result["total"] >= 1
        for req in result["requests"]:
            assert req["status"] == "pending"

    def test_invalid_status_raises_value_error(self, approval_service_with_mock_audit):
        """TC070: 無効な status フィルター → ValueError"""
        service = approval_service_with_mock_audit
        with pytest.raises(ValueError, match="Invalid status filter"):
            run_async(service.list_requests(status="invalid_status"))

    def test_sort_fallback(self, approval_service_with_mock_audit):
        """TC071: 無効な sort_by/sort_order → フォールバック（エラーなし）"""
        service = approval_service_with_mock_audit
        self._create_req(service, "user_001", username="lr_usr3")
        result = run_async(
            service.list_requests(sort_by="bad_col", sort_order="bad_order")
        )
        assert isinstance(result["requests"], list)


# =====================================================================
# TC072-073: get_policy() エラーケース
# =====================================================================


class TestGetPolicyEdgeCases:
    """get_policy() の未カバーパス"""

    def test_lookup_error(self, approval_service_with_mock_audit):
        """TC072: 存在しない operation_type → LookupError"""
        service = approval_service_with_mock_audit
        with pytest.raises(LookupError):
            run_async(service.get_policy("nonexistent_operation"))

    def test_get_policy_success(self, approval_service_with_mock_audit):
        """TC073: 既存の operation_type → ポリシー情報返却"""
        service = approval_service_with_mock_audit
        result = run_async(service.get_policy("user_add"))
        assert result["operation_type"] == "user_add"
        assert "description" in result
        assert "risk_level" in result


# =====================================================================
# TC074-076: initialize_db() 正常パス（lines 202-219）
# =====================================================================


class TestInitializeDbHappyPath:
    """initialize_db() の正常実行パスをカバー"""

    def test_initialize_db_creates_tables(self, tmp_path):
        """TC074: 新規DBにスキーマを適用してテーブルが作成される"""
        db_path = str(tmp_path / "test_init_happy.db")
        service = ApprovalService(db_path=db_path)
        run_async(service.initialize_db())

        async def check_tables():
            async with aiosqlite.connect(db_path) as db:
                async with db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ) as cursor:
                    return await cursor.fetchall()

        tables = run_async(check_tables())
        table_names = [t[0] for t in tables]
        assert "approval_requests" in table_names

    def test_initialize_db_migration_already_applied(self, tmp_path):
        """TC075: 2回目の initialize_db() はマイグレーションスキップ（例外なし）"""
        db_path = str(tmp_path / "test_init_dup.db")
        service = ApprovalService(db_path=db_path)
        # First call - applies schema and migration
        run_async(service.initialize_db())
        # Second call - migration fails silently (column already exists)
        run_async(service.initialize_db())

    def test_initialize_db_log_success(self, tmp_path):
        """TC076: 正常完了ログが出力される（例外なし）"""
        db_path = str(tmp_path / "test_init_log.db")
        service = ApprovalService(db_path=db_path)
        # Should complete without raising
        run_async(service.initialize_db())


# =====================================================================
# TC077-078: execute_request() 未定義 operation_type（lines 655, 768）
# =====================================================================


class TestExecuteRequestUnknownType:
    """execute_request() で未知の operation_type が execution_failed になること"""

    def _insert_approved_request(self, service, request_type: str) -> str:
        """テスト用に approved 状態のリクエストを直接 DB に挿入"""
        import uuid
        from datetime import datetime, timedelta

        request_id = str(uuid.uuid4())

        async def _insert():
            async with aiosqlite.connect(service.db_path) as db:
                await db.execute(
                    """
                    INSERT INTO approval_requests
                        (id, request_type, request_payload, reason, status,
                         requester_id, requester_name,
                         created_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request_id,
                        request_type,
                        '{"data": "test"}',
                        "unknown type test",
                        "approved",
                        "user_001",
                        "operator",
                        datetime.utcnow().isoformat(),
                        (datetime.utcnow() + timedelta(hours=1)).isoformat(),
                    ),
                )
                await db.commit()

        run_async(_insert())
        return request_id

    def test_execute_request_unknown_type_becomes_execution_failed(
        self, approval_service_with_mock_audit
    ):
        """TC077: 未知の operation_type → NotImplementedError → execution_failed（SudoWrapperError 送出）"""
        from backend.core.sudo_wrapper import SudoWrapperError

        service = approval_service_with_mock_audit
        request_id = self._insert_approved_request(service, "unknown_custom_operation")

        # execute_request は execution_failed 時に SudoWrapperError を送出する
        with pytest.raises(SudoWrapperError, match="No executor defined"):
            run_async(
                service.execute_request(
                    request_id=request_id,
                    executor_id="user_003",
                    executor_name="admin",
                    executor_role="Admin",
                )
            )

        # DB のステータスが execution_failed に更新されていることを確認
        async def check_status():
            async with aiosqlite.connect(service.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT status FROM approval_requests WHERE id = ?", (request_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    return row["status"]

        status = run_async(check_status())
        assert status == "execution_failed"

    def test_execute_request_covers_unsupported_check(
        self, approval_service_with_mock_audit
    ):
        """TC078: _UNSUPPORTED チェック行（line 655）が実行される"""
        from backend.core.sudo_wrapper import SudoWrapperError

        service = approval_service_with_mock_audit
        request_id = self._insert_approved_request(service, "another_unknown_op")

        # The dispatch function runs, hits the _UNSUPPORTED check (False), then falls
        # through to the else clause raising NotImplementedError → SudoWrapperError
        with pytest.raises(SudoWrapperError):
            run_async(
                service.execute_request(
                    request_id=request_id,
                    executor_id="user_003",
                    executor_name="admin",
                    executor_role="Admin",
                )
            )


# =====================================================================
# TC079-080: list_requests() requester_id / request_type フィルター（lines 1377-1382）
# =====================================================================


class TestListRequestsFilters:
    """list_requests() の追加フィルターパス"""

    def _create_req(self, service, requester_id, request_type="user_add", username="filter_u"):
        return run_async(
            service.create_request(
                request_type=request_type,
                payload={"username": username, "group": "dev"},
                reason="filter test",
                requester_id=requester_id,
                requester_name="operator",
                requester_role="Operator",
            )
        )

    def test_requester_id_filter(self, approval_service_with_mock_audit):
        """TC079: requester_id フィルターで該当リクエストのみ返る"""
        service = approval_service_with_mock_audit
        self._create_req(service, "user_req_filter_001", username="rf_usr1")
        result = run_async(service.list_requests(requester_id="user_req_filter_001"))
        assert result["total"] >= 1
        for req in result["requests"]:
            assert req["requester_id"] == "user_req_filter_001"

    def test_request_type_filter(self, approval_service_with_mock_audit):
        """TC080: request_type フィルターで該当種別のみ返る"""
        service = approval_service_with_mock_audit
        self._create_req(service, "user_002", request_type="user_add", username="rf_usr2")
        result = run_async(service.list_requests(request_type="user_add"))
        assert result["total"] >= 1
        for req in result["requests"]:
            assert req["request_type"] == "user_add"


# =====================================================================
# TC081-091: get_approval_history() バリデーション・フィルター（lines 1475-1512, 1543-1584）
# =====================================================================


class TestGetApprovalHistoryFilters:
    """get_approval_history() の各バリデーションとフィルターパス"""

    def _create_and_approve(self, service, username="hist_u"):
        """リクエストを作成して承認し、履歴エントリを生成する"""
        req = run_async(
            service.create_request(
                request_type="user_add",
                payload={"username": username, "group": "dev"},
                reason="history filter test",
                requester_id="user_002",
                requester_name="operator",
                requester_role="Operator",
            )
        )
        run_async(
            service.approve_request(
                request_id=req["request_id"],
                approver_id="user_003",
                approver_name="admin",
                approver_role="Admin",
            )
        )
        return req["request_id"]

    def test_per_page_low_clamped_to_1(self, approval_service_with_mock_audit):
        """TC081: per_page < 1 → 1 にクランプ（エラーなし）"""
        service = approval_service_with_mock_audit
        result = run_async(service.get_approval_history(per_page=0))
        assert isinstance(result["items"], list)
        assert result["per_page"] == 1

    def test_per_page_high_clamped_to_100(self, approval_service_with_mock_audit):
        """TC082: per_page > 100 → 100 にクランプ（エラーなし）"""
        service = approval_service_with_mock_audit
        result = run_async(service.get_approval_history(per_page=200))
        assert isinstance(result["items"], list)
        assert result["per_page"] == 100

    def test_invalid_action_raises_value_error(self, approval_service_with_mock_audit):
        """TC083: 無効な action フィルター → ValueError"""
        service = approval_service_with_mock_audit
        with pytest.raises(ValueError, match="Invalid action filter"):
            run_async(service.get_approval_history(action="invalid_action_xyz"))

    def test_request_id_filter(self, approval_service_with_mock_audit):
        """TC084: request_id フィルター"""
        service = approval_service_with_mock_audit
        request_id = self._create_and_approve(service, username="rid_filter_u")
        result = run_async(service.get_approval_history(request_id=request_id))
        assert "items" in result
        for item in result["items"]:
            assert item["approval_request_id"] == request_id

    def test_action_filter_approve(self, approval_service_with_mock_audit):
        """TC085: action='approved' フィルター"""
        service = approval_service_with_mock_audit
        self._create_and_approve(service, username="act_filter_u")
        result = run_async(service.get_approval_history(action="approved"))
        assert "items" in result
        for item in result["items"]:
            assert item["action"] == "approved"

    def test_actor_id_filter(self, approval_service_with_mock_audit):
        """TC086: actor_id フィルター"""
        service = approval_service_with_mock_audit
        self._create_and_approve(service, username="actor_filter_u")
        result = run_async(service.get_approval_history(actor_id="user_003"))
        assert "items" in result

    def test_start_date_filter(self, approval_service_with_mock_audit):
        """TC087: start_date フィルター"""
        service = approval_service_with_mock_audit
        result = run_async(service.get_approval_history(start_date="2020-01-01T00:00:00"))
        assert "items" in result

    def test_end_date_filter(self, approval_service_with_mock_audit):
        """TC088: end_date フィルター"""
        service = approval_service_with_mock_audit
        result = run_async(service.get_approval_history(end_date="2099-12-31T23:59:59"))
        assert "items" in result

    def test_request_type_filter(self, approval_service_with_mock_audit):
        """TC089: request_type フィルター"""
        service = approval_service_with_mock_audit
        self._create_and_approve(service, username="rtype_filter_u")
        result = run_async(service.get_approval_history(request_type="user_add"))
        assert "items" in result

    def test_history_items_have_expected_fields(self, approval_service_with_mock_audit):
        """TC090: 履歴アイテムに必要フィールドが含まれる（items ループ処理）"""
        service = approval_service_with_mock_audit
        self._create_and_approve(service, username="fields_u")
        result = run_async(service.get_approval_history())
        assert result["total"] >= 1
        for item in result["items"]:
            assert "action" in item
            assert "actor_id" in item
            assert "timestamp" in item
            assert "signature_valid" in item

    def test_page_low_clamped_to_1(self, approval_service_with_mock_audit):
        """TC091: page < 1 → 1 にクランプ（エラーなし）"""
        service = approval_service_with_mock_audit
        result = run_async(service.get_approval_history(page=0))
        assert isinstance(result["items"], list)
        assert result["page"] == 1


# =====================================================================
# TC092: get_approval_stats() type_counts ループ（line 1636）
# =====================================================================


class TestGetApprovalStats:
    """get_approval_stats() の type_counts ループをカバー"""

    def test_get_approval_stats_type_counts_populated(
        self, approval_service_with_mock_audit
    ):
        """TC092: リクエスト作成後に get_approval_stats() を呼び type_counts が含まれる"""
        service = approval_service_with_mock_audit
        run_async(
            service.create_request(
                request_type="user_add",
                payload={"username": "stats_usr_tc92", "group": "dev"},
                reason="stats type_counts test",
                requester_id="user_002",
                requester_name="operator",
                requester_role="Operator",
            )
        )
        result = run_async(service.get_approval_stats())
        assert "type_counts" in result
        assert "status_counts" in result
        assert "total" in result
        # type_counts リストに user_add が含まれること
        assert isinstance(result["type_counts"], list)
        type_names = [t["request_type"] for t in result["type_counts"]]
        assert "user_add" in type_names

    def test_get_approval_stats_period_filter(self, approval_service_with_mock_audit):
        """TC093: period フィルター（7d, 90d, all）が正常動作する"""
        service = approval_service_with_mock_audit
        for period in ("7d", "90d", "all"):
            result = run_async(service.get_approval_stats(period=period))
            assert "period" in result
            assert result["period"] == period


# =====================================================================
# TC094-095: get_approval_history() 例外パス（lines 1547-1548, 1578-1582）
# =====================================================================


class TestGetApprovalHistoryExceptionPaths:
    """get_approval_history() の例外パスをカバー"""

    def _insert_history_with_bad_details(self, service, request_id: str) -> None:
        """details に不正な JSON を持つ履歴レコードを直接挿入"""
        from datetime import datetime

        async def _insert():
            async with aiosqlite.connect(service.db_path) as db:
                await db.execute(
                    """
                    INSERT INTO approval_history
                        (approval_request_id, action, actor_id, actor_name,
                         actor_role, timestamp, details, previous_status, new_status,
                         signature)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request_id,
                        "created",
                        "user_001",
                        "operator",
                        "Operator",
                        datetime.utcnow().isoformat(),
                        "not-valid-json{{{",  # 不正な JSON
                        "pending",
                        "pending",
                        "a" * 64,  # 64 文字のダミー署名
                    ),
                )
                await db.commit()

        run_async(_insert())

    def _insert_request(self, service) -> str:
        """シンプルなリクエストを直接挿入して ID を返す"""
        import uuid
        from datetime import datetime, timedelta

        request_id = str(uuid.uuid4())

        async def _insert():
            async with aiosqlite.connect(service.db_path) as db:
                await db.execute(
                    """
                    INSERT INTO approval_requests
                        (id, request_type, request_payload, reason, status,
                         requester_id, requester_name, created_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request_id,
                        "user_add",
                        '{"username": "hist_exc_u"}',
                        "history exception test",
                        "pending",
                        "user_001",
                        "operator",
                        datetime.utcnow().isoformat(),
                        (datetime.utcnow() + timedelta(hours=1)).isoformat(),
                    ),
                )
                await db.commit()

        run_async(_insert())
        return request_id

    def test_history_details_json_parse_error(self, approval_service_with_mock_audit):
        """TC094: details に不正 JSON を持つ履歴レコードが正常処理される（lines 1547-1548）"""
        service = approval_service_with_mock_audit
        request_id = self._insert_request(service)
        self._insert_history_with_bad_details(service, request_id)

        result = run_async(service.get_approval_history(request_id=request_id))
        assert "items" in result
        # 不正 JSON でも items が返ること
        assert len(result["items"]) >= 1

    def test_history_signature_verification_failure(
        self, approval_service_with_mock_audit
    ):
        """TC095: HMAC 署名検証が例外を送出した場合 signature_valid=False になる（lines 1578-1582）"""
        from unittest.mock import patch

        service = approval_service_with_mock_audit
        request_id = self._insert_request(service)
        self._insert_history_with_bad_details(service, request_id)

        with patch(
            "backend.core.approval_service.verify_history_signature",
            side_effect=Exception("HMAC verification error"),
        ):
            result = run_async(service.get_approval_history(request_id=request_id))

        assert "items" in result
        for item in result["items"]:
            assert item["signature_valid"] is False


# =====================================================================
# TC-MIGA: initialize_db() マイグレーション成功パス（lines 214-215）
# =====================================================================


class TestInitializeDbMigrationSuccess:
    """execute_by カラムが存在しない旧スキーマへのマイグレーション成功（lines 214-215）"""

    def _create_old_schema_sync(self, db_path: str):
        """executed_by カラムを持たない approval_requests のみを事前作成する。

        approval_history / approval_policies はスキーマ SQL に任せることで、
        executescript が INSERT サンプルデータを正しく投入できる。
        """

        async def _setup():
            async with aiosqlite.connect(db_path) as db:
                await db.execute(
                    """
                    CREATE TABLE approval_requests (
                        id                VARCHAR(36)  PRIMARY KEY,
                        request_type      VARCHAR(50)  NOT NULL,
                        requester_id      VARCHAR(50)  NOT NULL,
                        requester_name    VARCHAR(100) NOT NULL,
                        request_payload   TEXT         NOT NULL,
                        reason            TEXT         NOT NULL,
                        status            VARCHAR(20)  NOT NULL DEFAULT 'pending',
                        created_at        TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        expires_at        TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        approved_by       VARCHAR(50)  NULL,
                        approved_by_name  VARCHAR(100) NULL,
                        approved_at       TIMESTAMP    NULL,
                        rejection_reason  TEXT         NULL,
                        execution_result  TEXT         NULL,
                        executed_at       TIMESTAMP    NULL
                    )
                    """
                )
                await db.commit()

        run_async(_setup())

    def test_migration_adds_executed_by_column(self, tmp_path):
        """旧スキーマ（executed_by なし）に initialize_db() でカラムを追加する"""
        db_path = str(tmp_path / "test_migration.db")
        self._create_old_schema_sync(db_path)

        # initialize_db() を呼び出す:
        # - executescript は CREATE TABLE IF NOT EXISTS のため approval_requests をスキップ
        # - ALTER TABLE ADD COLUMN executed_by が成功 → lines 214-215 を実行
        service = ApprovalService(db_path=db_path)
        run_async(service.initialize_db())

        # executed_by カラムが追加されていることを確認
        async def _check_column():
            async with aiosqlite.connect(db_path) as db:
                async with db.execute("PRAGMA table_info(approval_requests)") as cur:
                    return [row[1] for row in await cur.fetchall()]

        columns = run_async(_check_column())
        assert "executed_by" in columns

    def test_migration_success_log_message(self, tmp_path):
        """マイグレーション成功時のログメッセージが出力される（line 215）"""
        db_path = str(tmp_path / "test_migration_log.db")
        self._create_old_schema_sync(db_path)

        service = ApprovalService(db_path=db_path)
        with patch("backend.core.approval_service.logger") as mock_logger:
            run_async(service.initialize_db())

        # "Migrated approval_requests: added executed_by column" が記録される
        info_calls = [str(call) for call in mock_logger.info.call_args_list]
        assert any("executed_by" in msg for msg in info_calls)
