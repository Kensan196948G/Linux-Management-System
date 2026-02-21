"""
SudoWrapper ユニットテスト

対象: backend/core/sudo_wrapper.py
カバレッジ向上対象行:
  66-68, 91-93, 96-98, 111-114, 174-186, 209-211, 227-233, 236-238,
  246, 250-253, 284, 286, 308-309, 340, 342, 370, 372, 374, 523-524,
  546, 572
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.core.sudo_wrapper import SudoWrapper, SudoWrapperError


# ===========================================================================
# フィクスチャ
# ===========================================================================


@pytest.fixture
def wrapper_with_file(tmp_path):
    """adminui-status.sh が存在する tmp_path を使う SudoWrapper"""
    wrapper_file = tmp_path / "adminui-status.sh"
    wrapper_file.touch()
    return SudoWrapper(wrapper_dir=str(tmp_path))


@pytest.fixture
def mock_run_success_json(wrapper_with_file):
    """subprocess.run が JSON を返すモック付き SudoWrapper"""
    mock_result = MagicMock()
    mock_result.stdout = json.dumps({"status": "ok", "data": "value"})
    return wrapper_with_file, mock_result


# ===========================================================================
# TestSudoWrapperInit: 初期化テスト
# ===========================================================================


class TestSudoWrapperInit:
    """SudoWrapper の初期化テスト"""

    def test_default_dir_falls_back_to_wrappers(self, tmp_path):
        """adminui-status.sh が存在しない場合は wrappers/ へフォールバックする"""
        # wrapper_dir に adminui-status.sh がない tmp_path を渡す
        w = SudoWrapper(wrapper_dir=str(tmp_path))
        # project_root/wrappers に切り替わっていること
        assert str(w.wrapper_dir).endswith("wrappers")

    def test_custom_dir_used_when_file_exists(self, tmp_path):
        """adminui-status.sh が存在する場合はそのディレクトリを使用する"""
        (tmp_path / "adminui-status.sh").touch()
        w = SudoWrapper(wrapper_dir=str(tmp_path))
        assert w.wrapper_dir == tmp_path


# ===========================================================================
# TestExecute: _execute メソッドのテスト（行 66-68, 91-93, 96-98, 111-114）
# ===========================================================================


class TestExecute:
    """_execute メソッドのテスト"""

    # ------ 行 66-68: ラッパーが存在しない場合 ------

    def test_wrapper_not_found_raises_error(self, tmp_path):
        """ラッパースクリプトが存在しない場合は SudoWrapperError を発生させる（行 66-68）"""
        (tmp_path / "adminui-status.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))
        with pytest.raises(SudoWrapperError, match="not found"):
            wrapper._execute("nonexistent-wrapper.sh", [])

    # ------ 行 91-93: 非 JSON レスポンス ------

    def test_non_json_stdout_returns_success_dict(self, tmp_path):
        """JSON でない stdout は {'status': 'success', 'output': ...} で返す（行 91-93）"""
        (tmp_path / "adminui-status.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = "plain text output"

        with patch("subprocess.run", return_value=mock_result):
            result = wrapper._execute("adminui-status.sh", [])

        assert result["status"] == "success"
        assert "plain text output" in result["output"]

    def test_empty_stdout_returns_success_dict(self, tmp_path):
        """空の stdout も {'status': 'success', 'output': ''} で返す（行 91-93）"""
        (tmp_path / "adminui-status.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = ""

        with patch("subprocess.run", return_value=mock_result):
            result = wrapper._execute("adminui-status.sh", [])

        assert result["status"] == "success"
        assert result["output"] == ""

    # ------ 行 96-98: TimeoutExpired ------

    def test_timeout_raises_sudo_wrapper_error(self, tmp_path):
        """TimeoutExpired 時に SudoWrapperError を発生させる（行 96-98）"""
        (tmp_path / "adminui-status.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd=[], timeout=30)
            with pytest.raises(SudoWrapperError, match="timed out"):
                wrapper._execute("adminui-status.sh", [])

    # ------ 行 100-107: CalledProcessError (JSON エラー出力) ------

    def test_called_process_error_with_json_stderr_returns_data(self, tmp_path):
        """CalledProcessError で stderr が JSON の場合はそのデータを返す"""
        (tmp_path / "adminui-status.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        error_data = {"status": "error", "message": "some error"}
        exc = subprocess.CalledProcessError(
            returncode=1, cmd=[], stderr=json.dumps(error_data)
        )

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = exc
            result = wrapper._execute("adminui-status.sh", [])

        assert result["status"] == "error"
        assert result["message"] == "some error"

    def test_called_process_error_with_non_json_stderr_raises(self, tmp_path):
        """CalledProcessError で stderr が非 JSON の場合は SudoWrapperError を発生させる"""
        (tmp_path / "adminui-status.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        exc = subprocess.CalledProcessError(
            returncode=1, cmd=[], stderr="plain error text"
        )

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = exc
            with pytest.raises(SudoWrapperError):
                wrapper._execute("adminui-status.sh", [])

    def test_called_process_error_with_empty_stderr_returns_empty_dict(self, tmp_path):
        """CalledProcessError で stderr/stdout が空の場合は空 JSON ({}) を返す"""
        (tmp_path / "adminui-status.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        exc = subprocess.CalledProcessError(
            returncode=1, cmd=[], stderr=None, output=None
        )

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = exc
            result = wrapper._execute("adminui-status.sh", [])

        # json.loads("{}") -> {} が返される
        assert result == {}

    # ------ 行 111-114: 予期しない例外 ------

    def test_unexpected_exception_raises_sudo_wrapper_error(self, tmp_path):
        """予期しない例外を SudoWrapperError でラップする（行 111-114）"""
        (tmp_path / "adminui-status.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = RuntimeError("unexpected error")
            with pytest.raises(SudoWrapperError, match="Unexpected error"):
                wrapper._execute("adminui-status.sh", [])

    # ------ 正常系: JSON レスポンス ------

    def test_json_response_parsed_correctly(self, tmp_path):
        """JSON レスポンスが辞書として返される"""
        (tmp_path / "adminui-status.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        expected = {"status": "ok", "value": 42}
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(expected)

        with patch("subprocess.run", return_value=mock_result):
            result = wrapper._execute("adminui-status.sh", [])

        assert result == expected


# ===========================================================================
# TestExecuteWithStdin: _execute_with_stdin のテスト（行 209-211, 227-233, 236-238, 246, 250-253）
# ===========================================================================


class TestExecuteWithStdin:
    """_execute_with_stdin メソッドのテスト"""

    # ------ 行 209-211: ラッパーが存在しない場合 ------

    def test_wrapper_not_found_raises_error(self, tmp_path):
        """ラッパーが存在しない場合は SudoWrapperError を発生させる（行 209-211）"""
        (tmp_path / "adminui-status.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))
        with pytest.raises(SudoWrapperError, match="not found"):
            wrapper._execute_with_stdin("nonexistent-wrapper.sh", [], "stdin_data")

    # ------ 行 227-233: JSON レスポンス ------

    def test_json_response_parsed(self, tmp_path):
        """JSON レスポンスが辞書として返される（行 227-233）"""
        script = tmp_path / "adminui-user-add.sh"
        script.touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        expected = {"status": "success", "uid": 1001}
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(expected)

        with patch("subprocess.run", return_value=mock_result):
            result = wrapper._execute_with_stdin("adminui-user-add.sh", [], "hash")

        assert result == expected

    def test_non_json_stdout_returns_success_dict(self, tmp_path):
        """非 JSON stdout は {'status': 'success', 'output': ...} で返す（行 229-233）"""
        script = tmp_path / "adminui-user-add.sh"
        script.touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = "user created"

        with patch("subprocess.run", return_value=mock_result):
            result = wrapper._execute_with_stdin("adminui-user-add.sh", [], "hash")

        assert result["status"] == "success"
        assert "user created" in result["output"]

    # ------ 行 236-238: TimeoutExpired ------

    def test_timeout_raises_sudo_wrapper_error(self, tmp_path):
        """TimeoutExpired 時に SudoWrapperError を発生させる（行 236-238）"""
        script = tmp_path / "adminui-user-add.sh"
        script.touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd=[], timeout=30)
            with pytest.raises(SudoWrapperError, match="timed out"):
                wrapper._execute_with_stdin("adminui-user-add.sh", [], "hash")

    # ------ 行 246: CalledProcessError JSON stderr ------

    def test_called_process_error_with_json_stderr_returns_data(self, tmp_path):
        """CalledProcessError で JSON stderr を返す（行 246）"""
        script = tmp_path / "adminui-user-add.sh"
        script.touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        error_data = {"status": "error", "code": "USER_EXISTS"}
        exc = subprocess.CalledProcessError(
            returncode=1, cmd=[], stderr=json.dumps(error_data)
        )

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = exc
            result = wrapper._execute_with_stdin("adminui-user-add.sh", [], "hash")

        assert result["status"] == "error"
        assert result["code"] == "USER_EXISTS"

    # ------ 行 248: CalledProcessError 非 JSON stderr ------

    def test_called_process_error_non_json_raises(self, tmp_path):
        """CalledProcessError で非 JSON stderr は SudoWrapperError を発生させる（行 248）"""
        script = tmp_path / "adminui-user-add.sh"
        script.touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        exc = subprocess.CalledProcessError(
            returncode=1, cmd=[], stderr="user already exists"
        )

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = exc
            with pytest.raises(SudoWrapperError):
                wrapper._execute_with_stdin("adminui-user-add.sh", [], "hash")

    # ------ 行 250-253: 予期しない例外 ------

    def test_unexpected_exception_raises_sudo_wrapper_error(self, tmp_path):
        """予期しない例外を SudoWrapperError でラップする（行 250-253）"""
        script = tmp_path / "adminui-user-add.sh"
        script.touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = OSError("permission denied")
            with pytest.raises(SudoWrapperError, match="Unexpected error"):
                wrapper._execute_with_stdin("adminui-user-add.sh", [], "hash")


# ===========================================================================
# TestGetProcesses: get_processes のテスト（行 174-186）
# ===========================================================================


class TestGetProcesses:
    """get_processes メソッドのテスト"""

    def test_get_processes_default_args(self, tmp_path):
        """デフォルト引数で adminui-processes.sh を呼び出す（行 174-186）"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-processes.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "ok", "processes": []})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = wrapper.get_processes()

        args_called = mock_run.call_args[0][0]
        assert "--sort=cpu" in args_called
        assert "--limit=100" in args_called
        assert result["status"] == "ok"

    def test_get_processes_with_filter_user(self, tmp_path):
        """filter_user 指定時に --filter-user= 引数が追加される（行 179-180）"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-processes.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "ok", "processes": []})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper.get_processes(filter_user="root")

        args_called = mock_run.call_args[0][0]
        assert "--filter-user=root" in args_called

    def test_get_processes_with_min_cpu(self, tmp_path):
        """min_cpu > 0 時に --min-cpu= 引数が追加される（行 181-182）"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-processes.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "ok", "processes": []})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper.get_processes(min_cpu=10.0)

        args_called = mock_run.call_args[0][0]
        assert "--min-cpu=10.0" in args_called

    def test_get_processes_with_min_mem(self, tmp_path):
        """min_mem > 0 時に --min-mem= 引数が追加される（行 183-184）"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-processes.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "ok", "processes": []})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper.get_processes(min_mem=5.0)

        args_called = mock_run.call_args[0][0]
        assert "--min-mem=5.0" in args_called

    def test_get_processes_no_optional_args_when_zero(self, tmp_path):
        """min_cpu=0, min_mem=0, filter_user=None の場合はオプション引数が追加されない"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-processes.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "ok"})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper.get_processes(min_cpu=0.0, min_mem=0.0, filter_user=None)

        args_called = mock_run.call_args[0][0]
        # オプション引数が含まれていないこと
        assert not any("--filter-user" in a for a in args_called)
        assert not any("--min-cpu" in a for a in args_called)
        assert not any("--min-mem" in a for a in args_called)


