"""
Fail2ban 管理モジュール - 統合テスト

APIエンドポイントの統合テスト（sudo_wrapper / subprocess をモック）

テストケース数: 25件以上
- fail2ban なし環境での 503 対応（モック）
- jail 一覧取得（モック）
- 不正な jail 名の拒否
- 不正な IP アドレスの拒否（`;|` 含む）
- Viewer は unban 不可
- unban は audit_log 記録確認
- ban は Approver 以上のみ
- 認証テスト
"""

from unittest.mock import MagicMock, patch

import pytest

# ==============================================================================
# サンプルデータ
# ==============================================================================

SAMPLE_STATUS_OUTPUT = """\
Status
|- Number of jail:      2
`- Jail list:   sshd, nginx-auth
"""

SAMPLE_JAIL_LIST_OUTPUT = "sshd\nnginx-auth\n"

SAMPLE_JAIL_STATUS_OUTPUT = """\
Status for the jail: sshd
|- Filter
|  |- Currently failed: 3
|  |- Total failed:     120
|  `- File list:        /var/log/auth.log
`- Actions
   |- Currently banned: 5
   |- Total banned:     42
   `- Banned IP list:   192.168.1.10 10.0.0.5
"""

SAMPLE_BANNED_IPS_OUTPUT = "192.168.1.10\n10.0.0.5\n"

SAMPLE_UNBAN_OUTPUT = "1\n"
SAMPLE_BAN_OUTPUT = "1\n"
SAMPLE_RELOAD_OUTPUT = "OK\n"


def _make_wrapper_result(output: str) -> dict:
    """sudo_wrapper の返値形式を作成する"""
    return {"status": "success", "output": output}


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
def approver_headers(test_client):
    """Approver ユーザーの認証ヘッダー"""
    resp = test_client.post("/api/auth/login", json={"email": "approver@example.com", "password": "approver123"})
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
# TC001-TC005: 認証なしアクセス（401/403）
# ==============================================================================


class TestFail2banUnauthorized:
    """認証なしアクセスは 403 を返すこと"""

    def test_status_no_auth(self, test_client):
        """TC001: GET /api/fail2ban/status — 認証なしは 403"""
        resp = test_client.get("/api/fail2ban/status")
        assert resp.status_code == 403

    def test_jails_no_auth(self, test_client):
        """TC002: GET /api/fail2ban/jails — 認証なしは 403"""
        resp = test_client.get("/api/fail2ban/jails")
        assert resp.status_code == 403

    def test_jail_detail_no_auth(self, test_client):
        """TC003: GET /api/fail2ban/jails/sshd — 認証なしは 403"""
        resp = test_client.get("/api/fail2ban/jails/sshd")
        assert resp.status_code == 403

    def test_banned_ips_no_auth(self, test_client):
        """TC004: GET /api/fail2ban/jails/sshd/banned — 認証なしは 403"""
        resp = test_client.get("/api/fail2ban/jails/sshd/banned")
        assert resp.status_code == 403

    def test_summary_no_auth(self, test_client):
        """TC005: GET /api/fail2ban/summary — 認証なしは 403"""
        resp = test_client.get("/api/fail2ban/summary")
        assert resp.status_code == 403


# ==============================================================================
# TC006-TC010: fail2ban なし環境での 503
# ==============================================================================


