"""
fail2ban.py カバレッジ改善テスト

未カバー行を重点的にテスト:
- _check_fail2ban_available: TimeoutExpired パス
- _run_fail2ban: ip 引数付き呼び出し
- _parse_jail_status: 様々な出力パース
- _validate_ip: IPv6 アドレス / 境界値
- _validate_jail_name: 正常な名前 / 特殊文字
- get_summary: 個別 jail status エラー時のフォールバック
- SudoWrapperError パス: 各エンドポイント
- ban/unban の SudoWrapperError パス（audit_log failure 記録）
- reload の SudoWrapperError パス（audit_log failure 記録）
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.api.routes.fail2ban import (
    _check_fail2ban_available,
    _parse_jail_status,
    _validate_ip,
    _validate_jail_name,
)
from backend.core.sudo_wrapper import SudoWrapperError


# ===================================================================
# フィクスチャ
# ===================================================================


@pytest.fixture(scope="module")
def test_client():
    import os
    import sys
    from pathlib import Path

    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))
    os.environ["ENV"] = "dev"

    from backend.api.main import app

    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="module")
def admin_headers(test_client):
    resp = test_client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin123"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(scope="module")
def approver_headers(test_client):
    resp = test_client.post("/api/auth/login", json={"email": "approver@example.com", "password": "approver123"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(scope="module")
def operator_headers(test_client):
    resp = test_client.post("/api/auth/login", json={"email": "operator@example.com", "password": "operator123"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(scope="module")
def viewer_headers(test_client):
    resp = test_client.post("/api/auth/login", json={"email": "viewer@example.com", "password": "viewer123"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _mock_which_ok(*args, **kwargs):
    m = MagicMock()
    m.returncode = 0
    m.stdout = "/usr/bin/fail2ban-client"
    return m


def _make_wrapper_result(output: str) -> dict:
    return {"status": "success", "output": output}


# ===================================================================
# _validate_jail_name 直接テスト
# ===================================================================


class TestValidateJailName:
    """_validate_jail_name のテスト"""

    @pytest.mark.parametrize("name", ["sshd", "nginx-auth", "my_jail_01", "a" * 64])
    def test_valid_jail_names(self, name):
        """正常な jail 名は通過すること"""
        assert _validate_jail_name(name) == name

    @pytest.mark.parametrize("name", [
        "sshd;evil",
        "jail|pipe",
        "jail&amp",
        "jail$var",
        "jail`cmd`",
        "../traversal",
        "jail name",  # スペース
        "",  # 空文字列
        "a" * 65,  # 長すぎる
    ])
    def test_invalid_jail_names_rejected(self, name):
        """不正な jail 名は HTTPException を送出すること"""
        with pytest.raises(HTTPException) as exc:
            _validate_jail_name(name)
        assert exc.value.status_code == 400


# ===================================================================
# _validate_ip 直接テスト
# ===================================================================


class TestValidateIP:
    """_validate_ip のテスト"""

    @pytest.mark.parametrize("ip", [
        "192.168.1.1",
        "10.0.0.1",
        "255.255.255.255",
        "0.0.0.0",
        "::1",  # IPv6 loopback
        "2001:db8::1",  # IPv6
        "fe80::1",
    ])
    def test_valid_ips(self, ip):
        """正常な IP アドレスは通過すること"""
        assert _validate_ip(ip) == ip

    @pytest.mark.parametrize("ip", [
        "not.an.ip",
        "192.168.1.1;evil",
        "192.168.1.1|pipe",
        "evil.example.com",
        "192.168.1",  # 不完全
        "",  # 空
    ])
    def test_invalid_ips_rejected(self, ip):
        """不正な IP アドレスは HTTPException を送出すること"""
        with pytest.raises(HTTPException) as exc:
            _validate_ip(ip)
        assert exc.value.status_code == 400


# ===================================================================
# _check_fail2ban_available 直接テスト
# ===================================================================


class TestCheckFail2banAvailable:
    """_check_fail2ban_available のテスト"""

    def test_available_returns_none(self):
        """fail2ban-client が見つかる場合は何も返さない（例外なし）"""
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()):
            _check_fail2ban_available()  # Should not raise

    def test_not_available_raises_503(self):
        """fail2ban-client が見つからない場合は 503 を送出すること"""
        mock = MagicMock()
        mock.returncode = 1
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=mock):
            with pytest.raises(HTTPException) as exc:
                _check_fail2ban_available()
            assert exc.value.status_code == 503

    def test_timeout_raises_503(self):
        """タイムアウト時に 503 を送出すること"""
        with patch(
            "backend.api.routes.fail2ban.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="which", timeout=5),
        ):
            with pytest.raises(HTTPException) as exc:
                _check_fail2ban_available()
            assert exc.value.status_code == 503
            assert "timed out" in exc.value.detail


# ===================================================================
# _parse_jail_status 直接テスト
# ===================================================================


class TestParseJailStatus:
    """_parse_jail_status のテスト"""

    def test_parse_complete_output(self):
        """完全な出力を正しくパースすること"""
        raw = """\
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
        info = _parse_jail_status("sshd", raw)
        assert info.name == "sshd"
        assert info.currently_failed == 3
        assert info.total_failed == 120
        assert info.currently_banned == 5
        assert info.total_banned == 42

    def test_parse_empty_output(self):
        """空文字列でもデフォルト値でパースされること"""
        info = _parse_jail_status("test-jail", "")
        assert info.name == "test-jail"
        assert info.currently_failed == 0
        assert info.total_failed == 0
        assert info.currently_banned == 0
        assert info.total_banned == 0

    def test_parse_partial_output(self):
        """一部のみの出力でもパースできること"""
        raw = "Currently failed: 7\nTotal failed: 50\n"
        info = _parse_jail_status("partial", raw)
        assert info.currently_failed == 7
        assert info.total_failed == 50
        assert info.currently_banned == 0


