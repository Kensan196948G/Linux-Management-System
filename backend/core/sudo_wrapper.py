"""
sudo ラッパー呼び出しモジュール

CLAUDE.md のセキュリティ原則に従った安全な sudo 実行
"""

import json
import logging
import re
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

    # ==================================================================
    # DB モニタリング（MySQL/PostgreSQL）
    # ==================================================================

    _ALLOWED_DB_TYPES = ("mysql", "postgresql")
    _ALLOWED_MYSQL_CMDS = ("status", "processlist", "variables", "databases")
    _ALLOWED_PG_CMDS = ("status", "connections", "databases", "activity")

    def get_db_status(self, db_type: str) -> Dict[str, Any]:
        """DB サービス状態を取得

        Args:
            db_type: データベース種別（mysql/postgresql）

        Returns:
            DB 状態の辞書
        """
        if db_type not in self._ALLOWED_DB_TYPES:
            raise ValueError(f"DB type not allowed: {db_type}")
        return self._execute("adminui-dbmonitor.sh", [db_type, "status"], timeout=15)

    def get_db_processlist(self, db_type: str) -> Dict[str, Any]:
        """DB プロセス一覧を取得（MySQL: SHOW PROCESSLIST / PostgreSQL: pg_stat_activity）

        Args:
            db_type: データベース種別（mysql/postgresql）

        Returns:
            プロセス一覧の辞書
        """
        if db_type not in self._ALLOWED_DB_TYPES:
            raise ValueError(f"DB type not allowed: {db_type}")
        cmd = "processlist" if db_type == "mysql" else "activity"
        return self._execute("adminui-dbmonitor.sh", [db_type, cmd], timeout=15)

    def get_db_databases(self, db_type: str) -> Dict[str, Any]:
        """DB データベース一覧を取得

        Args:
            db_type: データベース種別（mysql/postgresql）

        Returns:
            データベース一覧の辞書
        """
        if db_type not in self._ALLOWED_DB_TYPES:
            raise ValueError(f"DB type not allowed: {db_type}")
        return self._execute("adminui-dbmonitor.sh", [db_type, "databases"], timeout=15)

    def get_db_connections(self, db_type: str) -> Dict[str, Any]:
        """DB 接続一覧を取得（PostgreSQL のみ）

        Args:
            db_type: データベース種別（postgresql）

        Returns:
            接続一覧の辞書
        """
        if db_type not in self._ALLOWED_DB_TYPES:
            raise ValueError(f"DB type not allowed: {db_type}")
        cmd = "connections" if db_type == "postgresql" else "processlist"
        return self._execute("adminui-dbmonitor.sh", [db_type, cmd], timeout=15)

    def get_db_variables(self, db_type: str) -> Dict[str, Any]:
        """DB 変数・設定を取得（MySQL: SHOW VARIABLES）

        Args:
            db_type: データベース種別（mysql）

        Returns:
            変数の辞書
        """
        if db_type not in self._ALLOWED_DB_TYPES:
            raise ValueError(f"DB type not allowed: {db_type}")
        cmd = "variables" if db_type == "mysql" else "status"
        return self._execute("adminui-dbmonitor.sh", [db_type, cmd], timeout=15)

    # ==================================================================
    # 帯域幅監視（vnstat / ip）
    # ==================================================================

    _IFACE_PATTERN = re.compile(r"^[a-zA-Z0-9._-]{1,32}$")

    def _validate_iface(self, iface: str) -> None:
        """インターフェース名をバリデーション"""
        if not self._IFACE_PATTERN.match(iface):
            raise ValueError(f"Invalid interface name: {iface}")

    def get_bandwidth_interfaces(self) -> Dict[str, Any]:
        """ネットワークインターフェース一覧を取得

        Returns:
            インターフェース一覧の辞書
        """
        return self._execute("adminui-bandwidth.sh", ["list"], timeout=10)

    def get_bandwidth_summary(self, iface: str = "") -> Dict[str, Any]:
        """帯域幅サマリ統計を取得（vnstat / ip -s link）

        Args:
            iface: インターフェース名（省略時: 全体）

        Returns:
            サマリ統計の辞書
        """
        if iface:
            self._validate_iface(iface)
        args = ["summary"] + ([iface] if iface else [])
        return self._execute("adminui-bandwidth.sh", args, timeout=15)

    def get_bandwidth_daily(self, iface: str = "") -> Dict[str, Any]:
        """日別帯域幅統計を取得（vnstat -d）

        Args:
            iface: インターフェース名（省略時: 全体）

        Returns:
            日別統計の辞書
        """
        if iface:
            self._validate_iface(iface)
        args = ["daily"] + ([iface] if iface else [])
        return self._execute("adminui-bandwidth.sh", args, timeout=15)

    def get_bandwidth_hourly(self, iface: str = "") -> Dict[str, Any]:
        """時間別帯域幅統計を取得（vnstat -h）

        Args:
            iface: インターフェース名（省略時: 全体）

        Returns:
            時間別統計の辞書
        """
        if iface:
            self._validate_iface(iface)
        args = ["hourly"] + ([iface] if iface else [])
        return self._execute("adminui-bandwidth.sh", args, timeout=15)

    def get_bandwidth_live(self, iface: str = "") -> Dict[str, Any]:
        """リアルタイム帯域幅を取得（1秒サンプリング）

        Args:
            iface: インターフェース名（省略時: デフォルトルートのIF）

        Returns:
            リアルタイム帯域幅の辞書 (rx_bps/tx_bps)
        """
        if iface:
            self._validate_iface(iface)
        args = ["live"] + ([iface] if iface else [])
        return self._execute("adminui-bandwidth.sh", args, timeout=10)

    def get_bandwidth_top(self) -> Dict[str, Any]:
        """全インターフェースの累積トラフィック統計を取得

        Returns:
            インターフェース別トラフィック統計の辞書
        """
        return self._execute("adminui-bandwidth.sh", ["top"], timeout=10)

    # ===================================================================
    # Apache Webserver 管理メソッド
    # ===================================================================

    def get_apache_status(self) -> Dict[str, Any]:
        """Apache サービス状態を取得

        Returns:
            Apache サービス状態の辞書（active/enabled/version）
        """
        return self._execute("adminui-apache.sh", ["status"], timeout=15)

    def get_apache_vhosts(self) -> Dict[str, Any]:
        """Apache 仮想ホスト一覧を取得

        Returns:
            仮想ホスト一覧の辞書
        """
        return self._execute("adminui-apache.sh", ["vhosts"], timeout=15)

    def get_apache_modules(self) -> Dict[str, Any]:
        """Apache ロード済みモジュール一覧を取得

        Returns:
            モジュール一覧の辞書
        """
        return self._execute("adminui-apache.sh", ["modules"], timeout=15)

    def get_apache_config_check(self) -> Dict[str, Any]:
        """Apache 設定ファイル構文チェック

        Returns:
            構文チェック結果の辞書（syntax_ok: bool）
        """
        return self._execute("adminui-apache.sh", ["config-check"], timeout=15)

    # ===================================================================
    # FTP Server (ProFTPD/vsftpd) メソッド
    # ===================================================================

    def get_ftp_status(self) -> Dict[str, Any]:
        """FTP サービス状態を取得 (proftpd/vsftpd)

        Returns:
            FTP サービス状態の辞書（active/enabled/version）

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-proftpd.sh", ["status"], timeout=15)

    def get_ftp_users(self) -> Dict[str, Any]:
        """FTP 許可ユーザー一覧を取得 (/etc/ftpusers 等)

        Returns:
            FTP ユーザー一覧の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-proftpd.sh", ["users"], timeout=15)

    def get_ftp_sessions(self) -> Dict[str, Any]:
        """FTP アクティブセッションを取得 (ss -tnp ポート21)

        Returns:
            アクティブセッションの辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-proftpd.sh", ["sessions"], timeout=15)

    def get_ftp_logs(self, lines: int = 50) -> Dict[str, Any]:
        """FTP ログを取得 (journalctl / /var/log/proftpd/)

        Args:
            lines: 取得するログ行数（1〜200）

        Returns:
            FTP ログの辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        safe_lines = max(1, min(200, lines))
        return self._execute("adminui-proftpd.sh", ["logs", str(safe_lines)], timeout=15)

    # ===================================================================
    # Squid Proxy Server メソッド
    # ===================================================================

    def get_squid_status(self) -> Dict[str, Any]:
        """Squid サービス状態を取得

        Returns:
            Squid サービス状態の辞書（active/enabled/version）

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-squid.sh", ["status"], timeout=15)

    def get_squid_cache(self) -> Dict[str, Any]:
        """Squid キャッシュ統計を取得 (squidclient mgr:info)

        Returns:
            キャッシュ統計の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-squid.sh", ["cache"], timeout=15)

    def get_squid_logs(self, lines: int = 50) -> Dict[str, Any]:
        """Squid アクセスログを取得 (/var/log/squid/access.log)

        Args:
            lines: 取得するログ行数（1〜200）

        Returns:
            Squid ログの辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        safe_lines = max(1, min(200, lines))
        return self._execute("adminui-squid.sh", ["logs", str(safe_lines)], timeout=15)

    def get_squid_config_check(self) -> Dict[str, Any]:
        """Squid 設定ファイル構文チェック (squid -k check)

        Returns:
            構文チェック結果の辞書（syntax_ok: bool）

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-squid.sh", ["config-check"], timeout=15)

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

    def get_packages_upgrade_dryrun(self) -> Dict[str, Any]:
        """アップグレードのドライランを実行（実際のインストールは行わない）

        Returns:
            アップグレード対象パッケージの辞書
        """
        return self._execute("adminui-packages.sh", ["upgrade-dryrun"], timeout=60)

    def upgrade_package(self, package_name: str) -> Dict[str, Any]:
        """特定パッケージをアップグレードする（承認フロー経由で呼び出すこと）

        Args:
            package_name: アップグレード対象パッケージ名

        Returns:
            実行結果の辞書
        """
        return self._execute("adminui-packages.sh", ["upgrade", package_name], timeout=120)

    def upgrade_all_packages(self) -> Dict[str, Any]:
        """全パッケージをアップグレードする（承認フロー経由で呼び出すこと・Admin のみ）

        Returns:
            実行結果の辞書
        """
        return self._execute("adminui-packages.sh", ["upgrade-all"], timeout=300)


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

    # ------------------------------------------------------------------
    # ユーザー属性変更（承認後自動実行）
    # ------------------------------------------------------------------

    def modify_user_shell(self, username: str, shell: str) -> Dict[str, Any]:
        """ユーザーのログインシェルを変更 (adminui-user-modify.sh set-shell)"""
        return self._execute("adminui-user-modify.sh", ["set-shell", username, shell], timeout=15)

    def modify_user_gecos(self, username: str, gecos: str) -> Dict[str, Any]:
        """ユーザーのGECOS（表示名）を変更 (adminui-user-modify.sh set-gecos)"""
        return self._execute("adminui-user-modify.sh", ["set-gecos", username, gecos], timeout=15)

    def modify_user_add_group(self, username: str, group: str) -> Dict[str, Any]:
        """ユーザーをグループに追加 (adminui-user-modify.sh add-group)"""
        return self._execute("adminui-user-modify.sh", ["add-group", username, group], timeout=15)

    def modify_user_remove_group(self, username: str, group: str) -> Dict[str, Any]:
        """ユーザーをグループから削除 (adminui-user-modify.sh remove-group)"""
        return self._execute("adminui-user-modify.sh", ["remove-group", username, group], timeout=15)

    # ------------------------------------------------------------------
    # ファイアウォール書き込み（承認後自動実行）
    # ------------------------------------------------------------------

    def allow_firewall_port(self, port: int, protocol: str = "tcp") -> Dict[str, Any]:
        """UFWポート許可ルール追加"""
        return self._execute("adminui-firewall-write.sh", ["allow-port", str(port), protocol])

    def deny_firewall_port(self, port: int, protocol: str = "tcp") -> Dict[str, Any]:
        """UFWポート拒否ルール追加"""
        return self._execute("adminui-firewall-write.sh", ["deny-port", str(port), protocol])

    def delete_firewall_rule(self, rule_num: int) -> Dict[str, Any]:
        """UFWルール削除"""
        return self._execute("adminui-firewall-write.sh", ["delete-rule", str(rule_num)])

    # ------------------------------------------------------------------
    # ファイルシステム情報取得
    # ------------------------------------------------------------------

    def get_filesystem_usage(self) -> Dict[str, Any]:
        """ファイルシステム使用量を取得"""
        return self._execute("adminui-filesystem.sh", ["df"])

    def get_filesystem_du(self, path: str = "/") -> Dict[str, Any]:
        """ディレクトリ使用量を取得"""
        return self._execute("adminui-filesystem.sh", ["du", path])

    def get_filesystem_mounts(self) -> Dict[str, Any]:
        """マウントポイント一覧を取得"""
        return self._execute("adminui-filesystem.sh", ["mounts"])

    # ===================================================================
    # Bootup / Shutdown 管理
    # ===================================================================

    def get_bootup_status(self) -> Dict[str, Any]:
        """起動状態（default target、uptime等）を取得"""
        return self._execute("adminui-bootup.sh", ["status"])

    def get_bootup_services(self) -> Dict[str, Any]:
        """起動時有効化サービス一覧を取得"""
        return self._execute("adminui-bootup.sh", ["services"])

    def enable_service_at_boot(self, service: str) -> Dict[str, Any]:
        """サービスを起動時に有効化する（承認フロー経由で呼び出すこと）

        Args:
            service: 有効化するサービス名（allowlist検証済み）

        Returns:
            実行結果の辞書
        """
        return self._execute("adminui-bootup.sh", ["enable", service])

    def disable_service_at_boot(self, service: str) -> Dict[str, Any]:
        """サービスを起動時に無効化する（承認フロー経由で呼び出すこと）

        Args:
            service: 無効化するサービス名（allowlist検証済み）

        Returns:
            実行結果の辞書
        """
        return self._execute("adminui-bootup.sh", ["disable", service])

    def schedule_shutdown(self, delay: str = "+1") -> Dict[str, Any]:
        """システムシャットダウンをスケジュールする（承認フロー必須・Admin のみ）

        Args:
            delay: 遅延指定（+N分、HH:MM、now）

        Returns:
            実行結果の辞書
        """
        return self._execute("adminui-bootup.sh", ["shutdown", delay], timeout=30)

    def schedule_reboot(self, delay: str = "+1") -> Dict[str, Any]:
        """システム再起動をスケジュールする（承認フロー必須・Admin のみ）

        Args:
            delay: 遅延指定（+N分、HH:MM、now）

        Returns:
            実行結果の辞書
        """
        return self._execute("adminui-bootup.sh", ["reboot", delay], timeout=30)

    # ===================================================================
    # System Time 管理
    # ===================================================================

    def get_time_status(self) -> Dict[str, Any]:
        """システム時刻・タイムゾーン状態を取得"""
        return self._execute("adminui-time.sh", ["status"])

    def get_timezones(self) -> Dict[str, Any]:
        """利用可能なタイムゾーン一覧を取得"""
        return self._execute("adminui-time.sh", ["list-timezones"])

    def set_timezone(self, timezone: str) -> Dict[str, Any]:
        """タイムゾーンを設定する（承認フロー経由で呼び出すこと）

        Args:
            timezone: 設定するタイムゾーン（例: Asia/Tokyo）

        Returns:
            実行結果の辞書
        """
        return self._execute("adminui-time.sh", ["set-timezone", timezone])

    # ===================================================================
    # Disk Quota 管理
    # ===================================================================

    def get_quota_status(self, filesystem: str = "") -> Dict[str, Any]:
        """ディスククォータの全体状態を取得

        Args:
            filesystem: 対象ファイルシステム（省略時は全体）

        Returns:
            実行結果の辞書
        """
        args = ["status"]
        if filesystem:
            args.append(filesystem)
        return self._execute("adminui-quotas.sh", args)

    def get_user_quota(self, username: str) -> Dict[str, Any]:
        """特定ユーザーのクォータ情報を取得

        Args:
            username: ユーザー名（allowlist検証済み）

        Returns:
            実行結果の辞書
        """
        return self._execute("adminui-quotas.sh", ["user", username])

    def get_group_quota(self, groupname: str) -> Dict[str, Any]:
        """特定グループのクォータ情報を取得

        Args:
            groupname: グループ名（allowlist検証済み）

        Returns:
            実行結果の辞書
        """
        return self._execute("adminui-quotas.sh", ["group", groupname])

    def get_all_user_quotas(self, filesystem: str = "") -> Dict[str, Any]:
        """全ユーザーのクォータ一覧を取得

        Args:
            filesystem: 対象ファイルシステム（省略時は全体）

        Returns:
            実行結果の辞書
        """
        args = ["users"]
        if filesystem:
            args.append(filesystem)
        return self._execute("adminui-quotas.sh", args)

    def set_user_quota(
        self,
        username: str,
        filesystem: str,
        soft_kb: int,
        hard_kb: int,
        isoft: int = 0,
        ihard: int = 0,
    ) -> Dict[str, Any]:
        """ユーザーのディスククォータを設定（承認フロー経由で呼び出すこと）

        Args:
            username: 対象ユーザー名
            filesystem: 対象ファイルシステム
            soft_kb: ソフトリミット（KB）
            hard_kb: ハードリミット（KB）
            isoft: inode ソフトリミット（省略時0=無制限）
            ihard: inode ハードリミット（省略時0=無制限）

        Returns:
            実行結果の辞書
        """
        return self._execute(
            "adminui-quotas.sh",
            ["set", "user", username, filesystem, str(soft_kb), str(hard_kb), str(isoft), str(ihard)],
        )

    def set_group_quota(
        self,
        groupname: str,
        filesystem: str,
        soft_kb: int,
        hard_kb: int,
        isoft: int = 0,
        ihard: int = 0,
    ) -> Dict[str, Any]:
        """グループのディスククォータを設定（承認フロー経由で呼び出すこと）

        Args:
            groupname: 対象グループ名
            filesystem: 対象ファイルシステム
            soft_kb: ソフトリミット（KB）
            hard_kb: ハードリミット（KB）
            isoft: inode ソフトリミット（省略時0=無制限）
            ihard: inode ハードリミット（省略時0=無制限）

        Returns:
            実行結果の辞書
        """
        return self._execute(
            "adminui-quotas.sh",
            ["set", "group", groupname, filesystem, str(soft_kb), str(hard_kb), str(isoft), str(ihard)],
        )

    def get_quota_report(self, filesystem: str = "") -> Dict[str, Any]:
        """クォータレポートを取得

        Args:
            filesystem: 対象ファイルシステム（省略時は全体）

        Returns:
            実行結果の辞書
        """
        args = ["report"]
        if filesystem:
            args.append(filesystem)
        return self._execute("adminui-quotas.sh", args)

    # ────────── Postfix / SMTP ──────────

    def get_postfix_status(self) -> Dict[str, Any]:
        """Postfix サービス状態を取得

        Returns:
            実行結果の辞書
        """
        return self._execute("adminui-postfix.sh", ["status"])

    def get_postfix_queue(self) -> Dict[str, Any]:
        """Postfix メールキューを取得

        Returns:
            実行結果の辞書
        """
        return self._execute("adminui-postfix.sh", ["queue"])

    def get_postfix_logs(self, lines: int = 50) -> Dict[str, Any]:
        """Postfix ログを取得

        Args:
            lines: 取得行数 (1-200)

        Returns:
            実行結果の辞書
        """
        safe_lines = max(1, min(200, lines))
        return self._execute("adminui-postfix.sh", ["logs", str(safe_lines)])

    def get_netstat_connections(self) -> Dict[str, Any]:
        """アクティブ接続一覧を取得

        Returns:
            実行結果の辞書
        """
        return self._execute("adminui-netstat.sh", ["connections"])

    def get_netstat_listening(self) -> Dict[str, Any]:
        """リスニングポート一覧を取得

        Returns:
            実行結果の辞書
        """
        return self._execute("adminui-netstat.sh", ["listening"])

    def get_netstat_stats(self) -> Dict[str, Any]:
        """ネットワーク統計サマリを取得

        Returns:
            実行結果の辞書
        """
        return self._execute("adminui-netstat.sh", ["stats"])

    def get_netstat_routes(self) -> Dict[str, Any]:
        """ルーティングテーブルを取得

        Returns:
            実行結果の辞書
        """
        return self._execute("adminui-netstat.sh", ["routes"])

    def get_bind_status(self) -> Dict[str, Any]:
        """BIND DNS サービス状態を取得

        Returns:
            実行結果の辞書
        """
        return self._execute("adminui-bind.sh", ["status"])

    def get_bind_zones(self) -> Dict[str, Any]:
        """BIND ゾーン一覧を取得

        Returns:
            実行結果の辞書
        """
        return self._execute("adminui-bind.sh", ["zones"])

    def get_bind_config(self) -> Dict[str, Any]:
        """BIND 設定確認を取得 (named-checkconf)

        Returns:
            実行結果の辞書
        """
        return self._execute("adminui-bind.sh", ["config"])

    def get_bind_logs(self, lines: int = 50) -> Dict[str, Any]:
        """BIND DNS ログを取得

        Args:
            lines: 取得行数 (1-200)

        Returns:
            実行結果の辞書
        """
        safe_lines = max(1, min(200, lines))
        return self._execute("adminui-bind.sh", ["logs", str(safe_lines)])

    def get_postgresql_status(self) -> Dict[str, Any]:
        """PostgreSQL サービス状態を取得

        Returns:
            PostgreSQL サービス状態の辞書（active/enabled/version/ready）
        """
        return self._execute("adminui-postgresql.sh", ["status"], timeout=15)

    def get_postgresql_databases(self) -> Dict[str, Any]:
        """PostgreSQL データベース一覧を取得

        Returns:
            データベース一覧の辞書
        """
        return self._execute("adminui-postgresql.sh", ["databases"], timeout=15)

    def get_postgresql_users(self) -> Dict[str, Any]:
        """PostgreSQL ユーザー/ロール一覧を取得

        Returns:
            ユーザー/ロール一覧の辞書
        """
        return self._execute("adminui-postgresql.sh", ["users"], timeout=15)

    def get_postgresql_activity(self) -> Dict[str, Any]:
        """PostgreSQL 接続・クエリ状況を取得

        Returns:
            pg_stat_activity の辞書
        """
        return self._execute("adminui-postgresql.sh", ["activity"], timeout=15)

    def get_postgresql_config(self) -> Dict[str, Any]:
        """PostgreSQL 設定パラメータを取得

        Returns:
            pg_settings 主要項目の辞書
        """
        return self._execute("adminui-postgresql.sh", ["config"], timeout=15)

    def get_postgresql_logs(self, lines: int = 50) -> Dict[str, Any]:
        """PostgreSQL ログを取得

        Args:
            lines: 取得行数 (1-200)

        Returns:
            実行結果の辞書
        """
        safe_lines = max(1, min(200, lines))
        return self._execute("adminui-postgresql.sh", ["logs", str(safe_lines)], timeout=15)

    # ────────── MySQL / MariaDB ──────────

    def get_mysql_status(self) -> Dict[str, Any]:
        """MySQL/MariaDB サービス状態・バージョンを取得

        Returns:
            実行結果の辞書
        """
        return self._execute("adminui-mysql.sh", ["status"])

    def get_mysql_databases(self) -> Dict[str, Any]:
        """データベース一覧を取得

        Returns:
            実行結果の辞書
        """
        return self._execute("adminui-mysql.sh", ["databases"])

    def get_mysql_users(self) -> Dict[str, Any]:
        """ユーザー一覧を取得（パスワードハッシュ除外）

        Returns:
            実行結果の辞書
        """
        return self._execute("adminui-mysql.sh", ["users"])

    def get_mysql_processes(self) -> Dict[str, Any]:
        """プロセスリストを取得

        Returns:
            実行結果の辞書
        """
        return self._execute("adminui-mysql.sh", ["processlist"])

    def get_mysql_variables(self) -> Dict[str, Any]:
        """システム変数（重要なもの）を取得

        Returns:
            実行結果の辞書
        """
        return self._execute("adminui-mysql.sh", ["variables"])

    def get_mysql_logs(self, lines: int = 50) -> Dict[str, Any]:
        """MySQL エラーログを取得

        Args:
            lines: 取得行数 (1-200)

        Returns:
            実行結果の辞書
        """
        safe_lines = max(1, min(200, lines))
        return self._execute("adminui-mysql.sh", ["logs", str(safe_lines)])

    # ===================================================================
    # SMART Drive Status メソッド
    # ===================================================================

    def get_smart_disks(self) -> Dict[str, Any]:
        """SMART 対応ディスク一覧を取得 (lsblk 経由)

        Returns:
            ディスク一覧と smartctl 有無の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-smart.sh", ["list"], timeout=15)

    def get_smart_info(self, disk: str) -> Dict[str, Any]:
        """ディスク詳細情報を取得 (smartctl -i)

        Args:
            disk: ディスクデバイスパス（allowlist 検証済み）

        Returns:
            ディスク詳細情報の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-smart.sh", ["info", disk], timeout=15)

    def get_smart_health(self, disk: str) -> Dict[str, Any]:
        """ディスク健全性を取得 (smartctl -H)

        Args:
            disk: ディスクデバイスパス（allowlist 検証済み）

        Returns:
            健全性チェック結果の辞書（health: PASSED/FAILED/unknown）

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-smart.sh", ["health", disk], timeout=15)

    def get_smart_tests(self) -> Dict[str, Any]:
        """SMART selftest ログ一覧を取得 (smartctl -l selftest)

        Returns:
            全ディスクの selftest ログ一覧の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-smart.sh", ["tests"], timeout=30)

    # ===================================================================
    # Disk Partitions メソッド
    # ===================================================================

    def get_partitions_list(self) -> Dict[str, Any]:
        """パーティション一覧を取得 (lsblk -J)

        Returns:
            パーティション一覧の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-partitions.sh", ["list"], timeout=15)

    def get_partitions_usage(self) -> Dict[str, Any]:
        """ディスク使用量を取得 (df -h)

        Returns:
            ディスク使用量の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-partitions.sh", ["usage"], timeout=15)

    def get_partitions_detail(self) -> Dict[str, Any]:
        """ブロックデバイス詳細を取得 (blkid)

        Returns:
            ブロックデバイス詳細の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-partitions.sh", ["detail"], timeout=15)

    def get_dhcp_status(self) -> Dict[str, Any]:
        """DHCP サービス状態を取得

        Returns:
            実行結果の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-dhcp.sh", ["status"])

    def get_dhcp_leases(self) -> Dict[str, Any]:
        """DHCP アクティブリース一覧を取得

        Returns:
            実行結果の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-dhcp.sh", ["leases"])

    def get_dhcp_config(self) -> Dict[str, Any]:
        """DHCP 設定サマリを取得

        Returns:
            実行結果の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-dhcp.sh", ["config"])

    def get_dhcp_pools(self) -> Dict[str, Any]:
        """DHCP アドレスプール情報を取得

        Returns:
            実行結果の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-dhcp.sh", ["pools"])

    def get_dhcp_logs(self, lines: int = 50) -> Dict[str, Any]:
        """DHCP ログを取得

        Args:
            lines: 取得行数 (1-200)

        Returns:
            実行結果の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        safe_lines = max(1, min(200, lines))
        return self._execute("adminui-dhcp.sh", ["logs", str(safe_lines)])