# ===========================================================================
# TestListUsers: list_users のテスト（行 284, 286）
# ===========================================================================


class TestListUsers:
    """list_users メソッドのテスト"""

    def test_list_users_default_args(self, tmp_path):
        """デフォルト引数で adminui-user-list.sh を呼び出す"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-user-list.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "ok", "users": []})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = wrapper.list_users()

        args_called = mock_run.call_args[0][0]
        assert "--sort=username" in args_called
        assert "--limit=100" in args_called
        assert result["status"] == "ok"

    def test_list_users_with_filter_locked(self, tmp_path):
        """filter_locked 指定時に --filter-locked= 引数が追加される（行 284）"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-user-list.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "ok", "users": []})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper.list_users(filter_locked="true")

        args_called = mock_run.call_args[0][0]
        assert "--filter-locked=true" in args_called

    def test_list_users_with_username_filter(self, tmp_path):
        """username_filter 指定時に --username-filter= 引数が追加される（行 286）"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-user-list.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "ok", "users": []})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper.list_users(username_filter="admin")

        args_called = mock_run.call_args[0][0]
        assert "--username-filter=admin" in args_called

    def test_list_users_no_optional_when_none(self, tmp_path):
        """filter_locked=None, username_filter=None のときオプション引数なし"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-user-list.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "ok"})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper.list_users(filter_locked=None, username_filter=None)

        args_called = mock_run.call_args[0][0]
        assert not any("--filter-locked" in a for a in args_called)
        assert not any("--username-filter" in a for a in args_called)