# ===================================================================
# SudoWrapperError パス: 各エンドポイント
# ===================================================================


class TestFail2banSudoWrapperErrors:
    """各エンドポイントの SudoWrapperError 処理テスト"""

    def test_status_sudo_error_503(self, test_client, admin_headers):
        """GET /status — SudoWrapperError → 503"""
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()):
            with patch("backend.api.routes.fail2ban._run_fail2ban", side_effect=SudoWrapperError("connection refused")):
                resp = test_client.get("/api/fail2ban/status", headers=admin_headers)
        assert resp.status_code == 503

    def test_jails_sudo_error_503(self, test_client, admin_headers):
        """GET /jails — SudoWrapperError → 503"""
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()):
            with patch("backend.api.routes.fail2ban._run_fail2ban", side_effect=SudoWrapperError("failed")):
                resp = test_client.get("/api/fail2ban/jails", headers=admin_headers)
        assert resp.status_code == 503

    def test_jail_detail_sudo_error_503(self, test_client, admin_headers):
        """GET /jails/{name} — SudoWrapperError → 503"""
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()):
            with patch("backend.api.routes.fail2ban._run_fail2ban", side_effect=SudoWrapperError("failed")):
                resp = test_client.get("/api/fail2ban/jails/sshd", headers=admin_headers)
        assert resp.status_code == 503

    def test_banned_ips_sudo_error_503(self, test_client, admin_headers):
        """GET /jails/{name}/banned — SudoWrapperError → 503"""
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()):
            with patch("backend.api.routes.fail2ban._run_fail2ban", side_effect=SudoWrapperError("failed")):
                resp = test_client.get("/api/fail2ban/jails/sshd/banned", headers=admin_headers)
        assert resp.status_code == 503

    def test_unban_sudo_error_503_with_audit(self, test_client, operator_headers):
        """POST /jails/{name}/unban — SudoWrapperError → 503 + audit failure"""
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()):
            with patch("backend.api.routes.fail2ban._run_fail2ban", side_effect=SudoWrapperError("unban failed")):
                with patch("backend.api.routes.fail2ban.audit_log.record") as mock_audit:
                    resp = test_client.post(
                        "/api/fail2ban/jails/sshd/unban",
                        json={"ip": "192.168.1.10"},
                        headers=operator_headers,
                    )
        assert resp.status_code == 503
        # audit_log に failure が記録されること
        calls = mock_audit.call_args_list
        failure_calls = [c for c in calls if "failure" in str(c)]
        assert len(failure_calls) >= 1

    def test_ban_sudo_error_503_with_audit(self, test_client, admin_headers):
        """POST /jails/{name}/ban — SudoWrapperError → 503 + audit failure"""
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()):
            with patch("backend.api.routes.fail2ban._run_fail2ban", side_effect=SudoWrapperError("ban failed")):
                with patch("backend.api.routes.fail2ban.audit_log.record") as mock_audit:
                    resp = test_client.post(
                        "/api/fail2ban/jails/sshd/ban",
                        json={"ip": "192.168.1.10"},
                        headers=admin_headers,
                    )
        assert resp.status_code == 503
        calls = mock_audit.call_args_list
        failure_calls = [c for c in calls if "failure" in str(c)]
        assert len(failure_calls) >= 1

    def test_reload_sudo_error_503_with_audit(self, test_client, admin_headers):
        """POST /reload — SudoWrapperError → 503 + audit failure"""
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()):
            with patch("backend.api.routes.fail2ban._run_fail2ban", side_effect=SudoWrapperError("reload failed")):
                with patch("backend.api.routes.fail2ban.audit_log.record") as mock_audit:
                    resp = test_client.post("/api/fail2ban/reload", headers=admin_headers)
        assert resp.status_code == 503
        calls = mock_audit.call_args_list
        failure_calls = [c for c in calls if "failure" in str(c)]
        assert len(failure_calls) >= 1

    def test_summary_sudo_error_503(self, test_client, admin_headers):
        """GET /summary — SudoWrapperError → 503"""
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()):
            with patch("backend.api.routes.fail2ban._run_fail2ban", side_effect=SudoWrapperError("failed")):
                resp = test_client.get("/api/fail2ban/summary", headers=admin_headers)
        assert resp.status_code == 503


