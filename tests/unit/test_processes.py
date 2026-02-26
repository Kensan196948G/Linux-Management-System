"""
プロセス管理 API - ユニットテスト

個別関数・メソッドのロジックを検証
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.api.routes.processes import ProcessInfo, ProcessListResponse

# テスト用サンプルデータ
MOCK_PROCESS = {
    "pid": 1234,
    "user": "root",
    "cpu_percent": 10.5,
    "mem_percent": 2.3,
    "vsz": 123456,
    "rss": 12345,
    "tty": "?",
    "stat": "S",
    "start": "Jan01",
    "time": "0:01",
    "command": "/usr/bin/python3",
}

MOCK_PROCESS_RESPONSE = {
    "status": "success",
    "total_processes": 100,
    "returned_processes": 1,
    "sort_by": "cpu",
    "filters": {"user": None, "min_cpu": 0.0, "min_mem": 0.0},
    "processes": [MOCK_PROCESS],
    "timestamp": "2026-02-06T12:00:00+00:00",
}


class TestProcessListEndpoint:
    """プロセス一覧エンドポイントのユニットテスト"""

    def test_list_processes_default_params(self, test_client, auth_headers):
        """デフォルトパラメータでプロセス一覧を取得"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = MOCK_PROCESS_RESPONSE
            response = test_client.get("/api/processes", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "processes" in data
        assert data["sort_by"] == "cpu"  # デフォルト

    def test_list_processes_with_sort_by_mem(self, test_client, auth_headers):
        """メモリ使用率でソート"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = {**MOCK_PROCESS_RESPONSE, "sort_by": "mem"}
            response = test_client.get("/api/processes?sort_by=mem", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["sort_by"] == "mem"

    def test_list_processes_with_limit(self, test_client, auth_headers):
        """limit パラメータでプロセス数を制限"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = MOCK_PROCESS_RESPONSE
            response = test_client.get("/api/processes?limit=10", headers=auth_headers)

        assert response.status_code == 200
        # sudo_wrapper が limit を受け取ったか確認
        mock_get.assert_called_once_with(
            sort_by="cpu", limit=10, filter_user=None, min_cpu=0.0, min_mem=0.0
        )

    def test_list_processes_default_limit(self, test_client, auth_headers):
        """デフォルトlimitは100"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = MOCK_PROCESS_RESPONSE
            response = test_client.get("/api/processes", headers=auth_headers)

        assert response.status_code == 200
        mock_get.assert_called_once_with(
            sort_by="cpu", limit=100, filter_user=None, min_cpu=0.0, min_mem=0.0
        )

    def test_list_processes_with_filter_user(self, test_client, auth_headers):
        """ユーザー名フィルタ"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = {
                **MOCK_PROCESS_RESPONSE,
                "filters": {"user": "root", "min_cpu": 0.0, "min_mem": 0.0},
            }
            response = test_client.get(
                "/api/processes?filter_user=root", headers=auth_headers
            )

        assert response.status_code == 200

    def test_list_processes_with_min_cpu(self, test_client, auth_headers):
        """最小CPU使用率フィルタ"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = {
                **MOCK_PROCESS_RESPONSE,
                "filters": {"user": None, "min_cpu": 10.0, "min_mem": 0.0},
            }
            response = test_client.get(
                "/api/processes?min_cpu=10.0", headers=auth_headers
            )

        assert response.status_code == 200

    def test_list_processes_with_min_mem(self, test_client, auth_headers):
        """最小メモリ使用率フィルタ"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = {
                **MOCK_PROCESS_RESPONSE,
                "filters": {"user": None, "min_cpu": 0.0, "min_mem": 5.0},
            }
            response = test_client.get(
                "/api/processes?min_mem=5.0", headers=auth_headers
            )

        assert response.status_code == 200

    def test_list_processes_combined_filters(self, test_client, auth_headers):
        """複数フィルタの組み合わせ"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = MOCK_PROCESS_RESPONSE
            response = test_client.get(
                "/api/processes?sort_by=mem&limit=20&filter_user=www-data&min_cpu=1.0&min_mem=2.0",
                headers=auth_headers,
            )

        assert response.status_code == 200
        mock_get.assert_called_once_with(
            sort_by="mem", limit=20, filter_user="www-data", min_cpu=1.0, min_mem=2.0
        )


class TestProcessListValidation:
    """プロセス一覧エンドポイントの入力検証"""

    def test_reject_invalid_sort_by(self, test_client, auth_headers):
        """無効なソートキーを拒否"""
        response = test_client.get("/api/processes?sort_by=invalid", headers=auth_headers)
        assert response.status_code == 422

    def test_reject_limit_out_of_range_low(self, test_client, auth_headers):
        """limit が範囲外（下限 0）の場合は拒否"""
        response = test_client.get("/api/processes?limit=0", headers=auth_headers)
        assert response.status_code == 422

    def test_reject_limit_out_of_range_high(self, test_client, auth_headers):
        """limit が範囲外（上限 1001）の場合は拒否"""
        response = test_client.get("/api/processes?limit=1001", headers=auth_headers)
        assert response.status_code == 422

    def test_reject_invalid_filter_user_special_chars(self, test_client, auth_headers):
        """filter_user に特殊文字が含まれる場合は拒否"""
        response = test_client.get(
            "/api/processes?filter_user=root%3Bls", headers=auth_headers
        )
        assert response.status_code == 422

    def test_reject_min_cpu_out_of_range(self, test_client, auth_headers):
        """min_cpu が範囲外の場合は拒否"""
        response = test_client.get("/api/processes?min_cpu=150.0", headers=auth_headers)
        assert response.status_code == 422

    def test_reject_min_mem_out_of_range(self, test_client, auth_headers):
        """min_mem が範囲外の場合は拒否"""
        response = test_client.get("/api/processes?min_mem=101.0", headers=auth_headers)
        assert response.status_code == 422

    def test_reject_non_numeric_limit(self, test_client, auth_headers):
        """limit が非数値の場合は拒否"""
        response = test_client.get("/api/processes?limit=abc", headers=auth_headers)
        assert response.status_code == 422

    def test_valid_sort_keys_accepted(self, test_client, auth_headers):
        """有効なソートキーはすべて受け入れられる"""
        for key in ["cpu", "mem", "pid", "time"]:
            with patch(
                "backend.core.sudo_wrapper.sudo_wrapper.get_processes"
            ) as mock_get:
                mock_get.return_value = {**MOCK_PROCESS_RESPONSE, "sort_by": key}
                response = test_client.get(
                    f"/api/processes?sort_by={key}", headers=auth_headers
                )
            assert response.status_code == 200, f"sort_by={key} should be valid"


class TestProcessListAuthentication:
    """プロセス一覧エンドポイントの認証・認可テスト"""

    def test_require_authentication(self, test_client):
        """認証なしではアクセスできない"""
        response = test_client.get("/api/processes")
        assert response.status_code == 403  # Bearer token required

    def test_require_read_processes_permission(self, test_client, viewer_headers):
        """read:processes 権限を持つ Viewer はアクセス可能"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = MOCK_PROCESS_RESPONSE
            response = test_client.get("/api/processes", headers=viewer_headers)

        assert response.status_code == 200

    def test_invalid_token_rejected(self, test_client):
        """無効なトークンは拒否"""
        invalid_headers = {"Authorization": "Bearer invalid_token_12345"}
        response = test_client.get("/api/processes", headers=invalid_headers)
        assert response.status_code == 401


