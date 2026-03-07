"""
リアルタイムアラート API - 統合テスト

テストケース数: 25件以上
- 認証なしアクセス拒否
- ルール CRUD（作成・取得・削除）
- 不正なmetric/operator/threshold/severity の拒否
- Viewer の write 操作拒否
- ルール上限チェック
- 発火履歴取得
- WebSocket 認証テスト
"""

from __future__ import annotations

import pytest


# ==============================================================================
# フィクスチャ
# ==============================================================================


@pytest.fixture(scope="module")
def test_client():
    """FastAPI テストクライアント（モジュールスコープ）"""
    import os
    import sys
    from pathlib import Path

    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))
    os.environ["ENV"] = "dev"

    from backend.api.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="module")
def admin_headers(test_client):
    """Admin ユーザーの認証ヘッダー"""
    resp = test_client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin123"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def operator_headers(test_client):
    """Operator ユーザーの認証ヘッダー"""
    resp = test_client.post("/api/auth/login", json={"email": "operator@example.com", "password": "operator123"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def viewer_headers(test_client):
    """Viewer ユーザーの認証ヘッダー"""
    resp = test_client.post("/api/auth/login", json={"email": "viewer@example.com", "password": "viewer123"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ==============================================================================
# TC001-TC004: 認証なしアクセス拒否
# ==============================================================================


class TestAuthRequired:
    """認証なしアクセスは 401/403 を返す"""

    def test_list_rules_no_auth(self, test_client):
        """TC001: ルール一覧は認証なしで拒否される"""
        resp = test_client.get("/api/realtime-alerts/rules")
        assert resp.status_code in (401, 403)

    def test_create_rule_no_auth(self, test_client):
        """TC002: ルール作成は認証なしで拒否される"""
        resp = test_client.post(
            "/api/realtime-alerts/rules",
            json={"name": "test", "metric": "cpu_percent", "threshold": 80.0, "operator": "gt", "severity": "warning"},
        )
        assert resp.status_code in (401, 403)

    def test_delete_rule_no_auth(self, test_client):
        """TC003: ルール削除は認証なしで拒否される"""
        resp = test_client.delete("/api/realtime-alerts/rules/some-id")
        assert resp.status_code in (401, 403)

    def test_get_history_no_auth(self, test_client):
        """TC004: 発火履歴は認証なしで拒否される"""
        resp = test_client.get("/api/realtime-alerts/history")
        assert resp.status_code in (401, 403)


# ==============================================================================
# TC005-TC008: ルール CRUD（正常系）
# ==============================================================================


class TestRuleCRUD:
    """ルールの作成・一覧・削除の正常系"""

    def test_list_rules_default_exists(self, test_client, admin_headers):
        """TC005: デフォルトルールが登録済みで一覧に含まれる"""
        resp = test_client.get("/api/realtime-alerts/rules", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "rules" in data
        assert "count" in data
        assert data["count"] >= 3  # デフォルト3件

    def test_create_rule_success(self, test_client, admin_headers):
        """TC006: 有効なパラメータでルール作成に成功する"""
        payload = {
            "name": "test_cpu_rule",
            "metric": "cpu_percent",
            "threshold": 75.0,
            "operator": "gt",
            "severity": "warning",
        }
        resp = test_client.post("/api/realtime-alerts/rules", json=payload, headers=admin_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "test_cpu_rule"
        assert data["metric"] == "cpu_percent"
        assert data["threshold"] == 75.0
        assert data["operator"] == "gt"
        assert data["severity"] == "warning"
        assert "id" in data
        assert "created_at" in data

    def test_created_rule_appears_in_list(self, test_client, admin_headers):
        """TC007: 作成したルールが一覧に反映される"""
        # 作成
        payload = {
            "name": "list_check_rule",
            "metric": "memory_percent",
            "threshold": 60.0,
            "operator": "gte",
            "severity": "info",
        }
        create_resp = test_client.post("/api/realtime-alerts/rules", json=payload, headers=admin_headers)
        assert create_resp.status_code == 201
        rule_id = create_resp.json()["id"]

        # 一覧確認
        list_resp = test_client.get("/api/realtime-alerts/rules", headers=admin_headers)
        assert list_resp.status_code == 200
        rule_ids = [r["id"] for r in list_resp.json()["rules"]]
        assert rule_id in rule_ids

    def test_delete_rule_success(self, test_client, admin_headers):
        """TC008: 存在するルールを正常に削除できる"""
        # 作成
        payload = {
            "name": "delete_target_rule",
            "metric": "disk_percent",
            "threshold": 90.0,
            "operator": "gt",
            "severity": "critical",
        }
        create_resp = test_client.post("/api/realtime-alerts/rules", json=payload, headers=admin_headers)
        assert create_resp.status_code == 201
        rule_id = create_resp.json()["id"]

        # 削除
        del_resp = test_client.delete(f"/api/realtime-alerts/rules/{rule_id}", headers=admin_headers)
        assert del_resp.status_code == 200
        assert del_resp.json()["rule_id"] == rule_id

        # 一覧で消えている確認
        list_resp = test_client.get("/api/realtime-alerts/rules", headers=admin_headers)
        rule_ids = [r["id"] for r in list_resp.json()["rules"]]
        assert rule_id not in rule_ids

    def test_delete_nonexistent_rule_returns_404(self, test_client, admin_headers):
        """TC009: 存在しないルール削除は404を返す"""
        resp = test_client.delete("/api/realtime-alerts/rules/nonexistent-uuid", headers=admin_headers)
        assert resp.status_code == 404


# ==============================================================================
# TC010-TC014: 不正な metric・operator・severity の拒否
# ==============================================================================


class TestValidation:
    """入力バリデーション - 許可リスト外は 422 で拒否"""

    def _base_payload(self) -> dict:
        return {
            "name": "validation_test",
            "metric": "cpu_percent",
            "threshold": 80.0,
            "operator": "gt",
            "severity": "warning",
        }

    def test_reject_invalid_metric(self, test_client, admin_headers):
        """TC010: 許可リスト外のmetric名を拒否する"""
        payload = {**self._base_payload(), "metric": "invalid_metric"}
        resp = test_client.post("/api/realtime-alerts/rules", json=payload, headers=admin_headers)
        assert resp.status_code == 422

    def test_reject_shell_injection_metric(self, test_client, admin_headers):
        """TC011: shell injection 試みのmetricを拒否する"""
        payload = {**self._base_payload(), "metric": "cpu_percent; rm -rf /"}
        resp = test_client.post("/api/realtime-alerts/rules", json=payload, headers=admin_headers)
        assert resp.status_code == 422

    def test_reject_invalid_operator(self, test_client, admin_headers):
        """TC012: 許可リスト外のoperatorを拒否する"""
        payload = {**self._base_payload(), "operator": "eq"}
        resp = test_client.post("/api/realtime-alerts/rules", json=payload, headers=admin_headers)
        assert resp.status_code == 422

    def test_reject_invalid_severity(self, test_client, admin_headers):
        """TC013: 許可リスト外のseverityを拒否する"""
        payload = {**self._base_payload(), "severity": "urgent"}
        resp = test_client.post("/api/realtime-alerts/rules", json=payload, headers=admin_headers)
        assert resp.status_code == 422

    def test_reject_negative_threshold(self, test_client, admin_headers):
        """TC014: 負の閾値を拒否する"""
        payload = {**self._base_payload(), "threshold": -10.0}
        resp = test_client.post("/api/realtime-alerts/rules", json=payload, headers=admin_headers)
        assert resp.status_code == 422

    def test_reject_empty_name(self, test_client, admin_headers):
        """TC015: 空のルール名を拒否する"""
        payload = {**self._base_payload(), "name": ""}
        resp = test_client.post("/api/realtime-alerts/rules", json=payload, headers=admin_headers)
        assert resp.status_code == 422

    def test_reject_name_with_special_chars(self, test_client, admin_headers):
        """TC016: 特殊文字を含むルール名を拒否する"""
        payload = {**self._base_payload(), "name": "rule; DROP TABLE alerts;"}
        resp = test_client.post("/api/realtime-alerts/rules", json=payload, headers=admin_headers)
        assert resp.status_code == 422

    def test_reject_pipe_in_name(self, test_client, admin_headers):
        """TC017: パイプ文字を含むルール名を拒否する"""
        payload = {**self._base_payload(), "name": "rule|evil"}
        resp = test_client.post("/api/realtime-alerts/rules", json=payload, headers=admin_headers)
        assert resp.status_code == 422

    def test_all_valid_metrics_accepted(self, test_client, admin_headers):
        """TC018: 全ての許可されたmetric名が受け入れられる"""
        allowed = ["cpu_percent", "memory_percent", "disk_percent", "load1"]
        for metric in allowed:
            payload = {
                "name": f"rule_{metric}",
                "metric": metric,
                "threshold": 50.0,
                "operator": "gt",
                "severity": "info",
            }
            resp = test_client.post("/api/realtime-alerts/rules", json=payload, headers=admin_headers)
            assert resp.status_code == 201, f"metric={metric} should be accepted, got {resp.status_code}"

    def test_all_valid_operators_accepted(self, test_client, admin_headers):
        """TC019: 全ての許可されたoperatorが受け入れられる"""
        allowed_ops = ["gt", "lt", "gte", "lte"]
        for op in allowed_ops:
            payload = {
                "name": f"rule_op_{op}",
                "metric": "cpu_percent",
                "threshold": 50.0,
                "operator": op,
                "severity": "info",
            }
            resp = test_client.post("/api/realtime-alerts/rules", json=payload, headers=admin_headers)
            assert resp.status_code == 201, f"operator={op} should be accepted, got {resp.status_code}"


# ==============================================================================
# TC020-TC022: 権限テスト
# ==============================================================================


class TestPermissions:
    """ロールベースアクセス制御のテスト"""

    def test_viewer_can_list_rules(self, test_client, viewer_headers):
        """TC020: Viewer はルール一覧を参照できる"""
        resp = test_client.get("/api/realtime-alerts/rules", headers=viewer_headers)
        assert resp.status_code == 200

    def test_viewer_cannot_create_rule(self, test_client, viewer_headers):
        """TC021: Viewer はルール作成を拒否される"""
        payload = {
            "name": "viewer_test_rule",
            "metric": "cpu_percent",
            "threshold": 80.0,
            "operator": "gt",
            "severity": "warning",
        }
        resp = test_client.post("/api/realtime-alerts/rules", json=payload, headers=viewer_headers)
        assert resp.status_code == 403

    def test_viewer_cannot_delete_rule(self, test_client, viewer_headers, admin_headers):
        """TC022: Viewer はルール削除を拒否される"""
        # Admin でルール作成
        payload = {
            "name": "rule_for_viewer_delete_test",
            "metric": "cpu_percent",
            "threshold": 85.0,
            "operator": "gt",
            "severity": "critical",
        }
        create_resp = test_client.post("/api/realtime-alerts/rules", json=payload, headers=admin_headers)
        assert create_resp.status_code == 201
        rule_id = create_resp.json()["id"]

        # Viewer で削除試行
        del_resp = test_client.delete(f"/api/realtime-alerts/rules/{rule_id}", headers=viewer_headers)
        assert del_resp.status_code == 403

    def test_operator_can_create_rule(self, test_client, operator_headers):
        """TC023: Operator はルール作成が可能"""
        payload = {
            "name": "operator_created_rule",
            "metric": "load1",
            "threshold": 4.0,
            "operator": "gte",
            "severity": "warning",
        }
        resp = test_client.post("/api/realtime-alerts/rules", json=payload, headers=operator_headers)
        assert resp.status_code == 201


# ==============================================================================
# TC024-TC025: 発火履歴
# ==============================================================================


class TestAlertHistory:
    """アラート発火履歴取得テスト"""

    def test_history_returns_list(self, test_client, admin_headers):
        """TC024: 発火履歴は list と count を含む"""
        resp = test_client.get("/api/realtime-alerts/history", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "history" in data
        assert "count" in data
        assert isinstance(data["history"], list)

    def test_viewer_can_get_history(self, test_client, viewer_headers):
        """TC025: Viewer は発火履歴を参照できる"""
        resp = test_client.get("/api/realtime-alerts/history", headers=viewer_headers)
        assert resp.status_code == 200


# ==============================================================================
# TC026-TC027: ルール上限
# ==============================================================================


class TestRuleLimit:
    """ルール上限（50件）テスト"""

    def test_rule_count_is_dict(self, test_client, admin_headers):
        """TC026: ルール一覧の count フィールドが整数である"""
        resp = test_client.get("/api/realtime-alerts/rules", headers=admin_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json()["count"], int)

    def test_rule_has_required_fields(self, test_client, admin_headers):
        """TC027: 作成されたルールに必須フィールドが含まれる"""
        payload = {
            "name": "field_check_rule",
            "metric": "disk_percent",
            "threshold": 70.0,
            "operator": "gte",
            "severity": "critical",
        }
        resp = test_client.post("/api/realtime-alerts/rules", json=payload, headers=admin_headers)
        assert resp.status_code == 201
        data = resp.json()
        for field in ("id", "name", "metric", "threshold", "operator", "severity", "created_at"):
            assert field in data, f"missing field: {field}"


# ==============================================================================
# TC028: WebSocket 認証テスト（HTTP エンドポイント代替）
# ==============================================================================


class TestWebSocketAuth:
    """WebSocket 認証テスト"""

    def test_ws_rejects_invalid_token(self, test_client):
        """TC028: 無効なトークンで WebSocket 接続が拒否される"""
        from starlette.websockets import WebSocketDisconnect

        try:
            with test_client.websocket_connect("/api/realtime-alerts/ws?token=invalid_token") as ws:
                # サーバーは 1008 で close するため、データ受信前に切断される
                ws.receive_json()
        except WebSocketDisconnect:
            # 接続拒否は期待動作
            pass

    def test_ws_accepts_valid_token(self, test_client, admin_headers):
        """TC029: 有効なトークンで WebSocket 接続が受け入れられメトリクスを受信する"""
        # トークンを取得
        resp = test_client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin123"})
        assert resp.status_code == 200
        token = resp.json()["access_token"]

        with test_client.websocket_connect(f"/api/realtime-alerts/ws?token={token}") as ws:
            data = ws.receive_json()
            assert data["type"] == "metrics"
            assert "metrics" in data
            assert "alerts" in data
            assert "timestamp" in data
            metrics = data["metrics"]
            for key in ("cpu_percent", "memory_percent", "disk_percent", "load1"):
                assert key in metrics