# ===================================================================
# get_summary 個別 jail エラーフォールバックテスト
# ===================================================================


class TestSummaryJailErrorFallback:
    """get_summary で個別 jail の status 取得に失敗した場合のフォールバック"""

    def test_summary_with_partial_jail_failures(self, test_client, admin_headers):
        """一部 jail の status 取得に失敗しても summary は成功すること"""
        call_count = [0]

        def _mock_run(cmd, *args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # jail-list は成功
                return _make_wrapper_result("sshd\nnginx-auth\n")
            elif call_count[0] == 2:
                # sshd の status は成功
                return _make_wrapper_result("Currently banned: 3\nTotal banned: 10\nCurrently failed: 5\n")
            else:
                # nginx-auth の status は失敗
                raise SudoWrapperError("connection timeout")

        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()):
            with patch("backend.api.routes.fail2ban._run_fail2ban", side_effect=_mock_run):
                resp = test_client.get("/api/fail2ban/summary", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["jail_count"] == 2
        # 失敗した jail もリストに含まれる（ゼロ値で）
        names = [j["name"] for j in data["jails"]]
        assert "sshd" in names
        assert "nginx-auth" in names


# ===================================================================
# ban/unban 正常系追加テスト
# ===================================================================


class TestBanUnbanExtended:
    """ban/unban の追加テスト"""

    def test_admin_can_ban(self, test_client, admin_headers):
        """Admin は ban 可能（admin:fail2ban あり）"""
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()):
            with patch("backend.api.routes.fail2ban._run_fail2ban", return_value=_make_wrapper_result("1\n")):
                resp = test_client.post(
                    "/api/fail2ban/jails/sshd/ban",
                    json={"ip": "10.0.0.100"},
                    headers=admin_headers,
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "ban"
        assert data["ip"] == "10.0.0.100"
        assert data["jail"] == "sshd"

    def test_ban_ipv6_address(self, test_client, admin_headers):
        """IPv6 アドレスで ban できること"""
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()):
            with patch("backend.api.routes.fail2ban._run_fail2ban", return_value=_make_wrapper_result("1\n")):
                resp = test_client.post(
                    "/api/fail2ban/jails/sshd/ban",
                    json={"ip": "2001:db8::1"},
                    headers=admin_headers,
                )
        assert resp.status_code == 200

    def test_unban_response_has_timestamp(self, test_client, operator_headers):
        """unban レスポンスに timestamp が含まれること"""
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()):
            with patch("backend.api.routes.fail2ban._run_fail2ban", return_value=_make_wrapper_result("1\n")):
                resp = test_client.post(
                    "/api/fail2ban/jails/sshd/unban",
                    json={"ip": "10.0.0.5"},
                    headers=operator_headers,
                )
        assert resp.status_code == 200
        assert "timestamp" in resp.json()