class TestFail2banNotInstalled:
    """fail2ban がインストールされていない環境では 503 を返すこと"""

    def _run_not_found(self, *args, **kwargs):
        """which fail2ban-client が失敗する mock"""
        m = MagicMock()
        m.returncode = 1
        return m

    def test_status_503_when_not_installed(self, test_client, admin_headers):
        """TC006: fail2ban-client がない場合は 503"""
        with patch("backend.api.routes.fail2ban.subprocess.run", side_effect=self._run_not_found):
            resp = test_client.get("/api/fail2ban/status", headers=admin_headers)
        assert resp.status_code == 503

    def test_jails_503_when_not_installed(self, test_client, admin_headers):
        """TC007: fail2ban-client がない場合 jail 一覧も 503"""
        with patch("backend.api.routes.fail2ban.subprocess.run", side_effect=self._run_not_found):
            resp = test_client.get("/api/fail2ban/jails", headers=admin_headers)
        assert resp.status_code == 503

    def test_jail_detail_503_when_not_installed(self, test_client, admin_headers):
        """TC008: fail2ban-client がない場合 jail 詳細も 503"""
        with patch("backend.api.routes.fail2ban.subprocess.run", side_effect=self._run_not_found):
            resp = test_client.get("/api/fail2ban/jails/sshd", headers=admin_headers)
        assert resp.status_code == 503

    def test_summary_503_when_not_installed(self, test_client, admin_headers):
        """TC009: fail2ban-client がない場合 summary も 503"""
        with patch("backend.api.routes.fail2ban.subprocess.run", side_effect=self._run_not_found):
            resp = test_client.get("/api/fail2ban/summary", headers=admin_headers)
        assert resp.status_code == 503

    def test_reload_503_when_not_installed(self, test_client, admin_headers):
        """TC010: fail2ban-client がない場合 reload も 503"""
        with patch("backend.api.routes.fail2ban.subprocess.run", side_effect=self._run_not_found):
            resp = test_client.post("/api/fail2ban/reload", headers=admin_headers)
        assert resp.status_code == 503


# ==============================================================================
# TC011-TC015: 正常系
# ==============================================================================


def _mock_which_ok(*args, **kwargs):
    """which fail2ban-client が成功する mock"""
    m = MagicMock()
    m.returncode = 0
    m.stdout = "/usr/bin/fail2ban-client"
    return m


class TestFail2banSuccess:
    """正常系テスト"""

    def test_get_status_success(self, test_client, admin_headers):
        """TC011: fail2ban status 取得成功"""
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()), patch(
            "backend.api.routes.fail2ban._run_fail2ban",
            return_value=_make_wrapper_result(SAMPLE_STATUS_OUTPUT),
        ):
            resp = test_client.get("/api/fail2ban/status", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "output" in data

    def test_get_jails_success(self, test_client, admin_headers):
        """TC012: jail 一覧取得成功"""
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()), patch(
            "backend.api.routes.fail2ban._run_fail2ban",
            return_value=_make_wrapper_result(SAMPLE_JAIL_LIST_OUTPUT),
        ):
            resp = test_client.get("/api/fail2ban/jails", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "sshd" in data["jails"]
        assert "nginx-auth" in data["jails"]
        assert data["total"] == 2

    def test_get_jail_detail_success(self, test_client, admin_headers):
        """TC013: jail 詳細取得成功"""
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()), patch(
            "backend.api.routes.fail2ban._run_fail2ban",
            return_value=_make_wrapper_result(SAMPLE_JAIL_STATUS_OUTPUT),
        ):
            resp = test_client.get("/api/fail2ban/jails/sshd", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["jail"]["name"] == "sshd"
        assert data["jail"]["currently_banned"] == 5
        assert data["jail"]["total_failed"] == 120

    def test_get_banned_ips_success(self, test_client, admin_headers):
        """TC014: 禁止 IP 一覧取得成功"""
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()), patch(
            "backend.api.routes.fail2ban._run_fail2ban",
            return_value=_make_wrapper_result(SAMPLE_BANNED_IPS_OUTPUT),
        ):
            resp = test_client.get("/api/fail2ban/jails/sshd/banned", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "192.168.1.10" in data["banned_ips"]
        assert data["total"] == 2

    def test_get_summary_success(self, test_client, admin_headers):
        """TC015: サマリー取得成功"""
        list_result = _make_wrapper_result(SAMPLE_JAIL_LIST_OUTPUT)
        detail_result = _make_wrapper_result(SAMPLE_JAIL_STATUS_OUTPUT)

        call_count = 0

        def _mock_run(cmd, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return list_result
            return detail_result

        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()), patch(
            "backend.api.routes.fail2ban._run_fail2ban", side_effect=_mock_run
        ):
            resp = test_client.get("/api/fail2ban/summary", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["jail_count"] == 2


# ==============================================================================
# TC016-TC018: 不正な jail 名の拒否
# ==============================================================================


class TestFail2banJailNameValidation:
    """不正な jail 名はバリデーションエラーを返すこと"""

    def test_reject_jail_name_with_semicolon(self, test_client, admin_headers):
        """TC016: セミコロンを含む jail 名を拒否（400）"""
        resp = test_client.get("/api/fail2ban/jails/sshd;evil/banned", headers=admin_headers)
        # FastAPI のパスパラメータはセミコロンを含む場合パス自体が一致しないか 400
        assert resp.status_code in (400, 404, 422)

    def test_reject_jail_name_with_pipe(self, test_client, admin_headers):
        """TC017: パイプを含む jail 名を拒否（400）"""
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()):
            resp = test_client.get("/api/fail2ban/jails/sshd|evil", headers=admin_headers)
        assert resp.status_code in (400, 404, 422)

    def test_reject_jail_name_too_long(self, test_client, admin_headers):
        """TC018: 65 文字以上の jail 名を拒否（400）"""
        long_name = "a" * 65
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()):
            resp = test_client.get(f"/api/fail2ban/jails/{long_name}", headers=admin_headers)
        assert resp.status_code == 400


