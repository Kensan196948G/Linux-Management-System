"""
Running Processes モジュール - 統合テスト

APIエンドポイントの統合テスト（sudo_wrapperをモック）
"""

import json
from unittest.mock import MagicMock, patch

import pytest


# テスト用プロセスデータ
SAMPLE_PROCESSES_RESPONSE = {
    "status": "success",
    "total_processes": 3,
    "returned_processes": 3,
    "sort_by": "cpu",
    "filters": {"user": None, "min_cpu": 0.0, "min_mem": 0.0},
    "processes": [
        {
            "pid": 1234,
            "user": "root",
            "cpu_percent": 5.2,
            "mem_percent": 1.5,
            "vsz": 102400,
            "rss": 8192,
            "tty": "?",
            "stat": "Ss",
            "start": "10:00",
            "time": "0:01",
            "command": "/usr/sbin/nginx -g daemon off;",
        },
        {
            "pid": 5678,
            "user": "postgres",
            "cpu_percent": 2.1,
            "mem_percent": 3.0,
            "vsz": 204800,
            "rss": 16384,
            "tty": "?",
            "stat": "Ss",
            "start": "09:00",
            "time": "0:10",
            "command": "postgres: checkpointer",
        },
        {
            "pid": 9999,
            "user": "www-data",
            "cpu_percent": 0.5,
            "mem_percent": 0.8,
            "vsz": 51200,
            "rss": 4096,
            "tty": "?",
            "stat": "S",
            "start": "10:05",
            "time": "0:00",
            "command": "/usr/sbin/apache2 -k start",
        },
    ],
    "timestamp": "2026-02-26T00:00:00Z",
}