# ===================================================================
# 認証なしアクセス 追加テスト
# ===================================================================


class TestFail2banUnauthorizedExtended:
    """追加の認証なしテスト"""

    def test_unban_no_auth(self, test_client):
        """POST /jails/{name}/unban 認証なし → 403"""
        resp = test_client.post("/api/fail2ban/jails/sshd/unban", json={"ip": "10.0.0.1"})
        assert resp.status_code == 403

    def test_ban_no_auth(self, test_client):
        """POST /jails/{name}/ban 認証なし → 403"""
        resp = test_client.post("/api/fail2ban/jails/sshd/ban", json={"ip": "10.0.0.1"})
        assert resp.status_code == 403

    def test_reload_no_auth(self, test_client):
        """POST /reload 認証なし → 403"""
        resp = test_client.post("/api/fail2ban/reload")
        assert resp.status_code == 403


# ===================================================================
# Viewer 読み取り追加テスト
# ===================================================================


class TestViewerReadExtended:
    """Viewer の読み取り追加テスト"""

    def test_viewer_can_read_jail_detail(self, test_client, viewer_headers):
        """Viewer は jail 詳細を読み取り可能"""
        raw = "Currently banned: 1\nTotal banned: 5\nCurrently failed: 2\n"
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()):
            with patch("backend.api.routes.fail2ban._run_fail2ban", return_value=_make_wrapper_result(raw)):
                resp = test_client.get("/api/fail2ban/jails/sshd", headers=viewer_headers)
        assert resp.status_code == 200

    def test_viewer_can_read_banned_ips(self, test_client, viewer_headers):
        """Viewer は禁止 IP 一覧を読み取り可能"""
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()):
            with patch("backend.api.routes.fail2ban._run_fail2ban", return_value=_make_wrapper_result("10.0.0.1\n")):
                resp = test_client.get("/api/fail2ban/jails/sshd/banned", headers=viewer_headers)
        assert resp.status_code == 200

    def test_viewer_can_read_summary(self, test_client, viewer_headers):
        """Viewer は summary を読み取り可能"""
        call_count = [0]

        def _mock_run(cmd, *args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_wrapper_result("sshd\n")
            return _make_wrapper_result("Currently banned: 0\n")

        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()):
            with patch("backend.api.routes.fail2ban._run_fail2ban", side_effect=_mock_run):
                resp = test_client.get("/api/fail2ban/summary", headers=viewer_headers)
        assert resp.status_code == 200

    def test_viewer_cannot_reload(self, test_client, viewer_headers):
        """Viewer は reload 不可（admin:fail2ban なし）"""
        with patch("backend.api.routes.fail2ban.subprocess.run", return_value=_mock_which_ok()):
            resp = test_client.post("/api/fail2ban/reload", headers=viewer_headers)
        assert resp.status_code == 403