# ==============================================================================
# TC019-TC021: 不正な IP アドレスの拒否
# ==============================================================================


class TestFail2banIPValidation:
    """不正な IP アドレスはバリデーションエラーを返すこと"""

    def test_reject_ip_with_semicolon(self, test_client, operator_headers):
        """TC019: セミコロンを含む IP を unban リクエストで拒否（422）"""
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()):
            resp = test_client.post(
                "/api/fail2ban/jails/sshd/unban",
                json={"ip": "192.168.1.1;evil"},
                headers=operator_headers,
            )
        assert resp.status_code == 422

    def test_reject_ip_with_pipe(self, test_client, operator_headers):
        """TC020: パイプを含む IP を unban リクエストで拒否（422）"""
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()):
            resp = test_client.post(
                "/api/fail2ban/jails/sshd/unban",
                json={"ip": "192.168.1.1|evil"},
                headers=operator_headers,
            )
        assert resp.status_code == 422

    def test_reject_invalid_ip_format(self, test_client, operator_headers):
        """TC021: 不正な IP フォーマット（ドメイン名）を拒否（422）"""
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()):
            resp = test_client.post(
                "/api/fail2ban/jails/sshd/unban",
                json={"ip": "evil.example.com"},
                headers=operator_headers,
            )
        assert resp.status_code == 422


# ==============================================================================
# TC022-TC023: 権限テスト - Viewer は unban 不可
# ==============================================================================


class TestFail2banPermissions:
    """権限テスト"""

    def test_viewer_cannot_unban(self, test_client, viewer_headers):
        """TC022: Viewer は unban 不可（403）"""
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()):
            resp = test_client.post(
                "/api/fail2ban/jails/sshd/unban",
                json={"ip": "192.168.1.10"},
                headers=viewer_headers,
            )
        assert resp.status_code == 403

    def test_viewer_cannot_ban(self, test_client, viewer_headers):
        """TC023: Viewer は ban 不可（403）"""
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()):
            resp = test_client.post(
                "/api/fail2ban/jails/sshd/ban",
                json={"ip": "192.168.1.10"},
                headers=viewer_headers,
            )
        assert resp.status_code == 403

    def test_operator_cannot_ban(self, test_client, operator_headers):
        """TC024: Operator は ban 不可（admin:fail2ban が必要）（403）"""
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()):
            resp = test_client.post(
                "/api/fail2ban/jails/sshd/ban",
                json={"ip": "192.168.1.10"},
                headers=operator_headers,
            )
        assert resp.status_code == 403

    def test_operator_can_unban(self, test_client, operator_headers):
        """TC025: Operator は unban 可（write:fail2ban あり）"""
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()), patch(
            "backend.api.routes.fail2ban._run_fail2ban",
            return_value=_make_wrapper_result(SAMPLE_UNBAN_OUTPUT),
        ):
            resp = test_client.post(
                "/api/fail2ban/jails/sshd/unban",
                json={"ip": "192.168.1.10"},
                headers=operator_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "unban"
        assert data["ip"] == "192.168.1.10"

    def test_approver_can_ban(self, test_client, approver_headers):
        """TC026: Approver は ban 可（admin:fail2ban あり）"""
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()), patch(
            "backend.api.routes.fail2ban._run_fail2ban",
            return_value=_make_wrapper_result(SAMPLE_BAN_OUTPUT),
        ):
            resp = test_client.post(
                "/api/fail2ban/jails/sshd/ban",
                json={"ip": "10.0.0.99"},
                headers=approver_headers,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "ban"
        assert data["ip"] == "10.0.0.99"

    def test_admin_can_reload(self, test_client, admin_headers):
        """TC027: Admin は reload 可（admin:fail2ban あり）"""
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()), patch(
            "backend.api.routes.fail2ban._run_fail2ban",
            return_value=_make_wrapper_result(SAMPLE_RELOAD_OUTPUT),
        ):
            resp = test_client.post("/api/fail2ban/reload", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"

    def test_operator_cannot_reload(self, test_client, operator_headers):
        """TC028: Operator は reload 不可（admin:fail2ban が必要）"""
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()):
            resp = test_client.post("/api/fail2ban/reload", headers=operator_headers)
        assert resp.status_code == 403