# グローバルインスタンス

    # ------------------------------------------------------------------
    # センサー (lm-sensors)
    # ------------------------------------------------------------------

    def get_sensors_all(self) -> Dict[str, Any]:
        """
        全センサー情報を取得 (sensors -j)

        Returns:
            全センサー情報の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-sensors.sh", ["all"], timeout=15)

    def get_sensors_temperature(self) -> Dict[str, Any]:
        """
        温度センサー情報を取得

        Returns:
            温度センサー情報の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-sensors.sh", ["temperature"], timeout=15)

    def get_sensors_fans(self) -> Dict[str, Any]:
        """
        ファン速度情報を取得 (RPM)

        Returns:
            ファン速度情報の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-sensors.sh", ["fans"], timeout=15)

    def get_sensors_voltage(self) -> Dict[str, Any]:
        """
        電圧センサー情報を取得

        Returns:
            電圧センサー情報の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-sensors.sh", ["voltage"], timeout=15)

    # ------------------------------------------------------------------
    # ルーティング・ゲートウェイ
    # ------------------------------------------------------------------

    def get_routing_routes(self) -> Dict[str, Any]:
        """
        ルーティングテーブルを取得 (ip route show)

        Returns:
            ルーティングテーブルの辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-routing.sh", ["routes"], timeout=15)

    def get_routing_gateways(self) -> Dict[str, Any]:
        """
        デフォルトゲートウェイ情報を取得 (ip route show default)

        Returns:
            ゲートウェイ情報の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-routing.sh", ["gateways"], timeout=15)

    def get_routing_arp(self) -> Dict[str, Any]:
        """
        ARP テーブルを取得 (ip neigh show)

        Returns:
            ARP テーブルの辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-routing.sh", ["arp"], timeout=15)

    def get_routing_interfaces(self) -> Dict[str, Any]:
        """
        インターフェース詳細を取得 (ip addr show)

        Returns:
            インターフェース情報の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-routing.sh", ["interfaces"], timeout=15)

    # ------------------------------------------------------------------
    # システム設定
    # ------------------------------------------------------------------

    def get_sysconfig_hostname(self) -> Dict[str, Any]:
        """
        ホスト名情報を取得 (hostname)

        Returns:
            ホスト名情報の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-sysconfig.sh", ["hostname"], timeout=10)

    def get_sysconfig_timezone(self) -> Dict[str, Any]:
        """
        タイムゾーン情報を取得 (timedatectl show / /etc/timezone)

        Returns:
            タイムゾーン情報の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-sysconfig.sh", ["timezone"], timeout=10)

    def get_sysconfig_locale(self) -> Dict[str, Any]:
        """
        ロケール情報を取得 (localectl status)

        Returns:
            ロケール情報の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-sysconfig.sh", ["locale"], timeout=10)

    def get_sysconfig_kernel(self) -> Dict[str, Any]:
        """
        カーネル情報を取得 (uname -a / /proc/version)

        Returns:
            カーネル情報の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-sysconfig.sh", ["kernel"], timeout=10)

    def get_sysconfig_uptime(self) -> Dict[str, Any]:
        """
        システム稼働時間を取得 (uptime / /proc/uptime)

        Returns:
            稼働時間情報の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-sysconfig.sh", ["uptime"], timeout=10)

    def get_sysconfig_modules(self) -> Dict[str, Any]:
        """
        カーネルモジュール一覧を取得 (lsmod)

        Returns:
            カーネルモジュール一覧の辞書

        Raises:
            SudoWrapperError: 実行失敗時
        """
        return self._execute("adminui-sysconfig.sh", ["modules"], timeout=15)


# グローバルインスタンス

sudo_wrapper = SudoWrapper()