# ===========================================================================
# TestGetUserDetail: get_user_detail のテスト（行 308-309）
# ===========================================================================


class TestGetUserDetail:
    """get_user_detail メソッドのテスト"""

    def test_get_user_detail_by_username(self, tmp_path):
        """username 指定時に --username= 引数が追加される（行 307-308）"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-user-detail.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "ok", "user": {}})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper.get_user_detail(username="alice")

        args_called = mock_run.call_args[0][0]
        assert "--username=alice" in args_called

    def test_get_user_detail_by_uid(self, tmp_path):
        """uid 指定時に --uid= 引数が追加される（行 308-309）"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-user-detail.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "ok", "user": {}})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper.get_user_detail(uid=1001)

        args_called = mock_run.call_args[0][0]
        assert "--uid=1001" in args_called

    def test_get_user_detail_no_args(self, tmp_path):
        """username も uid も指定しない場合は引数なしで呼び出す"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-user-detail.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "ok"})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper.get_user_detail()

        args_called = mock_run.call_args[0][0]
        assert not any("--username" in a for a in args_called)
        assert not any("--uid" in a for a in args_called)


# ===========================================================================
# TestAddUser: add_user のテスト（行 340, 342）
# ===========================================================================


class TestAddUser:
    """add_user メソッドのテスト"""

    def test_add_user_with_gecos(self, tmp_path):
        """gecos 指定時に --gecos= 引数が追加される（行 340）"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-user-add.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "ok"})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper.add_user(
                username="alice",
                password_hash="$6$hash",
                gecos="Alice Smith",
            )

        args_called = mock_run.call_args[0][0]
        assert "--gecos=Alice Smith" in args_called

    def test_add_user_with_groups(self, tmp_path):
        """groups 指定時に --groups= 引数が追加される（行 342）"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-user-add.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "ok"})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper.add_user(
                username="alice",
                password_hash="$6$hash",
                groups=["sudo", "developers"],
            )

        args_called = mock_run.call_args[0][0]
        assert "--groups=sudo,developers" in args_called

    def test_add_user_minimal(self, tmp_path):
        """最小引数（username, password_hash）での呼び出し"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-user-add.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "ok"})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper.add_user(username="bob", password_hash="$6$hash")

        args_called = mock_run.call_args[0][0]
        assert "--username=bob" in args_called
        assert "--shell=/bin/bash" in args_called
        assert not any("--gecos" in a for a in args_called)
        assert not any("--groups" in a for a in args_called)