# ==============================================================================
# TC029-TC030: audit_log 記録確認
# ==============================================================================


class TestFail2banAuditLog:
    """unban/ban 操作が audit_log に記録されること"""

    def test_unban_records_audit_log(self, test_client, operator_headers):
        """TC029: unban 操作が audit_log に記録されること"""
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()), patch(
            "backend.api.routes.fail2ban._run_fail2ban",
            return_value=_make_wrapper_result(SAMPLE_UNBAN_OUTPUT),
        ), patch("backend.api.routes.fail2ban.audit_log.record") as mock_record:
            resp = test_client.post(
                "/api/fail2ban/jails/sshd/unban",
                json={"ip": "192.168.1.10"},
                headers=operator_headers,
            )
        assert resp.status_code == 200
        mock_record.assert_called_once()
        call_kwargs = mock_record.call_args
        args = call_kwargs[1] if call_kwargs[1] else {}
        # キーワード引数チェック
        assert call_kwargs is not None
        # operation が fail2ban_unban であることを確認
        call_args_list = mock_record.call_args_list
        assert len(call_args_list) == 1
        called_with = call_args_list[0]
        assert "fail2ban_unban" in str(called_with)

    def test_ban_records_audit_log(self, test_client, approver_headers):
        """TC030: ban 操作が audit_log に記録されること"""
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()), patch(
            "backend.api.routes.fail2ban._run_fail2ban",
            return_value=_make_wrapper_result(SAMPLE_BAN_OUTPUT),
        ), patch("backend.api.routes.fail2ban.audit_log.record") as mock_record:
            resp = test_client.post(
                "/api/fail2ban/jails/sshd/ban",
                json={"ip": "10.0.0.99"},
                headers=approver_headers,
            )
        assert resp.status_code == 200
        mock_record.assert_called_once()
        call_args_list = mock_record.call_args_list
        assert "fail2ban_ban" in str(call_args_list[0])


# ==============================================================================
# TC031: Viewer は読み取り系は利用可
# ==============================================================================


class TestFail2banViewerRead:
    """Viewer は読み取り系エンドポイントにアクセス可能"""

    def test_viewer_can_read_status(self, test_client, viewer_headers):
        """TC031: Viewer は status 取得可"""
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()), patch(
            "backend.api.routes.fail2ban._run_fail2ban",
            return_value=_make_wrapper_result(SAMPLE_STATUS_OUTPUT),
        ):
            resp = test_client.get("/api/fail2ban/status", headers=viewer_headers)
        assert resp.status_code == 200

    def test_viewer_can_read_jails(self, test_client, viewer_headers):
        """TC032: Viewer は jail 一覧取得可"""
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()), patch(
            "backend.api.routes.fail2ban._run_fail2ban",
            return_value=_make_wrapper_result(SAMPLE_JAIL_LIST_OUTPUT),
        ):
            resp = test_client.get("/api/fail2ban/jails", headers=viewer_headers)
        assert resp.status_code == 200