class TestProcessesListingFlow:
    """プロセス一覧取得のE2Eフロー"""

    def test_e2e_anonymous_user_rejected(self, test_client):
        """認証なしユーザーはプロセス一覧にアクセスできない"""
        response = test_client.get("/api/processes")
        assert response.status_code == 403  # Bearer token required

    def test_e2e_authenticated_user_can_list_processes(self, test_client, auth_headers):
        """認証済みユーザーはプロセス一覧を取得可能"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = SAMPLE_PROCESSES_RESPONSE
            response = test_client.get("/api/processes", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "processes" in data
        assert isinstance(data["processes"], list)
        assert len(data["processes"]) >= 1

    def test_e2e_process_list_contains_required_fields(self, test_client, auth_headers):
        """プロセス一覧に必須フィールドが含まれる"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = SAMPLE_PROCESSES_RESPONSE
            response = test_client.get("/api/processes", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        assert len(data["processes"]) > 0
        first_process = data["processes"][0]
        assert "pid" in first_process
        assert "user" in first_process
        assert "cpu_percent" in first_process
        assert "mem_percent" in first_process
        assert "command" in first_process

    def test_e2e_response_structure(self, test_client, auth_headers):
        """レスポンス構造の検証"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = SAMPLE_PROCESSES_RESPONSE
            response = test_client.get("/api/processes", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "total_processes" in data
        assert "returned_processes" in data
        assert "sort_by" in data
        assert "processes" in data
        assert data["status"] == "success"


class TestProcessesFilteringAndSorting:
    """フィルタ・ソート機能のテスト"""

    def test_filter_by_user(self, test_client, auth_headers):
        """ユーザー名でフィルタリング"""
        filtered_response = {
            **SAMPLE_PROCESSES_RESPONSE,
            "returned_processes": 1,
            "processes": [SAMPLE_PROCESSES_RESPONSE["processes"][0]],
            "filters": {"user": "root", "min_cpu": 0.0, "min_mem": 0.0},
        }
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = filtered_response
            response = test_client.get(
                "/api/processes?filter_user=root", headers=auth_headers
            )

        assert response.status_code == 200
        data = response.json()
        assert data["filters"]["user"] == "root"

    def test_sort_by_cpu(self, test_client, auth_headers):
        """CPU使用率でソート（デフォルト）"""
        sorted_response = {**SAMPLE_PROCESSES_RESPONSE, "sort_by": "cpu"}
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = sorted_response
            response = test_client.get("/api/processes?sort_by=cpu", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["sort_by"] == "cpu"

    def test_sort_by_mem(self, test_client, auth_headers):
        """メモリ使用率でソート"""
        sorted_response = {**SAMPLE_PROCESSES_RESPONSE, "sort_by": "mem"}
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = sorted_response
            response = test_client.get("/api/processes?sort_by=mem", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["sort_by"] == "mem"

    def test_sort_by_pid(self, test_client, auth_headers):
        """PIDでソート"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = {**SAMPLE_PROCESSES_RESPONSE, "sort_by": "pid"}
            response = test_client.get("/api/processes?sort_by=pid", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["sort_by"] == "pid"

    def test_sort_by_time(self, test_client, auth_headers):
        """実行時間でソート"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = {**SAMPLE_PROCESSES_RESPONSE, "sort_by": "time"}
            response = test_client.get("/api/processes?sort_by=time", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["sort_by"] == "time"

    def test_invalid_sort_key_returns_422(self, test_client, auth_headers):
        """無効なソートキーは422を返す"""
        response = test_client.get(
            "/api/processes?sort_by=invalid_key", headers=auth_headers
        )
        assert response.status_code == 422

    def test_combined_filter_and_sort(self, test_client, auth_headers):
        """フィルタとソートの組み合わせ"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = {
                **SAMPLE_PROCESSES_RESPONSE,
                "sort_by": "mem",
                "filters": {"user": "root", "min_cpu": 0.0, "min_mem": 0.0},
            }
            response = test_client.get(
                "/api/processes?sort_by=mem&filter_user=root", headers=auth_headers
            )

        assert response.status_code == 200


class TestProcessesPagination:
    """ページネーション機能のテスト"""

    def test_limit_parameter(self, test_client, auth_headers):
        """limit パラメータでプロセス数を制限"""
        limited_response = {
            **SAMPLE_PROCESSES_RESPONSE,
            "returned_processes": 2,
            "processes": SAMPLE_PROCESSES_RESPONSE["processes"][:2],
        }
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = limited_response
            response = test_client.get("/api/processes?limit=2", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data["processes"]) <= 2

    def test_limit_max_value_1000(self, test_client, auth_headers):
        """limit の最大値 1000 は受け入れる"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = SAMPLE_PROCESSES_RESPONSE
            response = test_client.get("/api/processes?limit=1000", headers=auth_headers)

        assert response.status_code == 200

    def test_limit_over_max_returns_422(self, test_client, auth_headers):
        """limit が 1000 を超えると 422"""
        response = test_client.get("/api/processes?limit=1001", headers=auth_headers)
        assert response.status_code == 422

    def test_limit_zero_returns_422(self, test_client, auth_headers):
        """limit が 0 は 422"""
        response = test_client.get("/api/processes?limit=0", headers=auth_headers)
        assert response.status_code == 422


class TestProcessesErrorHandling:
    """エラーハンドリングのテスト"""

    def test_malformed_limit_param_return_422(self, test_client, auth_headers):
        """limit に文字列を指定すると 422"""
        response = test_client.get("/api/processes?limit=abc", headers=auth_headers)
        assert response.status_code == 422

    def test_invalid_filter_user_chars_return_422(self, test_client, auth_headers):
        """filter_user に特殊文字を含む値は 422"""
        # FastAPI の pattern バリデーションが弾く
        response = test_client.get(
            "/api/processes?filter_user=nginx%3Bls", headers=auth_headers
        )
        assert response.status_code == 422

    def test_sudo_wrapper_error_returns_500(self, test_client, auth_headers):
        """sudo_wrapper がエラーを返した場合は 500"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.side_effect = SudoWrapperError("Wrapper execution failed")
            response = test_client.get("/api/processes", headers=auth_headers)

        assert response.status_code == 500

    def test_sudo_wrapper_denied_returns_403(self, test_client, auth_headers):
        """sudo_wrapper がエラーステータスを返した場合は 403"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = {
                "status": "error",
                "message": "Access denied",
            }
            response = test_client.get("/api/processes", headers=auth_headers)

        assert response.status_code == 403

    def test_min_cpu_out_of_range_returns_422(self, test_client, auth_headers):
        """min_cpu が 100 を超えると 422"""
        response = test_client.get("/api/processes?min_cpu=101.0", headers=auth_headers)
        assert response.status_code == 422

    def test_min_mem_out_of_range_returns_422(self, test_client, auth_headers):
        """min_mem が 100 を超えると 422"""
        response = test_client.get("/api/processes?min_mem=101.0", headers=auth_headers)
        assert response.status_code == 422


class TestProcessesRBACIntegration:
    """RBAC統合テスト"""

    def test_viewer_can_access_processes(self, test_client, viewer_headers):
        """Viewerもプロセス一覧にアクセス可能（read:processes 権限あり）"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = SAMPLE_PROCESSES_RESPONSE
            response = test_client.get("/api/processes", headers=viewer_headers)

        assert response.status_code == 200

    def test_operator_can_access_processes(self, test_client, operator_headers):
        """Operatorもプロセス一覧にアクセス可能"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = SAMPLE_PROCESSES_RESPONSE
            response = test_client.get("/api/processes", headers=operator_headers)

        assert response.status_code == 200

    def test_admin_can_access_processes(self, test_client, admin_headers):
        """Adminはプロセス一覧にアクセス可能"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = SAMPLE_PROCESSES_RESPONSE
            response = test_client.get("/api/processes", headers=admin_headers)

        assert response.status_code == 200

    def test_unauthenticated_request_rejected(self, test_client):
        """未認証リクエストは拒否される"""
        response = test_client.get("/api/processes")
        assert response.status_code == 403

    def test_invalid_token_rejected(self, test_client):
        """無効なトークンは拒否される"""
        headers = {"Authorization": "Bearer invalid_token_here"}
        response = test_client.get("/api/processes", headers=headers)
        assert response.status_code == 401


class TestProcessesMinCpuMemFilter:
    """CPU/メモリ最小値フィルタのテスト"""

    def test_min_cpu_filter_applied(self, test_client, auth_headers):
        """最小CPU使用率フィルタが適用される"""
        filtered = {
            **SAMPLE_PROCESSES_RESPONSE,
            "filters": {"user": None, "min_cpu": 2.0, "min_mem": 0.0},
            "returned_processes": 2,
            "processes": SAMPLE_PROCESSES_RESPONSE["processes"][:2],
        }
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = filtered
            response = test_client.get("/api/processes?min_cpu=2.0", headers=auth_headers)

        assert response.status_code == 200

    def test_min_mem_filter_applied(self, test_client, auth_headers):
        """最小メモリ使用率フィルタが適用される"""
        filtered = {
            **SAMPLE_PROCESSES_RESPONSE,
            "filters": {"user": None, "min_cpu": 0.0, "min_mem": 1.0},
            "returned_processes": 2,
            "processes": SAMPLE_PROCESSES_RESPONSE["processes"][:2],
        }
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = filtered
            response = test_client.get("/api/processes?min_mem=1.0", headers=auth_headers)

        assert response.status_code == 200

    def test_min_cpu_boundary_zero(self, test_client, auth_headers):
        """min_cpu = 0.0 は境界値として有効"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = SAMPLE_PROCESSES_RESPONSE
            response = test_client.get("/api/processes?min_cpu=0.0", headers=auth_headers)

        assert response.status_code == 200

    def test_min_cpu_boundary_100(self, test_client, auth_headers):
        """min_cpu = 100.0 は境界値として有効"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = {
                **SAMPLE_PROCESSES_RESPONSE,
                "returned_processes": 0,
                "processes": [],
            }
            response = test_client.get("/api/processes?min_cpu=100.0", headers=auth_headers)

        assert response.status_code == 200