class TestSudoWrapperIntegration:
    """sudo_wrapper.get_processes() メソッドのテスト"""

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes")
    def test_sudo_wrapper_success(self, mock_get_processes, test_client, auth_headers):
        """sudo_wrapper が正常に動作する場合"""
        mock_get_processes.return_value = MOCK_PROCESS_RESPONSE

        response = test_client.get("/api/processes", headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "success"
        assert len(data["processes"]) == 1
        assert data["processes"][0]["pid"] == 1234

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes")
    def test_sudo_wrapper_error(self, mock_get_processes, test_client, auth_headers):
        """sudo_wrapper がエラーを返す場合"""
        mock_get_processes.return_value = {
            "status": "error",
            "message": "Permission denied",
        }

        response = test_client.get("/api/processes", headers=auth_headers)
        assert response.status_code == 403

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes")
    def test_sudo_wrapper_exception(self, mock_get_processes, test_client, auth_headers):
        """sudo_wrapper が例外を投げる場合"""
        from backend.core.sudo_wrapper import SudoWrapperError

        mock_get_processes.side_effect = SudoWrapperError("Wrapper script failed")

        response = test_client.get("/api/processes", headers=auth_headers)
        assert response.status_code == 500


class TestAuditLogRecording:
    """監査ログ記録のテスト"""

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes")
    def test_audit_log_on_success(self, mock_get_processes, test_client, auth_headers):
        """成功時の監査ログが記録される"""
        mock_get_processes.return_value = MOCK_PROCESS_RESPONSE

        with patch("backend.api.routes.processes.audit_log.record") as mock_record:
            response = test_client.get("/api/processes", headers=auth_headers)

        assert response.status_code == 200
        # 監査ログが複数回呼ばれていること（attempt + success）
        assert mock_record.call_count >= 1

    @patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes")
    def test_audit_log_on_failure(
        self, mock_get_processes, test_client, auth_headers
    ):
        """失敗時の監査ログが記録される"""
        from backend.core.sudo_wrapper import SudoWrapperError

        mock_get_processes.side_effect = SudoWrapperError("Wrapper failed")

        with patch("backend.api.routes.processes.audit_log.record") as mock_record:
            response = test_client.get("/api/processes", headers=auth_headers)

        assert response.status_code == 500
        assert mock_record.call_count >= 1


class TestProcessInfoModel:
    """ProcessInfo モデルのテスト"""

    def test_process_info_valid_data(self):
        """有効なデータでProcessInfoモデルを作成"""
        process = ProcessInfo(
            pid=1234,
            user="root",
            cpu_percent=10.5,
            mem_percent=2.3,
            vsz=123456,
            rss=12345,
            tty="?",
            stat="S",
            start="Jan01",
            time="0:01",
            command="/usr/bin/python3",
        )

        assert process.pid == 1234
        assert process.user == "root"
        assert process.cpu_percent == 10.5

    def test_process_info_zero_cpu(self):
        """CPU使用率0.0は有効"""
        process = ProcessInfo(
            pid=1,
            user="root",
            cpu_percent=0.0,
            mem_percent=0.0,
            vsz=0,
            rss=0,
            tty="?",
            stat="S",
            start="Jan01",
            time="0:00",
            command="init",
        )
        assert process.cpu_percent == 0.0


class TestProcessListResponseModel:
    """ProcessListResponse モデルのテスト"""

    def test_process_list_response_valid_data(self):
        """有効なデータでProcessListResponseモデルを作成"""
        response = ProcessListResponse(
            status="success",
            total_processes=100,
            returned_processes=1,
            sort_by="cpu",
            filters={"user": None, "min_cpu": 0.0, "min_mem": 0.0},
            processes=[
                ProcessInfo(
                    pid=1234,
                    user="root",
                    cpu_percent=10.5,
                    mem_percent=2.3,
                    vsz=123456,
                    rss=12345,
                    tty="?",
                    stat="S",
                    start="Jan01",
                    time="0:01",
                    command="/usr/bin/python3",
                )
            ],
            timestamp="2026-02-06T12:00:00+00:00",
        )

        assert response.status == "success"
        assert response.total_processes == 100
        assert len(response.processes) == 1

    def test_process_list_response_empty_processes(self):
        """プロセスリストが空でも有効"""
        response = ProcessListResponse(
            status="success",
            total_processes=0,
            returned_processes=0,
            sort_by="cpu",
            filters={},
            processes=[],
            timestamp="2026-02-06T12:00:00+00:00",
        )
        assert response.returned_processes == 0
        assert response.processes == []

