"""ログインレート制限 (ブルートフォース対策)"""

import sqlite3
import time
from pathlib import Path

RATE_LIMIT_DB = Path("data/rate_limit.db")
MAX_ATTEMPTS = 5  # 5回失敗でロック
LOCKOUT_DURATION = 300  # 5分間ロック
WINDOW_DURATION = 600  # 10分間のウィンドウ


class RateLimiter:
    """ログイン試行レート制限クラス。SQLiteでIP/メール単位の失敗回数を追跡する。"""

    def _get_conn(self) -> sqlite3.Connection:
        """DBコネクション取得（テーブル初期化込み）。"""
        RATE_LIMIT_DB.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(RATE_LIMIT_DB))
        conn.execute(
            """CREATE TABLE IF NOT EXISTS login_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT NOT NULL,
                email TEXT NOT NULL,
                timestamp REAL NOT NULL,
                success INTEGER NOT NULL DEFAULT 0
            )"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ip_ts ON login_attempts (ip, timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_email_ts ON login_attempts (email, timestamp)")
        conn.commit()
        return conn

    def check_and_record(self, ip: str, email: str) -> tuple[bool, int]:
        """
        ログイン失敗を記録し、ロック状態を返す。

        Args:
            ip: クライアントIPアドレス
            email: ログイン試行メールアドレス

        Returns:
            (allowed, remaining_seconds): allowedがFalseならロック中
        """
        now = time.time()
        window_start = now - WINDOW_DURATION

        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO login_attempts (ip, email, timestamp, success) VALUES (?, ?, ?, 0)",
                (ip, email, now),
            )
            conn.commit()

            cursor = conn.execute(
                """SELECT COUNT(*) FROM login_attempts
                   WHERE (ip = ? OR email = ?) AND timestamp > ? AND success = 0""",
                (ip, email, window_start),
            )
            count = cursor.fetchone()[0]

            if count >= MAX_ATTEMPTS:
                cursor = conn.execute(
                    """SELECT MIN(timestamp) FROM login_attempts
                       WHERE (ip = ? OR email = ?) AND timestamp > ? AND success = 0""",
                    (ip, email, window_start),
                )
                first_failure = cursor.fetchone()[0]
                lockout_end = first_failure + LOCKOUT_DURATION
                remaining = max(0, int(lockout_end - now))
                return False, remaining

        return True, 0

    def record_success(self, ip: str, email: str) -> None:
        """
        ログイン成功時にカウンタをリセットする。

        Args:
            ip: クライアントIPアドレス
            email: ログイン成功メールアドレス
        """
        now = time.time()
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO login_attempts (ip, email, timestamp, success) VALUES (?, ?, ?, 1)",
                (ip, email, now),
            )
            conn.execute(
                "DELETE FROM login_attempts WHERE (ip = ? OR email = ?) AND success = 0",
                (ip, email),
            )
            conn.commit()

    def is_locked(self, ip: str, email: str) -> tuple[bool, int]:
        """
        ロック状態を確認する。

        Args:
            ip: クライアントIPアドレス
            email: メールアドレス

        Returns:
            (locked, remaining_seconds)
        """
        now = time.time()
        window_start = now - WINDOW_DURATION

        with self._get_conn() as conn:
            cursor = conn.execute(
                """SELECT COUNT(*) FROM login_attempts
                   WHERE (ip = ? OR email = ?) AND timestamp > ? AND success = 0""",
                (ip, email, window_start),
            )
            count = cursor.fetchone()[0]

            if count >= MAX_ATTEMPTS:
                cursor = conn.execute(
                    """SELECT MIN(timestamp) FROM login_attempts
                       WHERE (ip = ? OR email = ?) AND timestamp > ? AND success = 0""",
                    (ip, email, window_start),
                )
                first_failure = cursor.fetchone()[0]
                lockout_end = first_failure + LOCKOUT_DURATION
                remaining = max(0, int(lockout_end - now))
                if remaining > 0:
                    return True, remaining

        return False, 0

    def get_all_locked(self) -> list[dict]:
        """
        ロック中のIP/メール一覧を返す。

        Returns:
            ロック中エントリのリスト
        """
        now = time.time()
        window_start = now - WINDOW_DURATION

        with self._get_conn() as conn:
            cursor = conn.execute(
                """SELECT ip, email, COUNT(*) as attempts, MIN(timestamp) as first_attempt
                   FROM login_attempts
                   WHERE timestamp > ? AND success = 0
                   GROUP BY ip, email
                   HAVING COUNT(*) >= ?""",
                (window_start, MAX_ATTEMPTS),
            )
            results = []
            for ip, email, attempts, first_attempt in cursor.fetchall():
                lockout_end = first_attempt + LOCKOUT_DURATION
                remaining = max(0, int(lockout_end - now))
                if remaining > 0:
                    results.append(
                        {
                            "ip": ip,
                            "email": email,
                            "attempts": attempts,
                            "locked_until": lockout_end,
                            "remaining_seconds": remaining,
                        }
                    )
        return results

    def clear_lock(self, identifier: str) -> bool:
        """
        特定のIP/メールのロックを解除する。

        Args:
            identifier: IPアドレスまたはメールアドレス

        Returns:
            True if cleared, False if not found
        """
        with self._get_conn() as conn:
            cursor = conn.execute(
                "DELETE FROM login_attempts WHERE ip = ? OR email = ?",
                (identifier, identifier),
            )
            conn.commit()
            return cursor.rowcount > 0


rate_limiter = RateLimiter()