# ===========================================================================
# TestDeleteUser: delete_user のテスト（行 370, 372, 374）
# ===========================================================================


class TestDeleteUser:
    """delete_user メソッドのテスト"""

    def test_delete_user_with_remove_home(self, tmp_path):
        """remove_home=True 時に --remove-home フラグが追加される（行 370）"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-user-delete.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "ok"})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper.delete_user(username="alice", remove_home=True)

        args_called = mock_run.call_args[0][0]
        assert "--remove-home" in args_called

    def test_delete_user_with_backup_home(self, tmp_path):
        """backup_home=True 時に --backup-home フラグが追加される（行 372）"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-user-delete.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "ok"})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper.delete_user(username="alice", backup_home=True)

        args_called = mock_run.call_args[0][0]
        assert "--backup-home" in args_called

    def test_delete_user_with_force_logout(self, tmp_path):
        """force_logout=True 時に --force-logout フラグが追加される（行 374）"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-user-delete.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "ok"})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper.delete_user(username="alice", force_logout=True)

        args_called = mock_run.call_args[0][0]
        assert "--force-logout" in args_called

    def test_delete_user_minimal_no_optional_flags(self, tmp_path):
        """フラグなしではオプション引数が追加されない"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-user-delete.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "ok"})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper.delete_user(username="alice")

        args_called = mock_run.call_args[0][0]
        assert "--username=alice" in args_called
        assert "--remove-home" not in args_called
        assert "--backup-home" not in args_called
        assert "--force-logout" not in args_called


