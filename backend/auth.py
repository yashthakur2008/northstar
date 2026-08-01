from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import time
from pathlib import Path


SESSION_SECONDS = 60 * 60 * 24 * 7


class AuthStore:
    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    display_name TEXT NOT NULL,
                    password_hash BLOB NOT NULL,
                    password_salt BLOB NOT NULL,
                    created_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS portfolio_holdings (
                    user_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    shares REAL NOT NULL CHECK (shares > 0),
                    average_cost REAL,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY (user_id, symbol),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS oauth_identities (
                    provider TEXT NOT NULL,
                    provider_user_id TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY (provider, provider_user_id),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                """
            )

    def oauth_user(self, provider: str, provider_user_id: str, email: str, display_name: str) -> dict:
        now = int(time.time())
        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT users.id, users.email, users.display_name
                FROM oauth_identities
                JOIN users ON users.id = oauth_identities.user_id
                WHERE provider = ? AND provider_user_id = ?
                """,
                (provider, provider_user_id),
            ).fetchone()
            if existing is not None:
                return dict(existing)
            user = connection.execute(
                "SELECT id, email, display_name FROM users WHERE email = ? COLLATE NOCASE",
                (email,),
            ).fetchone()
            if user is None:
                salt = secrets.token_bytes(16)
                cursor = connection.execute(
                    """
                    INSERT INTO users (email, display_name, password_hash, password_salt, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (email, display_name, self._password_hash(secrets.token_urlsafe(48), salt), salt, now),
                )
                user_id = cursor.lastrowid
                user = {"id": user_id, "email": email, "display_name": display_name}
            connection.execute(
                """
                INSERT INTO oauth_identities (provider, provider_user_id, user_id, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (provider, provider_user_id, user["id"], now),
            )
        return dict(user)

    @staticmethod
    def _password_hash(password: str, salt: bytes) -> bytes:
        return hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=2**14,
            r=8,
            p=1,
            dklen=64,
        )

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create_user(self, email: str, display_name: str, password: str) -> dict:
        salt = secrets.token_bytes(16)
        password_hash = self._password_hash(password, salt)
        now = int(time.time())
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO users (email, display_name, password_hash, password_salt, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (email, display_name, password_hash, salt, now),
                )
                user_id = cursor.lastrowid
        except sqlite3.IntegrityError as error:
            raise ValueError("account_exists") from error
        return {"id": user_id, "email": email, "display_name": display_name}

    def authenticate(self, email: str, password: str) -> dict | None:
        with self._connect() as connection:
            user = connection.execute(
                """
                SELECT id, email, display_name, password_hash, password_salt
                FROM users WHERE email = ?
                """,
                (email,),
            ).fetchone()
        if user is None:
            # Perform equivalent work so missing accounts are not significantly faster.
            self._password_hash(password, b"\0" * 16)
            return None
        candidate = self._password_hash(password, user["password_salt"])
        if not hmac.compare_digest(candidate, user["password_hash"]):
            return None
        return {
            "id": user["id"],
            "email": user["email"],
            "display_name": user["display_name"],
        }

    def create_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        with self._connect() as connection:
            connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
            connection.execute(
                """
                INSERT INTO sessions (token_hash, user_id, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (self._token_hash(token), user_id, now, now + SESSION_SECONDS),
            )
        return token

    def user_for_session(self, token: str | None) -> dict | None:
        if not token:
            return None
        now = int(time.time())
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT users.id, users.email, users.display_name
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token_hash = ? AND sessions.expires_at > ?
                """,
                (self._token_hash(token), now),
            ).fetchone()
        if row is None:
            return None
        return {"id": row["id"], "email": row["email"], "display_name": row["display_name"]}

    def delete_session(self, token: str | None) -> None:
        if not token:
            return
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM sessions WHERE token_hash = ?",
                (self._token_hash(token),),
            )

    def portfolio_holdings(self, user_id: int) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT symbol, shares, average_cost
                FROM portfolio_holdings WHERE user_id = ? ORDER BY updated_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_holding(self, user_id: int, symbol: str, shares: float, average_cost: float | None) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO portfolio_holdings (user_id, symbol, shares, average_cost, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, symbol) DO UPDATE SET
                    shares = excluded.shares,
                    average_cost = excluded.average_cost,
                    updated_at = excluded.updated_at
                """,
                (user_id, symbol, shares, average_cost, int(time.time())),
            )

    def delete_holding(self, user_id: int, symbol: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM portfolio_holdings WHERE user_id = ? AND symbol = ?",
                (user_id, symbol),
            )
