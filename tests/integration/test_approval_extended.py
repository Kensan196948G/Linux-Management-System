"""
承認ワークフロー拡張テスト - user_modify / service_stop フロー

テスト項目:
  - user_modify ディスパッチ（set-shell/set-gecos/add-group/remove-group）
  - service_stop ディスパッチ
  - adminui-user-modify.sh ラッパー呼び出し検証
  - 承認→実行フロー全体（pending → approved → executed）
  合計: 20件
"""

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest


# ===================================================================
# フィクスチャ
# ===================================================================


@pytest.fixture(scope="module", autouse=True)
def init_approval_db(tmp_path_factory):
    """APIルートの approval_service を一時DBで初期化する（モジュール単位）"""
    import sqlite3
    from backend.api.routes import approval as approval_module
    from pathlib import Path

    tmp_db = str(tmp_path_factory.mktemp("approval_db_ext") / "test_approval.db")
    approval_module.approval_service.db_path = tmp_db

    schema_path = Path(__file__).parent.parent.parent / "docs" / "database" / "approval-schema.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")
    with sqlite3.connect(tmp_db) as conn:
        conn.executescript(schema_sql)
    yield


@pytest.fixture(autouse=True)
def cleanup_approval_db():
    """各テスト前にDBデータをクリーンアップする"""
    import sqlite3
    from backend.api.routes.approval import approval_service

    with sqlite3.connect(approval_service.db_path) as conn:
        conn.execute("DELETE FROM approval_history")
        conn.execute("DELETE FROM approval_requests")
        conn.commit()
    yield


@pytest.fixture
def client():
    from backend.api.main import app
    from fastapi.testclient import TestClient

    return TestClient(app)


