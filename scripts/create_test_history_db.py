#!/usr/bin/env python3
"""
テスト用の価格履歴データベースを作成するスクリプト。

E2E テストで使用するダミーデータを含むデータベースを作成します。

Usage:
  create_test_history_db.py -o OUTPUT [-D]

Options:
  -o OUTPUT         : 出力先のデータベースファイルパス。
  -D                : デバッグモードで動作します。
"""

from __future__ import annotations

import hashlib
import logging
import pathlib
import sqlite3
from datetime import datetime, timedelta, timezone

# 日本時間
JST = timezone(timedelta(hours=9))


def generate_item_key(url: str) -> str:
    """URL から item_key を生成."""
    return hashlib.sha256(url.encode()).hexdigest()[:12]


def create_tables(conn: sqlite3.Connection) -> None:
    """テーブルを作成."""
    cur = conn.cursor()

    # items テーブル
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS items(
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            item_key    TEXT NOT NULL UNIQUE,
            url         TEXT,
            name        TEXT NOT NULL,
            store       TEXT NOT NULL,
            thumb_url   TEXT,
            search_keyword TEXT,
            search_cond    TEXT,
            created_at  TIMESTAMP DEFAULT(DATETIME('now','localtime')),
            updated_at  TIMESTAMP DEFAULT(DATETIME('now','localtime'))
        )
        """
    )

    # price_history テーブル
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS price_history(
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id      INTEGER NOT NULL,
            price        INTEGER,
            stock        INTEGER,
            crawl_status INTEGER NOT NULL DEFAULT 1,
            time         TIMESTAMP DEFAULT(DATETIME('now','localtime')),
            FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
        )
        """
    )

    # events テーブル
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS events(
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id        INTEGER NOT NULL,
            event_type     TEXT NOT NULL,
            price          INTEGER,
            old_price      INTEGER,
            threshold_days INTEGER,
            created_at     TIMESTAMP DEFAULT(DATETIME('now','localtime')),
            notified       INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
        )
        """
    )

    # インデックス
    cur.execute("CREATE INDEX IF NOT EXISTS idx_items_item_key ON items(item_key)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_price_history_item_id ON price_history(item_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_price_history_time ON price_history(time)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_item_id ON events(item_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)")

    conn.commit()


def insert_item(
    conn: sqlite3.Connection,
    url: str,
    name: str,
    store: str,
    thumb_url: str | None = None,
) -> int:
    """アイテムを挿入."""
    cur = conn.cursor()
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    item_key = generate_item_key(url)

    cur.execute(
        """
        INSERT INTO items (item_key, url, name, store, thumb_url, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (item_key, url, name, store, thumb_url, now, now),
    )
    conn.commit()
    return cur.lastrowid or 0


def insert_price_history(
    conn: sqlite3.Connection,
    item_id: int,
    price: int | None,
    stock: int,
    time: datetime,
    crawl_status: int = 1,
) -> None:
    """価格履歴を挿入."""
    cur = conn.cursor()
    time_str = time.strftime("%Y-%m-%d %H:%M:%S")

    cur.execute(
        """
        INSERT INTO price_history (item_id, price, stock, crawl_status, time)
        VALUES (?, ?, ?, ?, ?)
        """,
        (item_id, price, stock, crawl_status, time_str),
    )
    conn.commit()


def generate_sample_data(conn: sqlite3.Connection) -> None:
    """サンプルデータを生成."""
    now = datetime.now(JST)

    # テスト商品のリスト（複数ストア対応）
    items = [
        # 商品A: 2つのストアで販売
        {
            "name": "テスト商品A",
            "stores": [
                {
                    "store": "ヨドバシ",
                    "url": "https://www.yodobashi.com/product/test-item-a/",
                    "prices": [
                        (10000, 1, -30),  # 30日前: 10,000円
                        (9800, 1, -25),  # 25日前: 9,800円
                        (9500, 1, -20),  # 20日前: 9,500円（最安値）
                        (9800, 1, -15),  # 15日前: 9,800円
                        (10200, 1, -10),  # 10日前: 10,200円
                        (9900, 1, -5),  # 5日前: 9,900円
                        (9700, 1, 0),  # 現在: 9,700円
                    ],
                },
                {
                    "store": "Amazon",
                    "url": "https://www.amazon.co.jp/dp/B0TEST0001",
                    "prices": [
                        (10500, 1, -30),
                        (10200, 1, -25),
                        (9800, 1, -20),
                        (9600, 1, -15),  # 最安値
                        (10000, 1, -10),
                        (9900, 1, -5),
                        (9800, 1, 0),
                    ],
                },
            ],
        },
        # 商品B: 1つのストアのみ
        {
            "name": "テスト商品B",
            "stores": [
                {
                    "store": "Yahoo ショッピング",
                    "url": "https://store.shopping.yahoo.co.jp/test-store/item-b.html",
                    "prices": [
                        (5000, 1, -28),
                        (4800, 1, -21),
                        (4500, 1, -14),
                        (4200, 1, -7),  # 最安値
                        (4500, 1, 0),
                    ],
                },
            ],
        },
        # 商品C: 在庫切れあり
        {
            "name": "テスト商品C（在庫変動あり）",
            "stores": [
                {
                    "store": "ヨドバシ",
                    "url": "https://www.yodobashi.com/product/test-item-c/",
                    "prices": [
                        (15000, 1, -20),  # 在庫あり
                        (14500, 1, -15),
                        (None, 0, -10),  # 在庫切れ
                        (None, 0, -5),  # 在庫切れ継続
                        (14000, 1, 0),  # 在庫復活
                    ],
                },
            ],
        },
    ]

    for item_group in items:
        item_name = item_group["name"]
        for store_info in item_group["stores"]:
            # アイテムを挿入
            item_id = insert_item(
                conn,
                url=store_info["url"],
                name=item_name,
                store=store_info["store"],
            )

            # 価格履歴を挿入
            for price, stock, days_ago in store_info["prices"]:
                time = now + timedelta(days=days_ago)
                insert_price_history(conn, item_id, price, stock, time)


if __name__ == "__main__":
    import docopt
    import my_lib.logger

    assert __doc__ is not None  # noqa: S101
    args = docopt.docopt(__doc__)

    output_path = pathlib.Path(args["-o"])
    debug_mode = args["-D"]

    my_lib.logger.init("create-test-db", level=logging.DEBUG if debug_mode else logging.INFO)

    # 出力ディレクトリが存在しない場合は作成
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 既存のファイルがあれば削除
    if output_path.exists():
        output_path.unlink()

    # データベースを作成
    with sqlite3.connect(output_path) as conn:
        logging.info("Creating database: %s", output_path)

        # テーブルを作成
        create_tables(conn)
        logging.info("Tables created.")

        # サンプルデータを挿入
        generate_sample_data(conn)
        logging.info("Sample data inserted.")

        # 確認用のクエリ
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM items")
        item_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM price_history")
        history_count = cur.fetchone()[0]

        logging.info("Database created successfully:")
        logging.info("  - Items: %d", item_count)
        logging.info("  - Price history records: %d", history_count)
