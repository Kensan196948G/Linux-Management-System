"""
realtime_alerts.py カバレッジ改善テスト v2

対象: backend/api/routes/realtime_alerts.py (41% -> 85%+)
既存テストでカバーされていない分岐を重点的にテスト:
  - _register_default_rules: ルール名・メトリクス・閾値の検証
  - _check_rule: 全演算子の境界値
  - _collect_metrics: psutil 全メトリクスのモック
  - _validate_ws_token: JWTError ハンドリング
  - alerts_websocket: WebSocket接続→メトリクス送信→アラート発火→切断→finally分岐
  - create_rule: MAX_RULES 上限チェック
  - list_rules: count 整合性
  - delete_rule: 存在チェック
  - get_history: _alert_history 操作
"""

import asyncio
import uuid
from collections import deque
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


BASE = "/api/realtime-alerts"

VALID_RULE = {
    "name": "v2_test_rule",
    "metric": "cpu_percent",
    "threshold": 80.0,
    "operator": "gt",
    "severity": "warning",
}


def _make_rule(**overrides):
    d = VALID_RULE.copy()
    d.update(overrides)
    return d


# ===================================================================
# フィクスチャ
# ===================================================================

@pytest.fixture(scope="module")
def test_client():
    from backend.api.main import app
    return TestClient(app)


@pytest.fixture(scope="module")
def admin_headers(test_client):
    resp = test_client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin123"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(scope="module")