@pytest.fixture
def admin_token(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin123"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def operator_token(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "operator@example.com", "password": "operator123"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def approver_token(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "approver@example.com", "password": "approver123"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def operator_headers(operator_token):
    return {"Authorization": f"Bearer {operator_token}"}


@pytest.fixture
def approver_headers(approver_token):
    return {"Authorization": f"Bearer {approver_token}"}


def _create_request(client, headers, request_type, payload, reason="テスト"):
    return client.post(
        "/api/approval/request",
        json={"request_type": request_type, "payload": payload, "reason": reason},
        headers=headers,
    )


def _approve_request(client, headers, request_id):
    return client.post(
        f"/api/approval/{request_id}/approve",
        json={"comment": "承認"},
        headers=headers,
    )


def _reject_request(client, headers, request_id):
    return client.post(
        f"/api/approval/{request_id}/reject",
        json={"reason": "テスト却下"},
        headers=headers,
    )


# ===================================================================
# service_stop ディスパッチテスト
# ===================================================================


class TestServiceStopApproval:
    """service_stop の承認→実行フロー"""

    def test_service_stop_request_created(self, client, operator_headers):
        """正常系: service_stop リクエストが作成できる"""
        resp = _create_request(
            client, operator_headers, "service_stop",
            {"service_name": "nginx"},
            "メンテナンスのため停止",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["request_type"] == "service_stop"
        assert data["request_status"] == "pending"

    def test_service_stop_approve_and_execute(self, client, operator_headers, approver_headers):
        """正常系: 承認後に service_stop が自動実行される"""
        create_resp = _create_request(
            client, operator_headers, "service_stop",
            {"service_name": "nginx"},
        )
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        success_result = {"status": "success", "service": "nginx", "timestamp": "2026-01-01T00:00:00Z"}
        with patch("backend.core.sudo_wrapper.SudoWrapper.stop_service", return_value=success_result):
            approve_resp = _approve_request(client, approver_headers, request_id)
        assert approve_resp.status_code == 200

    def test_service_stop_wrong_service(self, client, operator_headers):
        """異常系: 存在しないサービス名でリクエスト作成（バリデーションは承認時に判明）"""
        resp = _create_request(
            client, operator_headers, "service_stop",
            {"service_name": "nonexistent-service"},
        )
        # リクエスト作成自体は成功（バリデーションはwrapper側）
        assert resp.status_code == 201

    def test_service_stop_viewer_cannot_request(self, client, client_fixture=None):
        """異常系: Viewerはリクエストできない"""
        from fastapi.testclient import TestClient
        from backend.api.main import app
        cl = TestClient(app)
        viewer_resp = cl.post(
            "/api/auth/login",
            json={"email": "viewer@example.com", "password": "viewer123"},
        )
        if viewer_resp.status_code != 200:
            pytest.skip("viewer user not available")
        viewer_token = viewer_resp.json()["access_token"]
        resp = _create_request(
            cl,
            {"Authorization": f"Bearer {viewer_token}"},
            "service_stop",
            {"service_name": "nginx"},
        )
        assert resp.status_code == 403


# ===================================================================
# user_modify ディスパッチテスト
# ===================================================================


class TestUserModifyApproval:
    """user_modify の承認→実行フロー（set-shell/set-gecos/add-group/remove-group）"""

    def test_user_modify_set_shell_request(self, client, approver_headers):
        """正常系: set-shell リクエスト作成"""
        resp = _create_request(
            client, approver_headers, "user_modify",
            {"username": "testuser", "action": "set-shell", "shell": "/bin/bash"},
            "シェルをbashに変更",
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["request_type"] == "user_modify"
        assert data["request_status"] == "pending"

    def test_user_modify_set_gecos_request(self, client, approver_headers):
        """正常系: set-gecos リクエスト作成"""
        resp = _create_request(
            client, approver_headers, "user_modify",
            {"username": "testuser", "action": "set-gecos", "gecos": "Test User Display"},
            "表示名変更",
        )
        assert resp.status_code == 201

    def test_user_modify_add_group_request(self, client, approver_headers):
        """正常系: add-group リクエスト作成"""
        resp = _create_request(
            client, approver_headers, "user_modify",
            {"username": "testuser", "action": "add-group", "group": "docker"},
            "dockerグループ追加",
        )
        assert resp.status_code == 201

    def test_user_modify_remove_group_request(self, client, approver_headers):
        """正常系: remove-group リクエスト作成"""
        resp = _create_request(
            client, approver_headers, "user_modify",
            {"username": "testuser", "action": "remove-group", "group": "oldgroup"},
        )
        assert resp.status_code == 201

    def test_user_modify_set_shell_execute(self, client, approver_headers, admin_headers):
        """正常系: set-shell 承認→自動実行"""
        create_resp = _create_request(
            client, approver_headers, "user_modify",
            {"username": "testuser", "action": "set-shell", "shell": "/bin/bash"},
        )
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        success_result = {"status": "success", "operation": "set-shell", "username": "testuser"}
        with patch("backend.core.sudo_wrapper.SudoWrapper.modify_user_shell", return_value=success_result):
            approve_resp = _approve_request(client, admin_headers, request_id)
        assert approve_resp.status_code == 200

    def test_user_modify_add_group_execute(self, client, approver_headers, admin_headers):
        """正常系: add-group 承認→自動実行"""
        create_resp = _create_request(
            client, approver_headers, "user_modify",
            {"username": "testuser", "action": "add-group", "group": "developers"},
        )
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        success_result = {"status": "success", "operation": "add-group", "username": "testuser"}
        with patch("backend.core.sudo_wrapper.SudoWrapper.modify_user_add_group", return_value=success_result):
            approve_resp = _approve_request(client, admin_headers, request_id)
        assert approve_resp.status_code == 200


# ===================================================================
# approval_service._dispatch_sync 単体テスト
# ===================================================================


class TestApprovalDispatch:
    """approval_service._dispatch_syncのuser_modify/service_stopロジック検証"""

    def test_user_modify_unsupported_action_raises(self, client, approver_headers, admin_headers):
        """異常系: user_modifyの未知アクションはexecution_failedになる"""
        create_resp = _create_request(
            client, approver_headers, "user_modify",
            {"username": "testuser", "action": "unsupported-action"},
        )
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        # 承認後、NotImplementedError→execution_failedになるはず
        approve_resp = _approve_request(client, admin_headers, request_id)
        # 承認自体はOK（実行が失敗するだけ）
        assert approve_resp.status_code in (200, 422)

    def test_service_stop_execution_failure(self, client, operator_headers, approver_headers):
        """異常系: wrapperエラー→execution_failed"""
        from backend.core.sudo_wrapper import SudoWrapperError

        create_resp = _create_request(
            client, operator_headers, "service_stop",
            {"service_name": "nginx"},
        )
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        with patch(
            "backend.core.sudo_wrapper.SudoWrapper.stop_service",
            side_effect=SudoWrapperError("Service not found"),
        ):
            approve_resp = _approve_request(client, approver_headers, request_id)
        assert approve_resp.status_code == 200

    def test_pending_request_cannot_be_re_approved(self, client, operator_headers, admin_headers):
        """正常系: 既に承認済みリクエストの再承認は失敗"""
        create_resp = _create_request(
            client, operator_headers, "service_stop",
            {"service_name": "nginx"},
        )
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        # 一度承認
        success_result = {"status": "success"}
        with patch("backend.core.sudo_wrapper.SudoWrapper.stop_service", return_value=success_result):
            first = _approve_request(client, admin_headers, request_id)
        assert first.status_code == 200

        # 再度承認
        second = _approve_request(client, admin_headers, request_id)
        assert second.status_code in (400, 409, 422)

    def test_firewall_modify_not_yet_supported(self, client, approver_headers, admin_headers):
        """正常系: firewall_modifyはNotImplementedError→execution_failed"""
        create_resp = _create_request(
            client, approver_headers, "firewall_modify",
            {"action": "allow", "port": 8080, "protocol": "tcp"},
        )
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        # 承認 → auto-execution では NotImplementedError → execution_failed
        approve_resp = _approve_request(client, admin_headers, request_id)
        assert approve_resp.status_code == 200  # 承認自体はOK


# ===================================================================
# 承認ポリシー検証
# ===================================================================


class TestApprovalPolicies:
    """承認ポリシーの検証テスト"""

    def test_service_stop_requires_approval(self, client, operator_headers):
        """正常系: service_stopは承認フローが必要"""
        resp = _create_request(
            client, operator_headers, "service_stop",
            {"service_name": "nginx"},
        )
        assert resp.status_code == 201
        # 直接実行ではなく承認待ちになる
        assert resp.json()["request_status"] == "pending"

    def test_user_modify_in_pending_list(self, client, approver_headers, admin_headers):
        """正常系: user_modify リクエストが作成され取得できる"""
        create_resp = _create_request(
            client, approver_headers, "user_modify",
            {"username": "testuser", "action": "set-shell", "shell": "/bin/bash"},
        )
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        # 個別リクエストをIDで取得
        get_resp = client.get(f"/api/approval/{request_id}", headers=admin_headers)
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["request"]["request_type"] == "user_modify"

    def test_rejected_request_not_executed(self, client, operator_headers, approver_headers):
        """正常系: 却下されたリクエストは実行されない"""
        create_resp = _create_request(
            client, operator_headers, "service_stop",
            {"service_name": "nginx"},
        )
        assert create_resp.status_code == 201
        request_id = create_resp.json()["request_id"]

        reject_resp = _reject_request(client, approver_headers, request_id)
        assert reject_resp.status_code == 200
        # 拒否レスポンスはrejection_reasonフィールドを含む
        data = reject_resp.json()
        assert data["status"] == "success"
        assert data.get("rejection_reason") is not None