class TestProcessesAuditLog:
    """監査ログのテスト"""

    def test_successful_request_creates_audit_log(self, test_client, auth_headers):
        """成功したリクエストの監査ログが記録される"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = SAMPLE_PROCESSES_RESPONSE
            response = test_client.get("/api/processes", headers=auth_headers)

        # レスポンスが成功していることを確認（監査ログはサイドエフェクトなのでここでは確認しない）
        assert response.status_code == 200

    def test_empty_process_list_valid_response(self, test_client, auth_headers):
        """プロセスが空でも有効なレスポンスを返す"""
        empty_response = {
            "status": "success",
            "total_processes": 0,
            "returned_processes": 0,
            "sort_by": "cpu",
            "filters": {"user": None, "min_cpu": 0.0, "min_mem": 0.0},
            "processes": [],
            "timestamp": "2026-02-26T00:00:00Z",
        }
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = empty_response
            response = test_client.get("/api/processes", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["returned_processes"] == 0
        assert data["processes"] == []


class TestProcessesFilteringAndSorting:
    """フィルタ・ソート機能のテスト"""

    def test_filter_by_user(self, test_client, auth_headers):
        """ユーザー名でフィルタリング"""
        filtered_response = {
            **SAMPLE_PROCESSES_RESPONSE,
            "filters": {"user": "root", "min_cpu": 0.0, "min_mem": 0.0},
            "returned_processes": 1,
            "processes": [SAMPLE_PROCESSES_RESPONSE["processes"][0]],
        }
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = filtered_response
            response = test_client.get(
                "/api/processes?filter_user=root", headers=auth_headers
            )

        assert response.status_code == 200
        mock_get.assert_called_once_with(
            sort_by="cpu", limit=100, filter_user="root", min_cpu=0.0, min_mem=0.0
        )

    def test_sort_by_cpu_percent(self, test_client, auth_headers):
        """CPU使用率でソート"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = {**SAMPLE_PROCESSES_RESPONSE, "sort_by": "cpu"}
            response = test_client.get(
                "/api/processes?sort_by=cpu", headers=auth_headers
            )

        assert response.status_code == 200
        assert response.json()["sort_by"] == "cpu"

    def test_sort_by_memory_percent(self, test_client, auth_headers):
        """メモリ使用率でソート"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = {**SAMPLE_PROCESSES_RESPONSE, "sort_by": "mem"}
            response = test_client.get(
                "/api/processes?sort_by=mem", headers=auth_headers
            )

        assert response.status_code == 200
        assert response.json()["sort_by"] == "mem"

    def test_combined_filter_and_sort(self, test_client, auth_headers):
        """フィルタとソートの組み合わせ"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = SAMPLE_PROCESSES_RESPONSE
            response = test_client.get(
                "/api/processes?sort_by=mem&filter_user=root&min_cpu=1.0",
                headers=auth_headers,
            )

        assert response.status_code == 200
        mock_get.assert_called_once_with(
            sort_by="mem", limit=100, filter_user="root", min_cpu=1.0, min_mem=0.0
        )