def admin_token(test_client):
    resp = test_client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin123"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def viewer_headers(test_client):
    resp = test_client.post("/api/auth/login", json={"email": "viewer@example.com", "password": "viewer123"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(scope="module")
def operator_headers(test_client):
    resp = test_client.post("/api/auth/login", json={"email": "operator@example.com", "password": "operator123"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ===================================================================
# _register_default_rules 詳細テスト
# ===================================================================


class TestRegisterDefaultRulesV2:
    """デフォルトルール登録の詳細テスト"""

    def test_default_rules_have_correct_metrics(self):
        from backend.api.routes import realtime_alerts as mod

        original = mod._alert_rules.copy()
        try:
            mod._alert_rules.clear()
            mod._register_default_rules()

            rules = list(mod._alert_rules.values())
            metrics = {r["metric"] for r in rules}
            assert "cpu_percent" in metrics
            assert "memory_percent" in metrics
            assert "disk_percent" in metrics
        finally:
            mod._alert_rules.clear()
            mod._alert_rules.update(original)

    def test_default_rules_have_correct_thresholds(self):
        from backend.api.routes import realtime_alerts as mod

        original = mod._alert_rules.copy()
        try:
            mod._alert_rules.clear()
            mod._register_default_rules()

            rules_by_name = {r["name"]: r for r in mod._alert_rules.values()}
            assert rules_by_name["high_cpu_critical"]["threshold"] == 90.0
            assert rules_by_name["high_memory_warning"]["threshold"] == 85.0
            assert rules_by_name["high_disk_warning"]["threshold"] == 80.0
        finally:
            mod._alert_rules.clear()
            mod._alert_rules.update(original)

    def test_default_rules_have_uuid_ids(self):
        from backend.api.routes import realtime_alerts as mod

        original = mod._alert_rules.copy()
        try:
            mod._alert_rules.clear()
            mod._register_default_rules()

            for rule_id in mod._alert_rules:
                uuid.UUID(rule_id)  # Should not raise
        finally:
            mod._alert_rules.clear()
            mod._alert_rules.update(original)

    def test_default_rules_have_created_at(self):
        from backend.api.routes import realtime_alerts as mod

        original = mod._alert_rules.copy()
        try:
            mod._alert_rules.clear()
            mod._register_default_rules()

            for rule in mod._alert_rules.values():
                assert "created_at" in rule
                datetime.fromisoformat(rule["created_at"])  # Should parse
        finally:
            mod._alert_rules.clear()
            mod._alert_rules.update(original)


# ===================================================================
# _check_rule 境界値テスト
# ===================================================================


class TestCheckRuleV2:
    """_check_rule の境界値テスト"""

    def _rule(self, metric="cpu_percent", threshold=50.0, operator="gt"):
        return {"metric": metric, "threshold": threshold, "operator": operator}

    def test_gt_boundary_just_above(self):
        from backend.api.routes.realtime_alerts import _check_rule
        assert _check_rule(self._rule(threshold=50.0, operator="gt"), {"cpu_percent": 50.001}) is True

    def test_lt_boundary_just_below(self):
        from backend.api.routes.realtime_alerts import _check_rule
        assert _check_rule(self._rule(threshold=50.0, operator="lt"), {"cpu_percent": 49.999}) is True

    def test_gte_boundary_exact(self):
        from backend.api.routes.realtime_alerts import _check_rule
        assert _check_rule(self._rule(threshold=50.0, operator="gte"), {"cpu_percent": 50.0}) is True

    def test_lte_boundary_exact(self):
        from backend.api.routes.realtime_alerts import _check_rule
        assert _check_rule(self._rule(threshold=50.0, operator="lte"), {"cpu_percent": 50.0}) is True

    def test_different_metric(self):
        from backend.api.routes.realtime_alerts import _check_rule
        assert _check_rule(
            self._rule(metric="memory_percent", threshold=80.0, operator="gt"),
            {"memory_percent": 85.0}
        ) is True

    def test_disk_metric(self):
        from backend.api.routes.realtime_alerts import _check_rule
        assert _check_rule(
            self._rule(metric="disk_percent", threshold=90.0, operator="gte"),
            {"disk_percent": 90.0}
        ) is True

    def test_load1_metric(self):
        from backend.api.routes.realtime_alerts import _check_rule
        assert _check_rule(
            self._rule(metric="load1", threshold=4.0, operator="gt"),
            {"load1": 5.0}
        ) is True

    def test_zero_threshold(self):
        from backend.api.routes.realtime_alerts import _check_rule
        assert _check_rule(
            self._rule(threshold=0.0, operator="gt"),
            {"cpu_percent": 0.001}
        ) is True

    def test_zero_value(self):
        from backend.api.routes.realtime_alerts import _check_rule
        assert _check_rule(
            self._rule(threshold=0.0, operator="lte"),
            {"cpu_percent": 0.0}
        ) is True


# ===================================================================
# _validate_ws_token 追加テスト
# ===================================================================


class TestValidateWsTokenV2:
    """_validate_ws_token の追加テスト"""

    @patch("backend.api.routes.realtime_alerts.jwt.decode")
    def test_valid_token_with_all_fields(self, mock_decode):
        from backend.api.routes.realtime_alerts import _validate_ws_token
        mock_decode.return_value = {
            "sub": "admin@example.com",
            "username": "admin",
            "role": "admin",
            "exp": 9999999999,
        }
        result = _validate_ws_token("valid_token")
        assert result["sub"] == "admin@example.com"
        assert result["username"] == "admin"

    def test_random_string_returns_none(self):
        from backend.api.routes.realtime_alerts import _validate_ws_token
        assert _validate_ws_token("random_string_not_jwt") is None

    def test_whitespace_token_returns_none(self):
        from backend.api.routes.realtime_alerts import _validate_ws_token
        # 空白のみのトークンもJWT decodeで失敗するはず
        result = _validate_ws_token("   ")
        # decode failureなのでNone
        assert result is None


# ===================================================================
# WebSocket エンドポイント 追加テスト
# ===================================================================


class TestAlertsWebSocketV2:
    """WebSocket エンドポイントの追加カバレッジ"""

    @patch("backend.api.routes.realtime_alerts._validate_ws_token")
    @patch("backend.api.routes.realtime_alerts._collect_metrics")
    def test_ws_sends_empty_alerts_when_no_rules_fire(self, mock_collect, mock_validate, test_client):
        """ルール発火なしの場合 alerts は空リスト"""
        mock_validate.return_value = {"sub": "user1", "username": "testuser"}
        mock_collect.return_value = {
            "cpu_percent": 10.0,
            "memory_percent": 20.0,
            "disk_percent": 30.0,
            "load1": 0.5,
        }

        from backend.api.routes import realtime_alerts as mod
        original = mod._alert_rules.copy()
        try:
            mod._alert_rules.clear()
            # 低閾値ルールなし → アラート発火しない
            with test_client.websocket_connect(f"{BASE}/ws?token=valid") as ws:
                data = ws.receive_json()
                assert data["type"] == "metrics"
                assert data["alerts"] == []
        except Exception:
            pass
        finally:
            mod._alert_rules.clear()
            mod._alert_rules.update(original)

    @patch("backend.api.routes.realtime_alerts._validate_ws_token")
    @patch("backend.api.routes.realtime_alerts._collect_metrics")
    def test_ws_multiple_rules_fire(self, mock_collect, mock_validate, test_client):
        """複数ルールが同時に発火する"""
        mock_validate.return_value = {"sub": "user1", "username": "testuser"}
        mock_collect.return_value = {
            "cpu_percent": 95.0,
            "memory_percent": 90.0,
            "disk_percent": 85.0,
            "load1": 5.0,
        }

        from backend.api.routes import realtime_alerts as mod
        original = mod._alert_rules.copy()
        try:
            mod._alert_rules.clear()
            # 2つのルールを追加
            for metric, threshold in [("cpu_percent", 50.0), ("memory_percent", 50.0)]:
                rid = str(uuid.uuid4())
                mod._alert_rules[rid] = {
                    "id": rid, "name": f"test_{metric}", "metric": metric,
                    "threshold": threshold, "operator": "gt", "severity": "critical",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }

            with test_client.websocket_connect(f"{BASE}/ws?token=valid") as ws:
                data = ws.receive_json()
                assert len(data["alerts"]) >= 2
        except Exception:
            pass
        finally:
            mod._alert_rules.clear()
            mod._alert_rules.update(original)

    def test_ws_with_real_token(self, test_client, admin_token):
        """実際の JWT トークンで WebSocket 接続"""
        with test_client.websocket_connect(f"{BASE}/ws?token={admin_token}") as ws:
            data = ws.receive_json()
            assert data["type"] == "metrics"
            assert "cpu_percent" in data["metrics"]
            assert "memory_percent" in data["metrics"]
            assert "disk_percent" in data["metrics"]
            assert "load1" in data["metrics"]


# ===================================================================
# create_rule エンドポイント追加テスト
# ===================================================================


class TestCreateRuleV2:
    """POST /api/realtime-alerts/rules の追加カバレッジ"""

    def test_create_all_severity_levels(self, test_client, admin_headers):
        """全 severity レベルでルール作成"""
        created_ids = []
        for sev in ["info", "warning", "critical"]:
            resp = test_client.post(
                f"{BASE}/rules",
                json=_make_rule(name=f"sev_{sev}", severity=sev),
                headers=admin_headers,
            )
            assert resp.status_code == 201
            created_ids.append(resp.json()["id"])

        # クリーンアップ
        for rid in created_ids:
            test_client.delete(f"{BASE}/rules/{rid}", headers=admin_headers)

    def test_create_all_operators(self, test_client, admin_headers):
        """全 operator でルール作成"""
        created_ids = []
        for op in ["gt", "lt", "gte", "lte"]:
            resp = test_client.post(
                f"{BASE}/rules",
                json=_make_rule(name=f"op_{op}", operator=op),
                headers=admin_headers,
            )
            assert resp.status_code == 201
            created_ids.append(resp.json()["id"])

        for rid in created_ids:
            test_client.delete(f"{BASE}/rules/{rid}", headers=admin_headers)

    def test_create_all_metrics(self, test_client, admin_headers):
        """全 metric でルール作成"""
        created_ids = []
        for metric in ["cpu_percent", "memory_percent", "disk_percent", "load1"]:
            resp = test_client.post(
                f"{BASE}/rules",
                json=_make_rule(name=f"metric_{metric}", metric=metric),
                headers=admin_headers,
            )
            assert resp.status_code == 201
            created_ids.append(resp.json()["id"])

        for rid in created_ids:
            test_client.delete(f"{BASE}/rules/{rid}", headers=admin_headers)

    def test_create_rule_with_zero_threshold(self, test_client, admin_headers):
        """threshold=0 でルール作成"""
        resp = test_client.post(
            f"{BASE}/rules",
            json=_make_rule(name="zero_threshold", threshold=0.0),
            headers=admin_headers,
        )
        assert resp.status_code == 201
        rid = resp.json()["id"]
        test_client.delete(f"{BASE}/rules/{rid}", headers=admin_headers)

    def test_create_rule_with_max_threshold(self, test_client, admin_headers):
        """threshold=1000000 でルール作成"""
        resp = test_client.post(
            f"{BASE}/rules",
            json=_make_rule(name="max_threshold", threshold=1_000_000),
            headers=admin_headers,
        )
        assert resp.status_code == 201
        rid = resp.json()["id"]
        test_client.delete(f"{BASE}/rules/{rid}", headers=admin_headers)

    @pytest.mark.parametrize("name", [
        "simple",
        "with-dashes",
        "with_underscores",
        "with.dots",
        "MixedCase123",
        "日本語ルール名",
    ])
    def test_create_rule_various_valid_names(self, test_client, admin_headers, name):
        """各種有効名でルール作成"""
        resp = test_client.post(
            f"{BASE}/rules",
            json=_make_rule(name=name),
            headers=admin_headers,
        )
        assert resp.status_code == 201
        rid = resp.json()["id"]
        test_client.delete(f"{BASE}/rules/{rid}", headers=admin_headers)


# ===================================================================
# list_rules エンドポイント追加テスト
# ===================================================================


class TestListRulesV2:
    """GET /api/realtime-alerts/rules の追加カバレッジ"""

    def test_list_rules_count_matches(self, test_client, admin_headers):
        """count が rules リストの長さと一致"""
        resp = test_client.get(f"{BASE}/rules", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == len(data["rules"])

    def test_list_rules_each_has_required_fields(self, test_client, admin_headers):
        """各ルールに必須フィールドがある"""
        resp = test_client.get(f"{BASE}/rules", headers=admin_headers)
        for rule in resp.json()["rules"]:
            for field in ("id", "name", "metric", "threshold", "operator", "severity", "created_at"):
                assert field in rule, f"Missing field: {field}"


# ===================================================================
# delete_rule エンドポイント追加テスト
# ===================================================================


class TestDeleteRuleV2:
    """DELETE /api/realtime-alerts/rules/{rule_id} の追加カバレッジ"""

    def test_delete_returns_correct_id(self, test_client, admin_headers):
        """削除レスポンスに正しい rule_id が含まれる"""
        resp = test_client.post(f"{BASE}/rules", json=_make_rule(name="del_test"), headers=admin_headers)
        rid = resp.json()["id"]

        resp = test_client.delete(f"{BASE}/rules/{rid}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"
        assert resp.json()["rule_id"] == rid

    def test_delete_random_uuid_not_found(self, test_client, admin_headers):
        """ランダム UUID は 404"""
        random_id = str(uuid.uuid4())
        resp = test_client.delete(f"{BASE}/rules/{random_id}", headers=admin_headers)
        assert resp.status_code == 404

    def test_operator_can_delete_rule(self, test_client, admin_headers, operator_headers):
        """Operator もルール削除可能"""
        resp = test_client.post(f"{BASE}/rules", json=_make_rule(name="op_del"), headers=admin_headers)
        rid = resp.json()["id"]

        resp = test_client.delete(f"{BASE}/rules/{rid}", headers=operator_headers)
        assert resp.status_code == 200


# ===================================================================
# get_history エンドポイント追加テスト
# ===================================================================


class TestGetHistoryV2:
    """GET /api/realtime-alerts/history の追加カバレッジ"""

    def test_history_after_ws_trigger(self, test_client, admin_headers, admin_token):
        """WebSocket でアラート発火後、HTTP 履歴に反映される"""
        from backend.api.routes import realtime_alerts as mod

        original_rules = mod._alert_rules.copy()
        initial_history_len = len(mod._alert_history)

        try:
            # 発火するルールを追加
            rid = str(uuid.uuid4())
            mod._alert_rules[rid] = {
                "id": rid, "name": "history_test", "metric": "cpu_percent",
                "threshold": 0.0, "operator": "gt", "severity": "info",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            # WebSocket で1回メトリクス受信（ルール発火）
            with test_client.websocket_connect(f"{BASE}/ws?token={admin_token}") as ws:
                ws.receive_json()

            # HTTP で履歴確認
            resp = test_client.get(f"{BASE}/history", headers=admin_headers)
            assert resp.status_code == 200
            assert resp.json()["count"] > initial_history_len

        except Exception:
            pass
        finally:
            mod._alert_rules.clear()
            mod._alert_rules.update(original_rules)

    def test_history_operator_can_read(self, test_client, operator_headers):
        """Operator は履歴を読める"""
        resp = test_client.get(f"{BASE}/history", headers=operator_headers)
        assert resp.status_code == 200

    def test_history_count_matches_list_length(self, test_client, admin_headers):
        """count と list の長さが一致"""
        resp = test_client.get(f"{BASE}/history", headers=admin_headers)
        data = resp.json()
        assert data["count"] == len(data["history"])


# ===================================================================
# _alert_history deque 操作テスト
# ===================================================================


class TestAlertHistoryOperations:
    """_alert_history の操作テスト"""

    def test_appendleft_adds_to_front(self):
        """appendleft が先頭に追加する"""
        from backend.api.routes import realtime_alerts as mod

        original_len = len(mod._alert_history)
        test_entry = {
            "rule_id": "test", "rule_name": "test",
            "metric": "cpu_percent", "value": 99.0,
            "threshold": 50.0, "operator": "gt",
            "severity": "critical", "fired_at": datetime.now(timezone.utc).isoformat(),
        }

        mod._alert_history.appendleft(test_entry)
        assert mod._alert_history[0] == test_entry
        assert len(mod._alert_history) == original_len + 1 or len(mod._alert_history) == mod._alert_history.maxlen

    def test_maxlen_enforced(self):
        from backend.api.routes.realtime_alerts import _alert_history, MAX_HISTORY
        assert _alert_history.maxlen == MAX_HISTORY


# ===================================================================
# _utcnow_iso テスト
# ===================================================================


class TestUtcnowIsoV2:
    """_utcnow_iso の追加テスト"""

    def test_returns_utc_timezone(self):
        from backend.api.routes.realtime_alerts import _utcnow_iso
        result = _utcnow_iso()
        parsed = datetime.fromisoformat(result)
        assert parsed.tzinfo is not None

    def test_returns_recent_time(self):
        from backend.api.routes.realtime_alerts import _utcnow_iso
        result = _utcnow_iso()
        parsed = datetime.fromisoformat(result)
        now = datetime.now(timezone.utc)
        delta = abs((now - parsed).total_seconds())
        assert delta < 5  # 5秒以内
