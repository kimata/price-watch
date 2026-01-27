#!/usr/bin/env python3
# ruff: noqa: S101
"""
managers/history/migrations.py のユニットテスト

データベースマイグレーションの各処理を検証します。
"""

from __future__ import annotations

import pathlib

import my_lib.sqlite_util

import price_watch.const
from price_watch.managers.history.connection import HistoryDBConnection
from price_watch.managers.history.migrations import HistoryMigrations


def _create_old_schema_db(db_path: pathlib.Path) -> None:
    """旧スキーマ（url カラムを含む price_history）のDBを作成."""
    with my_lib.sqlite_util.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE price_history(
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                url   TEXT NOT NULL,
                name  TEXT NOT NULL,
                store TEXT NOT NULL,
                price INTEGER NOT NULL,
                stock INTEGER NOT NULL,
                time  TIMESTAMP DEFAULT(DATETIME('now','localtime'))
            )
            """
        )
        # テストデータ挿入
        cur.execute(
            """
            INSERT INTO price_history (url, name, store, price, stock)
            VALUES ('https://example.com/item1', 'テスト商品1', 'test-store', 1000, 1)
            """
        )
        cur.execute(
            """
            INSERT INTO price_history (url, name, store, price, stock)
            VALUES ('https://example.com/item2', 'テスト商品2', 'test-store', 2000, 0)
            """
        )


def _create_v2_schema_db(db_path: pathlib.Path) -> None:
    """v2 スキーマ（url_hash カラム、price NOT NULL）のDBを作成."""
    with my_lib.sqlite_util.connect(db_path) as conn:
        cur = conn.cursor()
        # items テーブル（url_hash カラム）
        cur.execute(
            """
            CREATE TABLE items(
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
        # price_history テーブル（price NOT NULL、crawl_status なし）
        cur.execute(
            """
            CREATE TABLE price_history(
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                price   INTEGER NOT NULL,
                stock   INTEGER NOT NULL,
                time    TIMESTAMP DEFAULT(DATETIME('now','localtime')),
                FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
            )
            """
        )
        # テストデータ挿入
        cur.execute(
            """
            INSERT INTO items (url_hash, url, name, store)
            VALUES ('abc123def456', 'https://example.com/item1', 'テスト商品1', 'test-store')
            """
        )
        cur.execute(
            """
            INSERT INTO price_history (item_id, price, stock)
            VALUES (1, 1000, 1)
            """
        )


def _create_v3_schema_db(db_path: pathlib.Path) -> None:
    """v3 スキーマ（price NULL 許可、crawl_status あり、stock NOT NULL）のDBを作成."""
    with my_lib.sqlite_util.connect(db_path) as conn:
        cur = conn.cursor()
        # items テーブル（item_key カラム）
        cur.execute(
            """
            CREATE TABLE items(
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
        # price_history テーブル（price NULL 許可、crawl_status あり、stock NOT NULL）
        cur.execute(
            """
            CREATE TABLE price_history(
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id      INTEGER NOT NULL,
                price        INTEGER,
                stock        INTEGER NOT NULL,
                time         TIMESTAMP DEFAULT(DATETIME('now','localtime')),
                crawl_status INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
            )
            """
        )
        # テストデータ挿入
        cur.execute(
            """
            INSERT INTO items (item_key, url, name, store)
            VALUES ('abc123def456', 'https://example.com/item1', 'テスト商品1', 'test-store')
            """
        )
        cur.execute(
            """
            INSERT INTO price_history (item_id, price, stock, crawl_status)
            VALUES (1, 1000, 1, 1)
            """
        )


class TestMigrateFromOldSchema:
    """migrate_from_old_schema のテスト"""

    def test_no_old_table(self, temp_data_dir: pathlib.Path):
        """旧テーブルがない場合は何もしない"""
        db_path = temp_data_dir / price_watch.const.DB_FILE
        db = HistoryDBConnection(db_path=db_path)
        db.initialize()
        migrations = HistoryMigrations(db=db)

        # 旧テーブルがないので何もしない
        migrations.migrate_from_old_schema()

        # items テーブルが存在することを確認
        with my_lib.sqlite_util.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='items'")
            assert cur.fetchone() is not None

    def test_already_migrated(self, temp_data_dir: pathlib.Path):
        """既に移行済みの場合"""
        db_path = temp_data_dir / price_watch.const.DB_FILE
        # v2スキーマで作成（url カラムなし）
        _create_v2_schema_db(db_path)

        db = HistoryDBConnection(db_path=db_path)
        migrations = HistoryMigrations(db=db)

        migrations.migrate_from_old_schema()

        # url_hash カラムが残っていることを確認
        with my_lib.sqlite_util.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(items)")
            columns = [row[1] for row in cur.fetchall()]
            assert "url_hash" in columns

    def test_migrate_old_schema(self, temp_data_dir: pathlib.Path):
        """旧スキーマからの移行"""
        db_path = temp_data_dir / price_watch.const.DB_FILE
        _create_old_schema_db(db_path)

        db = HistoryDBConnection(db_path=db_path)
        migrations = HistoryMigrations(db=db)

        migrations.migrate_from_old_schema()

        # items テーブルが作成されていることを確認
        with my_lib.sqlite_util.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='items'")
            assert cur.fetchone() is not None

            # データが移行されていることを確認
            cur.execute("SELECT COUNT(*) as count FROM items")
            result = cur.fetchone()
            assert result[0] == 2

            # price_history テーブルにデータが移行されていることを確認
            cur.execute("SELECT COUNT(*) as count FROM price_history")
            result = cur.fetchone()
            assert result[0] == 2


class TestMigrateToNullablePrice:
    """migrate_to_nullable_price のテスト"""

    def test_no_table(self, temp_data_dir: pathlib.Path):
        """テーブルがない場合は何もしない"""
        db_path = temp_data_dir / price_watch.const.DB_FILE
        # 空のDBを作成
        with my_lib.sqlite_util.connect(db_path) as conn:
            conn.cursor()

        db = HistoryDBConnection(db_path=db_path)
        migrations = HistoryMigrations(db=db)

        migrations.migrate_to_nullable_price()

        # テーブルが存在しないことを確認
        with my_lib.sqlite_util.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='price_history'")
            assert cur.fetchone() is None

    def test_already_nullable(self, temp_data_dir: pathlib.Path):
        """既に NULL 許可の場合"""
        db_path = temp_data_dir / price_watch.const.DB_FILE
        db = HistoryDBConnection(db_path=db_path)
        db.initialize()  # 最新スキーマで作成（price は NULL 許可）
        migrations = HistoryMigrations(db=db)

        migrations.migrate_to_nullable_price()

        # スキーマが変更されていないことを確認
        with my_lib.sqlite_util.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(price_history)")
            columns = cur.fetchall()
            price_col = next(col for col in columns if col[1] == "price")
            assert price_col[3] == 0  # NOT NULL フラグが 0

    def test_migrate_to_nullable(self, temp_data_dir: pathlib.Path):
        """NOT NULL から NULL 許可への移行"""
        db_path = temp_data_dir / price_watch.const.DB_FILE
        _create_v2_schema_db(db_path)

        db = HistoryDBConnection(db_path=db_path)
        migrations = HistoryMigrations(db=db)

        migrations.migrate_to_nullable_price()

        # price カラムが NULL 許可になっていることを確認
        with my_lib.sqlite_util.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(price_history)")
            columns = cur.fetchall()
            price_col = next(col for col in columns if col[1] == "price")
            assert price_col[3] == 0  # NOT NULL フラグが 0


class TestMigrateToNullableStock:
    """migrate_to_nullable_stock のテスト"""

    def test_no_table(self, temp_data_dir: pathlib.Path):
        """テーブルがない場合は何もしない"""
        db_path = temp_data_dir / price_watch.const.DB_FILE
        with my_lib.sqlite_util.connect(db_path) as conn:
            conn.cursor()

        db = HistoryDBConnection(db_path=db_path)
        migrations = HistoryMigrations(db=db)

        migrations.migrate_to_nullable_stock()

    def test_already_nullable(self, temp_data_dir: pathlib.Path):
        """既に NULL 許可の場合"""
        db_path = temp_data_dir / price_watch.const.DB_FILE
        db = HistoryDBConnection(db_path=db_path)
        db.initialize()
        migrations = HistoryMigrations(db=db)

        migrations.migrate_to_nullable_stock()

        with my_lib.sqlite_util.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(price_history)")
            columns = cur.fetchall()
            stock_col = next(col for col in columns if col[1] == "stock")
            assert stock_col[3] == 0

    def test_migrate_with_crawl_status(self, temp_data_dir: pathlib.Path):
        """crawl_status がある場合の移行"""
        db_path = temp_data_dir / price_watch.const.DB_FILE
        _create_v3_schema_db(db_path)

        db = HistoryDBConnection(db_path=db_path)
        migrations = HistoryMigrations(db=db)

        migrations.migrate_to_nullable_stock()

        with my_lib.sqlite_util.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(price_history)")
            columns = cur.fetchall()
            stock_col = next(col for col in columns if col[1] == "stock")
            assert stock_col[3] == 0

            # crawl_status カラムが保持されていることを確認
            column_names = [col[1] for col in columns]
            assert "crawl_status" in column_names

    def test_migrate_without_crawl_status(self, temp_data_dir: pathlib.Path):
        """crawl_status がない場合の移行"""
        db_path = temp_data_dir / price_watch.const.DB_FILE
        _create_v2_schema_db(db_path)
        # まず price を NULL 許可に
        db = HistoryDBConnection(db_path=db_path)
        migrations = HistoryMigrations(db=db)
        migrations.migrate_to_nullable_price()

        migrations.migrate_to_nullable_stock()

        with my_lib.sqlite_util.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(price_history)")
            columns = cur.fetchall()
            stock_col = next(col for col in columns if col[1] == "stock")
            assert stock_col[3] == 0


class TestMigrateAddCrawlStatus:
    """migrate_add_crawl_status のテスト"""

    def test_no_table(self, temp_data_dir: pathlib.Path):
        """テーブルがない場合は何もしない"""
        db_path = temp_data_dir / price_watch.const.DB_FILE
        with my_lib.sqlite_util.connect(db_path) as conn:
            conn.cursor()

        db = HistoryDBConnection(db_path=db_path)
        migrations = HistoryMigrations(db=db)

        migrations.migrate_add_crawl_status()

    def test_already_has_column(self, temp_data_dir: pathlib.Path):
        """既に crawl_status カラムがある場合"""
        db_path = temp_data_dir / price_watch.const.DB_FILE
        db = HistoryDBConnection(db_path=db_path)
        db.initialize()
        migrations = HistoryMigrations(db=db)

        migrations.migrate_add_crawl_status()

        with my_lib.sqlite_util.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(price_history)")
            columns = [col[1] for col in cur.fetchall()]
            assert "crawl_status" in columns

    def test_add_crawl_status(self, temp_data_dir: pathlib.Path):
        """crawl_status カラムを追加"""
        db_path = temp_data_dir / price_watch.const.DB_FILE
        # crawl_status なしの v2 スキーマを作成
        _create_v2_schema_db(db_path)

        db = HistoryDBConnection(db_path=db_path)
        migrations = HistoryMigrations(db=db)

        migrations.migrate_add_crawl_status()

        with my_lib.sqlite_util.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(price_history)")
            columns = [col[1] for col in cur.fetchall()]
            assert "crawl_status" in columns

            # 既存データのデフォルト値を確認
            cur.execute("SELECT crawl_status FROM price_history WHERE id = 1")
            result = cur.fetchone()
            assert result[0] == 1  # デフォルト値は 1（成功）


class TestMigrateUrlHashToItemKey:
    """migrate_url_hash_to_item_key のテスト"""

    def test_no_table(self, temp_data_dir: pathlib.Path):
        """テーブルがない場合は何もしない"""
        db_path = temp_data_dir / price_watch.const.DB_FILE
        with my_lib.sqlite_util.connect(db_path) as conn:
            conn.cursor()

        db = HistoryDBConnection(db_path=db_path)
        migrations = HistoryMigrations(db=db)

        migrations.migrate_url_hash_to_item_key()

    def test_already_has_item_key(self, temp_data_dir: pathlib.Path):
        """既に item_key カラムがある場合"""
        db_path = temp_data_dir / price_watch.const.DB_FILE
        db = HistoryDBConnection(db_path=db_path)
        db.initialize()
        migrations = HistoryMigrations(db=db)

        migrations.migrate_url_hash_to_item_key()

        with my_lib.sqlite_util.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(items)")
            columns = [col[1] for col in cur.fetchall()]
            assert "item_key" in columns
            assert "url_hash" not in columns

    def test_rename_url_hash_to_item_key(self, temp_data_dir: pathlib.Path):
        """url_hash を item_key にリネーム"""
        db_path = temp_data_dir / price_watch.const.DB_FILE
        _create_v2_schema_db(db_path)

        db = HistoryDBConnection(db_path=db_path)
        migrations = HistoryMigrations(db=db)

        migrations.migrate_url_hash_to_item_key()

        with my_lib.sqlite_util.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(items)")
            columns = [col[1] for col in cur.fetchall()]
            assert "item_key" in columns
            assert "url_hash" not in columns

            # データが移行されていることを確認
            cur.execute("SELECT item_key FROM items WHERE id = 1")
            result = cur.fetchone()
            assert result[0] == "abc123def456"

            # 新カラムが追加されていることを確認
            assert "search_keyword" in columns
            assert "search_cond" in columns


class TestRunAll:
    """run_all のテスト"""

    def test_run_all_on_new_db(self, temp_data_dir: pathlib.Path):
        """新規DBで全マイグレーション実行"""
        db_path = temp_data_dir / price_watch.const.DB_FILE
        db = HistoryDBConnection(db_path=db_path)
        db.initialize()
        migrations = HistoryMigrations(db=db)

        migrations.run_all()

        # 最新スキーマになっていることを確認
        with my_lib.sqlite_util.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(items)")
            columns = [col[1] for col in cur.fetchall()]
            assert "item_key" in columns

            cur.execute("PRAGMA table_info(price_history)")
            columns = [col[1] for col in cur.fetchall()]
            assert "crawl_status" in columns

    def test_run_all_on_v2_db(self, temp_data_dir: pathlib.Path):
        """v2 スキーマから全マイグレーション実行"""
        db_path = temp_data_dir / price_watch.const.DB_FILE
        _create_v2_schema_db(db_path)

        db = HistoryDBConnection(db_path=db_path)
        migrations = HistoryMigrations(db=db)

        migrations.run_all()

        # 最新スキーマになっていることを確認
        with my_lib.sqlite_util.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(items)")
            columns = [col[1] for col in cur.fetchall()]
            assert "item_key" in columns

            cur.execute("PRAGMA table_info(price_history)")
            columns = cur.fetchall()
            column_names = [col[1] for col in columns]
            assert "crawl_status" in column_names

            # price と stock が NULL 許可になっていることを確認
            price_col = next(col for col in columns if col[1] == "price")
            stock_col = next(col for col in columns if col[1] == "stock")
            assert price_col[3] == 0
            assert stock_col[3] == 0