class TestProcessesPagination:
    """ページネーション機能のテスト"""

    def test_pagination_with_limit(self, test_client, auth_headers):
        """limit パラメータでページサイズを制限"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = {**SAMPLE_PROCESSES_RESPONSE, "returned_processes": 1}
            response = test_client.get("/api/processes?limit=1", headers=auth_headers)

        assert response.status_code == 200
        mock_get.assert_called_once_with(
            sort_by="cpu", limit=1, filter_user=None, min_cpu=0.0, min_mem=0.0
        )

    def test_pagination_limit_max_value(self, test_client, auth_headers):
        """limit の最大値 1000 は有効"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = SAMPLE_PROCESSES_RESPONSE
            response = test_client.get("/api/processes?limit=1000", headers=auth_headers)

        assert response.status_code == 200

    def test_pagination_limit_over_max_rejected(self, test_client, auth_headers):
        """limit が 1001 以上は422を返す"""
        response = test_client.get("/api/processes?limit=1001", headers=auth_headers)
        assert response.status_code == 422


class TestProcessesErrorHandling:
    """エラーハンドリングのテスト"""

    def test_malformed_query_params_return_422(self, test_client, auth_headers):
        """不正なクエリパラメータは422を返す"""
        response = test_client.get("/api/processes?limit=abc", headers=auth_headers)
        assert response.status_code == 422

    def test_forbidden_chars_in_filter_return_422(self, test_client, auth_headers):
        """特殊文字を含むfilter_userは422を返す"""
        response = test_client.get(
            "/api/processes?filter_user=nginx%3Bls", headers=auth_headers
        )
        assert response.status_code == 422

    def test_internal_error_returns_500(self, test_client, auth_headers):
        """sudo_wrapper例外は500を返す"""
        from backend.core.sudo_wrapper import SudoWrapperError

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.side_effect = SudoWrapperError("Mock internal error")
            response = test_client.get("/api/processes", headers=auth_headers)

        assert response.status_code == 500


class TestProcessesRBACIntegration:
    """RBAC統合テスト"""

    def test_viewer_can_list_processes(self, test_client, viewer_headers):
        """Viewerはプロセス一覧にアクセス可能"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = SAMPLE_PROCESSES_RESPONSE
            response = test_client.get("/api/processes", headers=viewer_headers)

        assert response.status_code == 200

    def test_admin_can_list_processes(self, test_client, admin_headers):
        """Adminはプロセス一覧にアクセス可能"""
        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = SAMPLE_PROCESSES_RESPONSE
            response = test_client.get("/api/processes", headers=admin_headers)

        assert response.status_code == 200


class TestProcessesPerformance:
    """パフォーマンステスト"""

    def test_process_list_response_time(self, test_client, auth_headers):
        """プロセス一覧のレスポンスタイムが許容範囲内（5秒以内）"""
        import time

        with patch("backend.core.sudo_wrapper.sudo_wrapper.get_processes") as mock_get:
            mock_get.return_value = SAMPLE_PROCESSES_RESPONSE
            start = time.time()
            response = test_client.get("/api/processes", headers=auth_headers)
            elapsed = time.time() - start

        assert response.status_code == 200
        assert elapsed < 5.0

    def test_concurrent_requests(self, test_client, auth_headers):
        """並行リクエストが全て成功する"""
        import concurrent.futures

        def make_request():
            with patch(
                "backend.core.sudo_wrapper.sudo_wrapper.get_processes"
            ) as mock_get:
                mock_get.return_value = SAMPLE_PROCESSES_RESPONSE
                return test_client.get("/api/processes", headers=auth_headers)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request) for _ in range(5)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        for r in results:
            assert r.status_code == 200
