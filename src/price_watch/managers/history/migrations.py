#!/usr/bin/env python3
"""履歴 DB マイグレーション.

既存データベースのスキーマを新しいスキーマに移行します。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import my_lib.sqlite_util

from price_watch.managers.history.utils import url_hash

if TYPE_CHECKING:
    from price_watch.managers.history.connection import HistoryDBConnection


@dataclass
class HistoryMigrations:
    """履歴 DB マイグレーション.

    既存データベースのスキーマを新しいスキーマに移行します。
    """

    db: HistoryDBConnection

    def run_all(self) -> None:
        """全マイグレーションを実行.

        インデックス作成前に実行する必要があります。
        """
        self.migrate_to_nullable_price()
        self.migrate_to_nullable_stock()
        self.migrate_add_crawl_status()
        self.migrate_url_hash_to_item_key()

    def migrate_from_old_schema(self) -> None:
        """旧スキーマからデータをマイグレーション."""
        with my_lib.sqlite_util.connect(self.db.db_path) as conn:
            cur = conn.cursor()

            # 旧テーブルが存在するか確認
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='price_history'")
            if not cur.fetchone():
                logging.info("No old price_history table found")
                return

            # 旧テーブルの構造を確認（url カラムがあるかどうか）
            cur.execute("PRAGMA table_info(price_history)")
            columns = [row[1] for row in cur.fetchall()]

            if "url" not in columns:
                logging.info("Already migrated or new schema")
                return

            logging.info("Starting migration from old schema...")

            # 新しいテーブルを作成
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS items(
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    url_hash    TEXT NOT NULL UNIQUE,
                    url         TEXT NOT NULL,
                    name        TEXT NOT NULL,
                    store       TEXT NOT NULL,
                    thumb_url   TEXT,
                    created_at  TIMESTAMP DEFAULT(DATETIME('now','localtime')),
                    updated_at  TIMESTAMP DEFAULT(DATETIME('now','localtime'))
                )
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS price_history_new(
                    id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id INTEGER NOT NULL,
                    price   INTEGER NOT NULL,
                    stock   INTEGER NOT NULL,
                    time    TIMESTAMP DEFAULT(DATETIME('now','localtime')),
                    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
                )
                """
            )

            # 旧データからユニークなアイテムを抽出してitemsテーブルに挿入
            cur.execute(
                """
                SELECT DISTINCT url, name, store
                FROM price_history
                """
            )
            unique_items = cur.fetchall()

            item_id_map: dict[str, int] = {}
            for url, name, store in unique_items:
                hash_value = url_hash(url)
                cur.execute(
                    """
                    INSERT OR IGNORE INTO items (url_hash, url, name, store)
                    VALUES (?, ?, ?, ?)
                    """,
                    (hash_value, url, name, store),
                )
                cur.execute("SELECT id FROM items WHERE url_hash = ?", (hash_value,))
                item_id_map[url] = cur.fetchone()[0]

            # 価格履歴を新テーブルに移行
            cur.execute("SELECT url, price, stock, time FROM price_history")
            for url, price, stock, time_val in cur.fetchall():
                item_id = item_id_map.get(url)
                if item_id:
                    cur.execute(
                        """
                        INSERT INTO price_history_new (item_id, price, stock, time)
                        VALUES (?, ?, ?, ?)
                        """,
                        (item_id, price, stock, time_val),
                    )

            # 旧テーブルを削除し、新テーブルをリネーム
            cur.execute("DROP TABLE price_history")
            cur.execute("ALTER TABLE price_history_new RENAME TO price_history")

            # インデックスを作成
            cur.execute("CREATE INDEX IF NOT EXISTS idx_items_url_hash ON items(url_hash)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_price_history_item_id ON price_history(item_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_price_history_time ON price_history(time)")

        logging.info("Migration completed successfully")

    def migrate_to_nullable_price(self) -> None:
        """price カラムを NULL 許可に変更するマイグレーション.

        SQLite は ALTER COLUMN をサポートしていないため、
        テーブルを再作成してデータを移行する。
        """
        with my_lib.sqlite_util.connect(self.db.db_path) as conn:
            cur = conn.cursor()

            # テーブルが存在するか確認
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='price_history'")
            if not cur.fetchone():
                logging.info("No price_history table found")
                return

            # 現在のスキーマを確認（price カラムが NOT NULL かどうか）
            cur.execute("PRAGMA table_info(price_history)")
            columns = cur.fetchall()
            price_col = next((col for col in columns if col[1] == "price"), None)

            if price_col is None:
                logging.info("price column not found")
                return

            # notnull フラグ: 1 = NOT NULL, 0 = NULL 許可
            if price_col[3] == 0:
                logging.info("price column already allows NULL")
                return

            logging.info("Starting migration to allow NULL in price column...")

            # 新しいテーブルを作成（price に NULL を許可）
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS price_history_new(
                    id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id INTEGER NOT NULL,
                    price   INTEGER,
                    stock   INTEGER NOT NULL,
                    time    TIMESTAMP DEFAULT(DATETIME('now','localtime')),
                    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
                )
                """
            )

            # データを移行
            cur.execute(
                """
                INSERT INTO price_history_new (id, item_id, price, stock, time)
                SELECT id, item_id, price, stock, time FROM price_history
                """
            )

            # 旧テーブルを削除し、新テーブルをリネーム
            cur.execute("DROP TABLE price_history")
            cur.execute("ALTER TABLE price_history_new RENAME TO price_history")

            # インデックスを再作成
            cur.execute("CREATE INDEX IF NOT EXISTS idx_price_history_item_id ON price_history(item_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_price_history_time ON price_history(time)")

        logging.info("Migration to nullable price completed successfully")

    def migrate_to_nullable_stock(self) -> None:
        """stock カラムを NULL 許可に変更するマイグレーション.

        crawl_status=0 (失敗) の場合、stock は不明なため NULL を許可する。
        SQLite は ALTER COLUMN をサポートしていないため、
        テーブルを再作成してデータを移行する。
        """
        with my_lib.sqlite_util.connect(self.db.db_path) as conn:
            cur = conn.cursor()

            # テーブルが存在するか確認
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='price_history'")
            if not cur.fetchone():
                logging.info("No price_history table found")
                return

            # 現在のスキーマを確認（stock カラムが NOT NULL かどうか）
            cur.execute("PRAGMA table_info(price_history)")
            columns = cur.fetchall()
            stock_col = next((col for col in columns if col[1] == "stock"), None)

            if stock_col is None:
                logging.info("stock column not found")
                return

            # notnull フラグ: 1 = NOT NULL, 0 = NULL 許可
            if stock_col[3] == 0:
                logging.info("stock column already allows NULL")
                return

            logging.info("Starting migration to allow NULL in stock column...")

            # crawl_status カラムが存在するか確認
            has_crawl_status = any(col[1] == "crawl_status" for col in columns)

            if has_crawl_status:
                # crawl_status カラムがある場合
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS price_history_new(
                        id           INTEGER PRIMARY KEY AUTOINCREMENT,
                        item_id      INTEGER NOT NULL,
                        price        INTEGER,
                        stock        INTEGER,
                        time         TIMESTAMP DEFAULT(DATETIME('now','localtime')),
                        crawl_status INTEGER NOT NULL DEFAULT 1,
                        FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
                    )
                    """
                )

                # データを移行
                cur.execute(
                    """
                    INSERT INTO price_history_new (id, item_id, price, stock, time, crawl_status)
                    SELECT id, item_id, price, stock, time, crawl_status FROM price_history
                    """
                )
            else:
                # crawl_status カラムがない場合
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS price_history_new(
                        id      INTEGER PRIMARY KEY AUTOINCREMENT,
                        item_id INTEGER NOT NULL,
                        price   INTEGER,
                        stock   INTEGER,
                        time    TIMESTAMP DEFAULT(DATETIME('now','localtime')),
                        FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
                    )
                    """
                )

                # データを移行
                cur.execute(
                    """
                    INSERT INTO price_history_new (id, item_id, price, stock, time)
                    SELECT id, item_id, price, stock, time FROM price_history
                    """
                )

            # 旧テーブルを削除し、新テーブルをリネーム
            cur.execute("DROP TABLE price_history")
            cur.execute("ALTER TABLE price_history_new RENAME TO price_history")

            # インデックスを再作成
            cur.execute("CREATE INDEX IF NOT EXISTS idx_price_history_item_id ON price_history(item_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_price_history_time ON price_history(time)")

        logging.info("Migration to nullable stock completed successfully")

    def migrate_add_crawl_status(self) -> None:
        """crawl_status カラムを追加するマイグレーション."""
        with my_lib.sqlite_util.connect(self.db.db_path) as conn:
            cur = conn.cursor()

            # テーブルが存在するか確認
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='price_history'")
            if not cur.fetchone():
                logging.info("No price_history table found")
                return

            # 現在のスキーマを確認（crawl_status カラムが存在するか）
            cur.execute("PRAGMA table_info(price_history)")
            columns = [col[1] for col in cur.fetchall()]

            if "crawl_status" in columns:
                logging.info("crawl_status column already exists")
                return

            logging.info("Adding crawl_status column to price_history...")

            # カラムを追加（デフォルト値 1 = 成功）
            cur.execute("ALTER TABLE price_history ADD COLUMN crawl_status INTEGER NOT NULL DEFAULT 1")

        logging.info("Migration to add crawl_status completed successfully")

    def migrate_url_hash_to_item_key(self) -> None:
        """url_hash カラムを item_key にリネームし、新カラムを追加するマイグレーション.

        SQLite は ALTER COLUMN RENAME をサポートしていないため、
        テーブルを再作成してデータを移行する。
        """
        with my_lib.sqlite_util.connect(self.db.db_path) as conn:
            cur = conn.cursor()

            # テーブルが存在するか確認
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='items'")
            if not cur.fetchone():
                logging.info("No items table found")
                return

            # 現在のスキーマを確認（url_hash カラムが存在するか）
            cur.execute("PRAGMA table_info(items)")
            columns = [col[1] for col in cur.fetchall()]

            if "item_key" in columns:
                logging.info("item_key column already exists")
                return

            if "url_hash" not in columns:
                logging.info("url_hash column not found, skipping migration")
                return

            logging.info("Starting migration from url_hash to item_key...")

            # 新しいテーブルを作成
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS items_new(
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_key        TEXT NOT NULL UNIQUE,
                    url             TEXT,
                    name            TEXT NOT NULL,
                    store           TEXT NOT NULL,
                    thumb_url       TEXT,
                    search_keyword  TEXT,
                    search_cond     TEXT,
                    created_at      TIMESTAMP DEFAULT(DATETIME('now','localtime')),
                    updated_at      TIMESTAMP DEFAULT(DATETIME('now','localtime'))
                )
                """
            )

            # データを移行（url_hash を item_key にコピー）
            cur.execute(
                """
                INSERT INTO items_new (id, item_key, url, name, store, thumb_url, created_at, updated_at)
                SELECT id, url_hash, url, name, store, thumb_url, created_at, updated_at FROM items
                """
            )

            # 旧テーブルを削除し、新テーブルをリネーム
            cur.execute("DROP TABLE items")
            cur.execute("ALTER TABLE items_new RENAME TO items")

            # インデックスを再作成
            cur.execute("CREATE INDEX IF NOT EXISTS idx_items_item_key ON items(item_key)")

            # 旧インデックスを削除（存在する場合）
            cur.execute("DROP INDEX IF EXISTS idx_items_url_hash")

        logging.info("Migration from url_hash to item_key completed successfully")
