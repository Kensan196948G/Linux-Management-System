"""
sudo ラッパー呼び出しモジュール

CLAUDE.md のセキュリティ原則に従った安全な sudo 実行
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


class SudoWrapperError(Exception):
    """sudo ラッパー実行エラー"""

    pass


class SudoWrapper:
    """sudo ラッパー呼び出しクラス"""

    def __init__(self, wrapper_dir: str = "/usr/local/sbin"):
        """
        初期化

        Args:
            wrapper_dir: ラッパースクリプトのディレクトリ
        """
        self.wrapper_dir = Path(wrapper_dir)

        # テストファイルが存在するか確認
        test_file = self.wrapper_dir / "adminui-status.sh"

        # 開発環境では、プロジェクトの wrappers/ を使用
        if not test_file.exists():
            project_root = Path(__file__).parent.parent.parent
            self.wrapper_dir = project_root / "wrappers"
            logger.warning(
                f"Wrapper scripts not found at {wrapper_dir}, "
                f"using development directory: {self.wrapper_dir}"
            )

    def _execute(
        self, wrapper_name: str, args: list[str], timeout: int = 30
    ) -> Dict[str, Any]:
        """
        ラッパースクリプトを実行

        Args:
            wrapper_name: ラッパースクリプト名（例: adminui-status.sh）
            args: 引数リスト
            timeout: タイムアウト（秒）

        Returns:
            実行結果の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        wrapper_path = self.wrapper_dir / wrapper_name

        if not wrapper_path.exists():
            error_msg = f"Wrapper script not found: {wrapper_path}"
            logger.error(error_msg)
            raise SudoWrapperError(error_msg)

        # ラッパースクリプトの実行（配列渡し）
        # 注意: shell=True は絶対に使用しない
        cmd = ["sudo", str(wrapper_path)] + args

        logger.info(f"Executing wrapper: {wrapper_name}, args={args}")

        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            logger.info(f"Wrapper execution successful: {wrapper_name}")

            # JSON レスポンスをパース
            try:
                output = json.loads(result.stdout)
                return output
            except json.JSONDecodeError:
                # JSON でない場合はそのまま返す
                return {"status": "success", "output": result.stdout.strip()}

        except subprocess.TimeoutExpired:
            error_msg = f"Wrapper execution timed out: {wrapper_name}"
            logger.error(error_msg)
            raise SudoWrapperError(error_msg)

        except subprocess.CalledProcessError as e:
            error_msg = f"Wrapper execution failed: {wrapper_name}"
            logger.error(f"{error_msg}, stderr={e.stderr}")

            # エラー出力を JSON としてパース試行
            try:
                error_data = json.loads(e.stderr or e.stdout or "{}")
                return error_data
            except json.JSONDecodeError:
                raise SudoWrapperError(f"{error_msg}: {e.stderr}")

        except Exception as e:
            error_msg = f"Unexpected error during wrapper execution: {wrapper_name}"
            logger.error(f"{error_msg}: {e}")
            raise SudoWrapperError(f"{error_msg}: {str(e)}")

    def get_system_status(self) -> Dict[str, Any]:
        """
        システム状態を取得

        Returns:
            システム状態の辞書
        """
        return self._execute("adminui-status.sh", [])

    def restart_service(self, service_name: str) -> Dict[str, Any]:
        """
        サービスを再起動

        Args:
            service_name: サービス名

        Returns:
            実行結果の辞書
        """
        return self._execute("adminui-service-restart.sh", [service_name])

    def stop_service(self, service_name: str) -> Dict[str, Any]:
        """
        サービスを停止（要承認操作）

        Args:
            service_name: サービス名

        Returns:
            実行結果の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-service-stop.sh", [service_name])

    def get_logs(self, service_name: str, lines: int = 100) -> Dict[str, Any]:
        """
        サービスのログを取得

        Args:
            service_name: サービス名
            lines: 取得行数

        Returns:
            ログデータの辞書
        """
        return self._execute("adminui-logs.sh", [service_name, str(lines)])

    def get_processes(
        self,
        sort_by: str = "cpu",
        limit: int = 100,
        filter_user: str | None = None,
        min_cpu: float = 0.0,
        min_mem: float = 0.0,
    ) -> Dict[str, Any]:
        """
        プロセス一覧を取得

        Args:
            sort_by: ソートキー (cpu/mem/pid/time)
            limit: 取得件数 (1-1000)
            filter_user: ユーザー名フィルタ (allowlist検証済み)
            min_cpu: 最小CPU使用率 (0.0-100.0)
            min_mem: 最小メモリ使用率 (0.0-100.0)

        Returns:
            プロセス情報の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        args = [
            f"--sort={sort_by}",
            f"--limit={limit}",
        ]

        if filter_user:
            args.append(f"--filter-user={filter_user}")
        if min_cpu > 0.0:
            args.append(f"--min-cpu={min_cpu}")
        if min_mem > 0.0:
            args.append(f"--min-mem={min_mem}")

        return self._execute("adminui-processes.sh", args, timeout=10)

    def _execute_with_stdin(
        self, wrapper_name: str, args: list[str], stdin_data: str, timeout: int = 30
    ) -> Dict[str, Any]:
        """
        ラッパースクリプトを stdin データ付きで実行

        Args:
            wrapper_name: ラッパースクリプト名
            args: 引数リスト
            stdin_data: stdin に渡すデータ
            timeout: タイムアウト（秒）

        Returns:
            実行結果の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        wrapper_path = self.wrapper_dir / wrapper_name

        if not wrapper_path.exists():
            error_msg = f"Wrapper script not found: {wrapper_path}"
            logger.error(error_msg)
            raise SudoWrapperError(error_msg)

        cmd = ["sudo", str(wrapper_path)] + args

        logger.info(f"Executing wrapper (with stdin): {wrapper_name}, args={args}")

        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                input=stdin_data,
                timeout=timeout,
            )

            logger.info(f"Wrapper execution successful: {wrapper_name}")

            try:
                output = json.loads(result.stdout)
                return output
            except json.JSONDecodeError:
                return {"status": "success", "output": result.stdout.strip()}

        except subprocess.TimeoutExpired:
            error_msg = f"Wrapper execution timed out: {wrapper_name}"
            logger.error(error_msg)
            raise SudoWrapperError(error_msg)

        except subprocess.CalledProcessError as e:
            error_msg = f"Wrapper execution failed: {wrapper_name}"
            logger.error(f"{error_msg}, stderr={e.stderr}")

            try:
                error_data = json.loads(e.stderr or e.stdout or "{}")
                return error_data
            except json.JSONDecodeError:
                raise SudoWrapperError(f"{error_msg}: {e.stderr}")

        except Exception as e:
            error_msg = f"Unexpected error during wrapper execution: {wrapper_name}"
            logger.error(f"{error_msg}: {e}")
            raise SudoWrapperError(f"{error_msg}: {str(e)}")

    # ===================================================================
    # ユーザー管理
    # ===================================================================

    def list_users(
        self,
        sort_by: str = "username",
        limit: int = 100,
        filter_locked: str | None = None,
        username_filter: str | None = None,
    ) -> Dict[str, Any]:
        """
        ユーザー一覧を取得

        Args:
            sort_by: ソートキー (username/uid/last_login)
            limit: 取得件数 (1-500)
            filter_locked: ロック状態フィルタ (true/false)
            username_filter: ユーザー名フィルタ

        Returns:
            ユーザー一覧の辞書
        """
        args = [
            f"--sort={sort_by}",
            f"--limit={limit}",
        ]

        if filter_locked is not None:
            args.append(f"--filter-locked={filter_locked}")
        if username_filter:
            args.append(f"--username-filter={username_filter}")

        return self._execute("adminui-user-list.sh", args, timeout=10)

    def get_user_detail(
        self,
        username: str | None = None,
        uid: int | None = None,
    ) -> Dict[str, Any]:
        """
        ユーザー詳細情報を取得

        Args:
            username: ユーザー名（username か uid のどちらか一方を指定）
            uid: UID

        Returns:
            ユーザー詳細の辞書
        """
        args = []
        if username is not None:
            args.append(f"--username={username}")
        elif uid is not None:
            args.append(f"--uid={uid}")

        return self._execute("adminui-user-detail.sh", args, timeout=10)

    def add_user(
        self,
        username: str,
        password_hash: str,
        shell: str = "/bin/bash",
        gecos: str = "",
        groups: list[str] | None = None,
    ) -> Dict[str, Any]:
        """
        ユーザーを作成

        Args:
            username: ユーザー名
            password_hash: bcrypt パスワードハッシュ（stdin 経由で渡す）
            shell: ログインシェル
            gecos: GECOS フィールド（フルネーム等）
            groups: 追加グループリスト

        Returns:
            作成結果の辞書
        """
        args = [
            f"--username={username}",
            f"--shell={shell}",
        ]

        if gecos:
            args.append(f"--gecos={gecos}")
        if groups:
            args.append(f"--groups={','.join(groups)}")

        return self._execute_with_stdin(
            "adminui-user-add.sh", args, stdin_data=password_hash, timeout=15
        )

    def delete_user(
        self,
        username: str,
        remove_home: bool = False,
        backup_home: bool = False,
        force_logout: bool = False,
    ) -> Dict[str, Any]:
        """
        ユーザーを削除

        Args:
            username: ユーザー名
            remove_home: ホームディレクトリを削除するか
            backup_home: ホームディレクトリをバックアップするか
            force_logout: アクティブセッションを強制ログアウトするか

        Returns:
            削除結果の辞書
        """
        args = [f"--username={username}"]

        if remove_home:
            args.append("--remove-home")
        if backup_home:
            args.append("--backup-home")
        if force_logout:
            args.append("--force-logout")

        return self._execute("adminui-user-delete.sh", args, timeout=30)

    def change_user_password(
        self,
        username: str,
        password_hash: str,
    ) -> Dict[str, Any]:
        """
        ユーザーパスワードを変更

        Args:
            username: ユーザー名
            password_hash: bcrypt パスワードハッシュ（stdin 経由で渡す）

        Returns:
            変更結果の辞書
        """
        return self._execute_with_stdin(
            "adminui-user-passwd.sh",
            [f"--username={username}"],
            stdin_data=password_hash,
            timeout=10,
        )

    # ===================================================================
    # グループ管理
    # ===================================================================

    def list_groups(
        self,
        sort_by: str = "name",
        limit: int = 100,
    ) -> Dict[str, Any]:
        """
        グループ一覧を取得

        Args:
            sort_by: ソートキー (name/gid/member_count)
            limit: 取得件数 (1-500)

        Returns:
            グループ一覧の辞書
        """
        args = [
            f"--sort={sort_by}",
            f"--limit={limit}",
        ]

        return self._execute("adminui-group-list.sh", args, timeout=10)

    def add_group(self, name: str) -> Dict[str, Any]:
        """
        グループを作成

        Args:
            name: グループ名

        Returns:
            作成結果の辞書
        """
        return self._execute("adminui-group-add.sh", [f"--name={name}"], timeout=10)

    def delete_group(self, name: str) -> Dict[str, Any]:
        """
        グループを削除

        Args:
            name: グループ名

        Returns:
            削除結果の辞書
        """
        return self._execute("adminui-group-delete.sh", [f"--name={name}"], timeout=10)

    def modify_group_membership(
        self,
        group: str,
        action: str,
        user: str,
    ) -> Dict[str, Any]:
        """
        グループメンバーシップを変更

        Args:
            group: グループ名
            action: アクション ("add" or "remove")
            user: 対象ユーザー名

        Returns:
            変更結果の辞書
        """
        return self._execute(
            "adminui-group-modify.sh",
            [f"--group={group}", f"--action={action}", f"--user={user}"],
            timeout=10,
        )

    # ===================================================================
    # Cron ジョブ管理
    # ===================================================================

    def list_cron_jobs(self, username: str) -> Dict[str, Any]:
        """
        指定ユーザーの cron ジョブ一覧を取得

        Args:
            username: 対象ユーザー名

        Returns:
            cron ジョブ一覧の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-cron-list.sh", [username], timeout=10)

    def add_cron_job(
        self,
        username: str,
        schedule: str,
        command: str,
        arguments: str = "",
        comment: str = "",
    ) -> Dict[str, Any]:
        """
        指定ユーザーに cron ジョブを追加

        Args:
            username: 対象ユーザー名
            schedule: cron スケジュール式 (例: "0 2 * * *")
            command: 実行コマンド（絶対パス、allowlist 検証済み）
            arguments: コマンド引数
            comment: ジョブの説明コメント

        Returns:
            追加結果の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        args = [username, schedule, command]
        if arguments:
            args.append(arguments)
            if comment:
                args.append(comment)
        elif comment:
            # 引数なしでコメントありの場合、空文字列の引数を挿入
            args.append("")
            args.append(comment)

        return self._execute("adminui-cron-add.sh", args, timeout=10)

    def remove_cron_job(
        self,
        username: str,
        line_number: int,
    ) -> Dict[str, Any]:
        """
        指定ユーザーの cron ジョブを削除（コメントアウト方式）

        Args:
            username: 対象ユーザー名
            line_number: 削除対象の行番号

        Returns:
            削除結果の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute(
            "adminui-cron-remove.sh",
            [username, str(line_number)],
            timeout=10,
        )

    def toggle_cron_job(
        self,
        username: str,
        line_number: int,
        action: str,
    ) -> Dict[str, Any]:
        """
        指定ユーザーの cron ジョブの有効/無効を切り替え

        Args:
            username: 対象ユーザー名
            line_number: 対象の行番号
            action: "enable" または "disable"

        Returns:
            切替結果の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute(
            "adminui-cron-toggle.sh",
            [username, str(line_number), action],
            timeout=10,
        )

    # ------------------------------------------------------------------
    # ネットワーク情報取得（読み取り専用）
    # ------------------------------------------------------------------

    def get_network_interfaces(self) -> Dict[str, Any]:
        """
        ネットワークインターフェース一覧を取得 (ip addr show)

        Returns:
            インターフェース情報の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-network.sh", ["interfaces"], timeout=10)

    def get_network_stats(self) -> Dict[str, Any]:
        """
        ネットワークインターフェース統計を取得 (ip -s link show)

        Returns:
            統計情報の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-network.sh", ["stats"], timeout=10)

    def get_network_connections(self) -> Dict[str, Any]:
        """
        アクティブなネットワーク接続を取得 (ss -tlnp)

        Returns:
            接続情報の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-network.sh", ["connections"], timeout=10)

    def get_network_routes(self) -> Dict[str, Any]:
        """
        ルーティングテーブルを取得 (ip route show)

        Returns:
            ルーティング情報の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-network.sh", ["routes"], timeout=10)

    # ------------------------------------------------------------------
    # サーバー管理（読み取り専用）
    # ------------------------------------------------------------------

    #: 許可サーバー名一覧
    ALLOWED_SERVERS = ("nginx", "apache2", "mysql", "postgresql", "redis")

    def get_all_server_status(self) -> Dict[str, Any]:
        """
        全許可サーバーの状態を一括取得 (systemctl show)

        Returns:
            全サーバー状態の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-servers.sh", ["status"], timeout=15)

    def get_server_status(self, server: str) -> Dict[str, Any]:
        """
        指定サーバーの状態を取得

        Args:
            server: サーバー名（allowlist: nginx/apache2/mysql/postgresql/redis）

        Returns:
            サーバー状態の辞書

        Raises:
            SudoWrapperError: 実行失敗時
            ValueError: 不正なサーバー名
        """
        if server not in self.ALLOWED_SERVERS:
            raise ValueError(f"Server not allowed: {server}")
        return self._execute("adminui-servers.sh", ["status", server], timeout=10)

    def get_server_version(self, server: str) -> Dict[str, Any]:
        """
        指定サーバーのバージョン情報を取得

        Args:
            server: サーバー名

        Returns:
            バージョン情報の辞書

        Raises:
            SudoWrapperError: 実行失敗時
            ValueError: 不正なサーバー名
        """
        if server not in self.ALLOWED_SERVERS:
            raise ValueError(f"Server not allowed: {server}")
        return self._execute("adminui-servers.sh", ["version", server], timeout=10)

    def get_server_config_info(self, server: str) -> Dict[str, Any]:
        """
        指定サーバーの設定ファイル情報を取得（パスと存在確認のみ）

        Args:
            server: サーバー名

        Returns:
            設定ファイル情報の辞書

        Raises:
            SudoWrapperError: 実行失敗時
            ValueError: 不正なサーバー名
        """
        if server not in self.ALLOWED_SERVERS:
            raise ValueError(f"Server not allowed: {server}")
        return self._execute("adminui-servers.sh", ["config", server], timeout=10)

    # ------------------------------------------------------------------
    # ハードウェア情報取得（読み取り専用）
    # ------------------------------------------------------------------

    def get_hardware_disks(self) -> Dict[str, Any]:
        """
        ブロックデバイス一覧を取得 (lsblk -J)

        Returns:
            ディスク一覧の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-hardware.sh", ["disks"], timeout=15)

    def get_hardware_disk_usage(self) -> Dict[str, Any]:
        """
        ディスク使用量を取得 (df -P)

        Returns:
            ディスク使用量の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-hardware.sh", ["disk_usage"], timeout=15)

    def get_hardware_smart(self, device: str) -> Dict[str, Any]:
        """
        SMART情報を取得 (smartctl -j -a)

        Args:
            device: デバイスパス（例: /dev/sda）。allowlist: /dev/sd[a-z], /dev/nvme*

        Returns:
            SMART情報の辞書

        Raises:
            SudoWrapperError: 実行失敗時
            ValueError: 不正なデバイスパス
        """
        import re

        # Pythonレベルでのデバイスパス検証（二重チェック）
        if not re.match(r"^/dev/(sd[a-z]|nvme[0-9]n[0-9]|vd[a-z]|xvd[a-z]|hd[a-z])$", device):
            raise ValueError(f"Invalid device path: {device}")
        return self._execute("adminui-hardware.sh", ["smart", device], timeout=30)

    def get_hardware_sensors(self) -> Dict[str, Any]:
        """
        温度センサー情報を取得 (sensors -j or /sys/class/thermal/)

        Returns:
            センサー情報の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-hardware.sh", ["sensors"], timeout=10)

    def get_hardware_memory(self) -> Dict[str, Any]:
        """
        メモリ情報を取得 (/proc/meminfo)

        Returns:
            メモリ情報の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-hardware.sh", ["memory"], timeout=10)

    # ------------------------------------------------------------------
    # ファイアウォール（読み取り専用）
    # ------------------------------------------------------------------

    def get_firewall_rules(self) -> Dict[str, Any]:
        """
        ファイアウォールルール一覧を取得 (iptables-save / nft list ruleset)

        Returns:
            ルール情報の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-firewall.sh", ["rules"], timeout=15)

    def get_firewall_policy(self) -> Dict[str, Any]:
        """
        ファイアウォールデフォルトポリシーを取得

        Returns:
            ポリシー情報の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-firewall.sh", ["policy"], timeout=10)

    def get_firewall_status(self) -> Dict[str, Any]:
        """
        ファイアウォール全体状態を取得 (ufw/firewalld/iptables/nftables)

        Returns:
            状態情報の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-firewall.sh", ["status"], timeout=10)

    # ------------------------------------------------------------------
    # パッケージ管理（読み取り専用）
    # ------------------------------------------------------------------

    def get_packages_list(self) -> Dict[str, Any]:
        """
        インストール済みパッケージ一覧を取得 (dpkg-query)

        Returns:
            パッケージ情報の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-packages.sh", ["list"], timeout=30)

    def get_packages_updates(self) -> Dict[str, Any]:
        """
        更新可能なパッケージ一覧を取得 (apt list --upgradable)

        Returns:
            更新パッケージ情報の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-packages.sh", ["updates"], timeout=30)

    def get_packages_security(self) -> Dict[str, Any]:
        """
        セキュリティ更新一覧を取得

        Returns:
            セキュリティ更新情報の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-packages.sh", ["security"], timeout=30)


    # ------------------------------------------------------------------
    # SSH設定（読み取り専用）
    # ------------------------------------------------------------------

    def get_ssh_status(self) -> Dict[str, Any]:
        """
        SSHサービスの状態を取得 (systemctl status sshd)

        Returns:
            SSH状態情報の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-ssh.sh", ["status"], timeout=10)

    def get_ssh_config(self) -> Dict[str, Any]:
        """
        sshd_config の設定を読み取り・パース

        Returns:
            SSH設定情報の辞書（危険設定警告含む）

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-ssh.sh", ["config"], timeout=10)


# グローバルインスタンス
sudo_wrapper = SudoWrapper()
