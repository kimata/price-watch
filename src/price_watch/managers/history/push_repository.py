#!/usr/bin/env python3
"""Push サブスクリプション管理リポジトリ.

Web Push 通知のサブスクリプション情報を管理します。
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from price_watch.managers.history.connection import HistoryDBConnection


@dataclass(frozen=True)
class PushSubscription:
    """Push サブスクリプション."""

    id: int
    item_key: str
    endpoint: str
    p256dh: str
    auth: str
    created_at: str


@dataclass
class PushRepository:
    """Push サブスクリプションリポジトリ.

    Web Push 通知のサブスクリプション情報を管理します。
    読み取り専用データベースでも読み取り操作は正常に動作します。
    """

    db: HistoryDBConnection
    _table_exists: bool = field(default=False, init=False)
    _readonly: bool = field(default=False, init=False)

    def initialize_table(self) -> None:
        """テーブルを初期化.

        テーブルが存在しない場合に作成します。
        読み取り専用データベースの場合はスキップします。
        """
        try:
            with self.db.connect() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS push_subscriptions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        item_key TEXT NOT NULL,
                        endpoint TEXT NOT NULL,
                        p256dh TEXT NOT NULL,
                        auth TEXT NOT NULL,
                        created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                        UNIQUE(item_key, endpoint)
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_push_subscriptions_item_key
                    ON push_subscriptions(item_key)
                """)
                conn.commit()
            self._table_exists = True
        except sqlite3.OperationalError as e:
            if "readonly" in str(e).lower():
                logging.debug("Push subscriptions table not created: database is read-only")
                self._readonly = True
                # テーブルが存在するかチェック
                self._table_exists = self._check_table_exists()
            else:
                raise

    def _check_table_exists(self) -> bool:
        """テーブルが存在するかチェック."""
        try:
            with self.db.connect() as conn:
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='push_subscriptions'"
                )
                return cursor.fetchone() is not None
        except sqlite3.OperationalError:
            return False

    def subscribe(
        self,
        item_key: str,
        endpoint: str,
        p256dh: str,
        auth: str,
    ) -> int:
        """サブスクリプションを登録.

        既に存在する場合は更新します。

        Args:
            item_key: 監視対象アイテムキー
            endpoint: Push Service エンドポイント
            p256dh: 公開鍵
            auth: 認証シークレット

        Returns:
            サブスクリプション ID
        """
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO push_subscriptions (item_key, endpoint, p256dh, auth)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(item_key, endpoint) DO UPDATE SET
                    p256dh = excluded.p256dh,
                    auth = excluded.auth,
                    created_at = datetime('now', 'localtime')
                RETURNING id
                """,
                (item_key, endpoint, p256dh, auth),
            )
            row = cursor.fetchone()
            conn.commit()
            return row["id"] if row else 0

    def unsubscribe(self, item_key: str, endpoint: str) -> bool:
        """サブスクリプションを解除.

        Args:
            item_key: 監視対象アイテムキー
            endpoint: Push Service エンドポイント

        Returns:
            削除された場合 True
        """
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                DELETE FROM push_subscriptions
                WHERE item_key = ? AND endpoint = ?
                """,
                (item_key, endpoint),
            )
            conn.commit()
            return cursor.rowcount > 0

    def unsubscribe_all(self, endpoint: str) -> int:
        """指定エンドポイントの全サブスクリプションを解除.

        Args:
            endpoint: Push Service エンドポイント

        Returns:
            削除された件数
        """
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                DELETE FROM push_subscriptions
                WHERE endpoint = ?
                """,
                (endpoint,),
            )
            conn.commit()
            return cursor.rowcount

    def get_subscriptions(self, item_key: str) -> list[PushSubscription]:
        """アイテムのサブスクリプション一覧を取得.

        Args:
            item_key: 監視対象アイテムキー

        Returns:
            サブスクリプションリスト
        """
        if not self._table_exists:
            return []
        try:
            with self.db.connect() as conn:
                cursor = conn.execute(
                    """
                    SELECT id, item_key, endpoint, p256dh, auth, created_at
                    FROM push_subscriptions
                    WHERE item_key = ?
                    ORDER BY created_at DESC
                    """,
                    (item_key,),
                )
                return [
                    PushSubscription(
                        id=row["id"],
                        item_key=row["item_key"],
                        endpoint=row["endpoint"],
                        p256dh=row["p256dh"],
                        auth=row["auth"],
                        created_at=row["created_at"],
                    )
                    for row in cursor.fetchall()
                ]
        except sqlite3.OperationalError:
            return []

    def is_subscribed(self, item_key: str, endpoint: str) -> bool:
        """サブスクリプションが存在するか確認.

        Args:
            item_key: 監視対象アイテムキー
            endpoint: Push Service エンドポイント

        Returns:
            存在する場合 True
        """
        if not self._table_exists:
            return False
        try:
            with self.db.connect() as conn:
                cursor = conn.execute(
                    """
                    SELECT 1 FROM push_subscriptions
                    WHERE item_key = ? AND endpoint = ?
                    """,
                    (item_key, endpoint),
                )
                return cursor.fetchone() is not None
        except sqlite3.OperationalError:
            return False

    def delete_by_endpoint(self, endpoint: str) -> int:
        """エンドポイントでサブスクリプションを削除.

        失効したサブスクリプション（410応答）の削除に使用します。

        Args:
            endpoint: Push Service エンドポイント

        Returns:
            削除された件数
        """
        return self.unsubscribe_all(endpoint)

    def count_subscriptions(self, item_key: str) -> int:
        """アイテムのサブスクリプション数を取得.

        Args:
            item_key: 監視対象アイテムキー

        Returns:
            サブスクリプション数
        """
        if not self._table_exists:
            return 0
        try:
            with self.db.connect() as conn:
                cursor = conn.execute(
                    """
                    SELECT COUNT(*) as count FROM push_subscriptions
                    WHERE item_key = ?
                    """,
                    (item_key,),
                )
                row = cursor.fetchone()
                return row["count"] if row else 0
        except sqlite3.OperationalError:
            return 0
