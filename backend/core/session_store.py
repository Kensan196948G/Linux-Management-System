"""JWTセッションストア - JTIベースのセッション追跡とブロックリスト管理。"""

import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

SESSIONS_DB = Path("data/sessions.db")


class SessionStore:
    """アクティブJWTセッションの追跡とrevoke管理を行うクラス。"""

    def _get_conn(self) -> sqlite3.Connection:
        """DBコネクション取得（テーブル初期化込み）。"""
        SESSIONS_DB.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(SESSIONS_DB))
        conn.execute(
            """CREATE TABLE IF NOT EXISTS active_sessions (
                jti TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                username TEXT NOT NULL,
                email TEXT NOT NULL,
                role TEXT NOT NULL,
                ip_address TEXT,
                user_agent TEXT,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS revoked_sessions (
                jti TEXT PRIMARY KEY,
                revoked_at REAL NOT NULL
            )"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sess_email ON active_sessions (email)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sess_user ON active_sessions (user_id)")
        conn.commit()
        return conn

    def _cleanup(self, conn: sqlite3.Connection) -> None:
        """期限切れセッションとrevoke古エントリを削除する。"""
        now = time.time()
        conn.execute("DELETE FROM active_sessions WHERE expires_at < ?", (now,))
        conn.execute("DELETE FROM revoked_sessions WHERE revoked_at < ?", (now - 86400,))
        conn.commit()

    def register_session(
        self,
        jti: str,
        user_id: str,
        username: str,
        email: str,
        role: str,
        ip_address: str,
        user_agent: str,
        expires_at: float,
    ) -> None:
        """
        セッションを登録する。

        Args:
            jti: JWT ID（一意識別子）
            user_id: ユーザーID
            username: ユーザー名
            email: メールアドレス
            role: ユーザーロール
            ip_address: クライアントIPアドレス
            user_agent: User-Agentヘッダー
            expires_at: UNIX timestamp（有効期限）
        """
        now = time.time()
        with self._get_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO active_sessions
                   (jti, user_id, username, email, role, ip_address, user_agent, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (jti, user_id, username, email, role, ip_address, user_agent, now, expires_at),
            )
            self._cleanup(conn)

    def revoke_session(self, jti: str) -> bool:
        """
        セッションを無効化する（ブロックリストに追加）。

        Args:
            jti: 無効化するJWT ID

        Returns:
            True if revoked, False if not found
        """
        now = time.time()
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT jti FROM active_sessions WHERE jti = ?", (jti,))
            if not cursor.fetchone():
                return False
            conn.execute("DELETE FROM active_sessions WHERE jti = ?", (jti,))
            conn.execute(
                "INSERT OR REPLACE INTO revoked_sessions (jti, revoked_at) VALUES (?, ?)",
                (jti, now),
            )
            conn.commit()
            return True

    def revoke_user_sessions(self, email: str) -> int:
        """
        ユーザーの全セッションを無効化する。

        Args:
            email: 対象ユーザーのメールアドレス

        Returns:
            無効化したセッション数
        """
        now = time.time()
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT jti FROM active_sessions WHERE email = ?", (email,))
            jtis = [row[0] for row in cursor.fetchall()]
            for jti in jtis:
                conn.execute(
                    "INSERT OR REPLACE INTO revoked_sessions (jti, revoked_at) VALUES (?, ?)",
                    (jti, now),
                )
            conn.execute("DELETE FROM active_sessions WHERE email = ?", (email,))
            conn.commit()
            return len(jtis)

    def is_revoked(self, jti: str) -> bool:
        """
        セッションがブロックリストに存在するか確認する。

        Args:
            jti: JWT ID

        Returns:
            True if revoked
        """
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT jti FROM revoked_sessions WHERE jti = ?", (jti,))
            return cursor.fetchone() is not None

    def get_active_sessions(self) -> list[dict]:
        """
        アクティブセッション一覧を返す。

        Returns:
            セッション情報のリスト
        """
        now = time.time()
        with self._get_conn() as conn:
            self._cleanup(conn)
            cursor = conn.execute(
                """SELECT jti, user_id, username, email, role, ip_address, user_agent, created_at, expires_at
                   FROM active_sessions
                   WHERE expires_at > ?
                   ORDER BY created_at DESC""",
                (now,),
            )
            sessions = []
            for jti, user_id, username, email, role, ip_address, user_agent, created_at, expires_at in cursor.fetchall():
                sessions.append(
                    {
                        "session_id": jti,
                        "user_id": user_id,
                        "username": username,
                        "email": email,
                        "role": role,
                        "ip_address": ip_address or "unknown",
                        "user_agent": user_agent or "unknown",
                        "created_at": datetime.fromtimestamp(created_at, tz=timezone.utc).isoformat(),
                        "expires_at": datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat(),
                    }
                )
            return sessions


session_store = SessionStore()