# ===========================================================================
# TestAddCronJob: add_cron_job のテスト（行 523-524）
# ===========================================================================


class TestAddCronJob:
    """add_cron_job メソッドのテスト"""

    def test_add_cron_job_with_arguments_and_comment(self, tmp_path):
        """arguments と comment の両方が指定された場合（行 518-520）"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-cron-add.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "ok"})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper.add_cron_job(
                username="alice",
                schedule="0 2 * * *",
                command="/usr/bin/backup.sh",
                arguments="--verbose",
                comment="daily backup",
            )

        args_called = mock_run.call_args[0][0]
        # username, schedule, command, arguments, comment の順
        assert "alice" in args_called
        assert "0 2 * * *" in args_called
        assert "/usr/bin/backup.sh" in args_called
        assert "--verbose" in args_called
        assert "daily backup" in args_called

    def test_add_cron_job_with_comment_no_arguments(self, tmp_path):
        """arguments がなく comment だけの場合、空文字列を挿入する（行 523-524）"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-cron-add.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "ok"})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper.add_cron_job(
                username="alice",
                schedule="0 2 * * *",
                command="/usr/bin/backup.sh",
                comment="daily backup",
            )

        args_called = mock_run.call_args[0][0]
        # 空文字列の引数が挿入されていること
        # ["sudo", script, "alice", "0 2 * * *", "/usr/bin/backup.sh", "", "daily backup"]
        assert "" in args_called
        assert "daily backup" in args_called

    def test_add_cron_job_minimal(self, tmp_path):
        """最小引数（username, schedule, command）での呼び出し"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-cron-add.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "ok"})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper.add_cron_job(
                username="bob",
                schedule="*/5 * * * *",
                command="/usr/bin/check.sh",
            )

        args_called = mock_run.call_args[0][0]
        assert "bob" in args_called
        assert "*/5 * * * *" in args_called
        assert "/usr/bin/check.sh" in args_called


# ===========================================================================
# TestRemoveCronJob: remove_cron_job のテスト（行 546）
# ===========================================================================


class TestRemoveCronJob:
    """remove_cron_job メソッドのテスト"""

    def test_remove_cron_job_calls_correct_wrapper(self, tmp_path):
        """adminui-cron-remove.sh を正しい引数で呼び出す（行 546）"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-cron-remove.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "ok"})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper.remove_cron_job(username="alice", line_number=5)

        args_called = mock_run.call_args[0][0]
        assert "alice" in args_called
        assert "5" in args_called
        assert str(tmp_path / "adminui-cron-remove.sh") in args_called


# ===========================================================================
# TestToggleCronJob: toggle_cron_job のテスト（行 572）
# ===========================================================================


class TestToggleCronJob:
    """toggle_cron_job メソッドのテスト"""

    def test_toggle_cron_job_enable(self, tmp_path):
        """enable アクションで adminui-cron-toggle.sh を呼び出す（行 572）"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-cron-toggle.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "ok"})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper.toggle_cron_job(username="alice", line_number=3, action="enable")

        args_called = mock_run.call_args[0][0]
        assert "alice" in args_called
        assert "3" in args_called
        assert "enable" in args_called

    def test_toggle_cron_job_disable(self, tmp_path):
        """disable アクションで adminui-cron-toggle.sh を呼び出す"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-cron-toggle.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "ok"})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper.toggle_cron_job(username="bob", line_number=7, action="disable")

        args_called = mock_run.call_args[0][0]
        assert "bob" in args_called
        assert "7" in args_called
        assert "disable" in args_called


# ===========================================================================
# TestHighLevelMethods: 高レベルメソッドのテスト（各ラッパー呼び出し確認）
# ===========================================================================


class TestHighLevelMethods:
    """高レベルメソッドが正しいラッパーを呼び出すことを確認"""

    def test_get_system_status(self, tmp_path):
        """get_system_status が adminui-status.sh を呼び出す"""
        (tmp_path / "adminui-status.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"uptime": "1 day"})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = wrapper.get_system_status()

        args_called = mock_run.call_args[0][0]
        assert "adminui-status.sh" in args_called[-1] or any(
            "adminui-status.sh" in str(a) for a in args_called
        )
        assert result["uptime"] == "1 day"

    def test_restart_service(self, tmp_path):
        """restart_service が adminui-service-restart.sh を呼び出す"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-service-restart.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "restarted"})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = wrapper.restart_service("nginx")

        args_called = mock_run.call_args[0][0]
        assert "nginx" in args_called

    def test_change_user_password(self, tmp_path):
        """change_user_password が _execute_with_stdin を通じて呼び出す"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-user-passwd.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "ok"})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper.change_user_password(username="alice", password_hash="$6$hash")

        args_called = mock_run.call_args[0][0]
        assert "--username=alice" in args_called

    def test_list_cron_jobs(self, tmp_path):
        """list_cron_jobs が adminui-cron-list.sh を呼び出す"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-cron-list.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"jobs": []})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper.list_cron_jobs(username="alice")

        args_called = mock_run.call_args[0][0]
        assert "alice" in args_called

    def test_list_groups(self, tmp_path):
        """list_groups が adminui-group-list.sh を呼び出す"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-group-list.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"groups": []})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper.list_groups()

        args_called = mock_run.call_args[0][0]
        assert "--sort=name" in args_called

    def test_add_group(self, tmp_path):
        """add_group が adminui-group-add.sh を呼び出す"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-group-add.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "ok"})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper.add_group(name="devteam")

        args_called = mock_run.call_args[0][0]
        assert "--name=devteam" in args_called

    def test_delete_group(self, tmp_path):
        """delete_group が adminui-group-delete.sh を呼び出す"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-group-delete.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "ok"})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper.delete_group(name="devteam")

        args_called = mock_run.call_args[0][0]
        assert "--name=devteam" in args_called

    def test_modify_group_membership_add(self, tmp_path):
        """modify_group_membership が adminui-group-modify.sh を呼び出す"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-group-modify.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "ok"})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper.modify_group_membership(group="sudo", action="add", user="alice")

        args_called = mock_run.call_args[0][0]
        assert "--group=sudo" in args_called
        assert "--action=add" in args_called
        assert "--user=alice" in args_called
