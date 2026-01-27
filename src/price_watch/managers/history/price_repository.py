#!/usr/bin/env python3
"""価格履歴 Repository.

価格履歴の CRUD 操作を担当します。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

import my_lib.time

from price_watch.managers.history.utils import url_hash

if TYPE_CHECKING:
    from price_watch.managers.history.connection import HistoryDBConnection
    from price_watch.managers.history.item_repository import ItemRepository


@dataclass
class PriceRepository:
    """価格履歴 Repository.

    価格履歴の CRUD 操作を提供します。
    """

    db: HistoryDBConnection
    item_repo: ItemRepository

    def insert(self, item: dict[str, Any], *, crawl_status: int = 1) -> int:
        """価格履歴を挿入または更新.

        1時間に1回の記録を保持する。同一時間帯で複数回取得した場合:
        - より安い価格で更新（価格がある場合のみ）
        - 収集時刻は常に最新に更新

        Args:
            item: アイテム情報
            crawl_status: クロール状態（0: 失敗, 1: 成功）

        Returns:
            アイテム ID
        """
        with self.db.connect() as conn:
            cur = conn.cursor()

            item_id = self.item_repo.get_or_create(
                cur,
                item["name"],
                item["store"],
                url=item.get("url"),
                thumb_url=item.get("thumb_url"),
                search_keyword=item.get("search_keyword"),
                search_cond=item.get("search_cond"),
            )

            now = my_lib.time.now()
            now_str = now.strftime("%Y-%m-%d %H:%M:%S")
            hour_start = now.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")

            # crawl_status=0 の場合は stock=NULL, price=NULL
            if crawl_status == 0:
                new_stock: int | None = None
                new_price: int | None = None
            else:
                new_stock = item.get("stock", 0)
                new_price = item.get("price")

            # 同一時間帯の既存レコードを確認
            cur.execute(
                """
                SELECT id, price, stock, crawl_status
                FROM price_history
                WHERE item_id = ?
                  AND time >= ?
                ORDER BY time DESC
                LIMIT 1
                """,
                (item_id, hour_start),
            )
            existing = cur.fetchone()

            if existing:
                existing_id = existing["id"]
                existing_price = existing["price"]
                existing_stock = existing["stock"]
                existing_crawl_status = existing["crawl_status"]

                should_update = False
                final_price = new_price
                final_stock = new_stock

                if crawl_status == 1:
                    if existing_crawl_status == 0:
                        should_update = True
                    elif new_price is not None and existing_price is not None:
                        if new_stock == 1:
                            final_price = min(new_price, existing_price)
                            should_update = new_price < existing_price
                        else:
                            should_update = True
                    elif (new_price is not None and existing_price is None) or new_stock != existing_stock:
                        should_update = True
                else:
                    if existing_crawl_status == 1:
                        final_price = existing_price
                        final_stock = existing_stock
                        should_update = True

                if should_update:
                    cur.execute(
                        """
                        UPDATE price_history
                        SET price = ?, stock = ?, crawl_status = ?, time = ?
                        WHERE id = ?
                        """,
                        (final_price, final_stock, crawl_status, now_str, existing_id),
                    )
                else:
                    cur.execute(
                        "UPDATE price_history SET time = ? WHERE id = ?",
                        (now_str, existing_id),
                    )
            else:
                cur.execute(
                    """
                    INSERT INTO price_history (item_id, price, stock, crawl_status, time)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (item_id, new_price, new_stock, crawl_status, now_str),
                )

            conn.commit()
            return item_id

    def upsert_item(self, item: dict[str, Any]) -> int:
        """アイテム情報のみを upsert（価格履歴は挿入しない）.

        Args:
            item: アイテム情報

        Returns:
            アイテム ID
        """
        with self.db.connect() as conn:
            cur = conn.cursor()
            item_id = self.item_repo.get_or_create(
                cur,
                item["name"],
                item["store"],
                url=item.get("url"),
                thumb_url=item.get("thumb_url"),
                search_keyword=item.get("search_keyword"),
                search_cond=item.get("search_cond"),
            )
            conn.commit()
            return item_id

    def insert_price_history(
        self,
        item_id: int,
        price: int | None,
        stock: int | None,
        crawl_status: int,
    ) -> None:
        """価格履歴のみを挿入/更新.

        1時間に1回の記録を保持する。同一時間帯で複数回取得した場合:
        - より安い価格で更新（価格がある場合のみ）
        - 収集時刻は常に最新に更新

        Args:
            item_id: アイテム ID
            price: 価格
            stock: 在庫状態（0: なし, 1: あり, None: 不明）
            crawl_status: クロール状態（0: 失敗, 1: 成功）
        """
        with self.db.connect() as conn:
            cur = conn.cursor()

            now = my_lib.time.now()
            now_str = now.strftime("%Y-%m-%d %H:%M:%S")
            hour_start = now.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")

            # crawl_status=0 の場合は stock=NULL, price=NULL
            if crawl_status == 0:
                new_stock: int | None = None
                new_price: int | None = None
            else:
                new_stock = stock
                new_price = price

            # 同一時間帯の既存レコードを確認
            cur.execute(
                """
                SELECT id, price, stock, crawl_status
                FROM price_history
                WHERE item_id = ?
                  AND time >= ?
                ORDER BY time DESC
                LIMIT 1
                """,
                (item_id, hour_start),
            )
            existing = cur.fetchone()

            if existing:
                existing_id = existing["id"]
                existing_price = existing["price"]
                existing_stock = existing["stock"]
                existing_crawl_status = existing["crawl_status"]

                should_update = False
                final_price = new_price
                final_stock = new_stock

                if crawl_status == 1:
                    if existing_crawl_status == 0:
                        should_update = True
                    elif new_price is not None and existing_price is not None:
                        if new_stock == 1:
                            final_price = min(new_price, existing_price)
                            should_update = new_price < existing_price
                        else:
                            should_update = True
                    elif (new_price is not None and existing_price is None) or new_stock != existing_stock:
                        should_update = True
                else:
                    if existing_crawl_status == 1:
                        final_price = existing_price
                        final_stock = existing_stock
                        should_update = True

                if should_update:
                    cur.execute(
                        """
                        UPDATE price_history
                        SET price = ?, stock = ?, crawl_status = ?, time = ?
                        WHERE id = ?
                        """,
                        (final_price, final_stock, crawl_status, now_str, existing_id),
                    )
                else:
                    cur.execute(
                        "UPDATE price_history SET time = ? WHERE id = ?",
                        (now_str, existing_id),
                    )
            else:
                cur.execute(
                    """
                    INSERT INTO price_history (item_id, price, stock, crawl_status, time)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (item_id, new_price, new_stock, crawl_status, now_str),
                )

            conn.commit()

    def get_last(self, url: str | None = None, *, item_key: str | None = None) -> dict[str, Any] | None:
        """最新の価格履歴を取得.

        Args:
            url: URL（後方互換性のため残す）
            item_key: アイテムキー（優先）

        Returns:
            最新の価格履歴、または None
        """
        key = item_key if item_key is not None else url_hash(url) if url else None
        if key is None:
            return None

        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT i.url, i.name, i.store, i.thumb_url, ph.price, ph.stock, ph.time
                FROM items i
                JOIN price_history ph ON i.id = ph.item_id
                WHERE i.item_key = ?
                ORDER BY ph.time DESC
                LIMIT 1
                """,
                (key,),
            )
            return cur.fetchone()

    def get_lowest(self, url: str | None = None, *, item_key: str | None = None) -> dict[str, Any] | None:
        """最安値の価格履歴を取得.

        Args:
            url: URL（後方互換性のため残す）
            item_key: アイテムキー（優先）

        Returns:
            最安値の価格履歴、または None
        """
        key = item_key if item_key is not None else url_hash(url) if url else None
        if key is None:
            return None

        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT i.url, i.name, i.store, i.thumb_url, ph.price, ph.stock, ph.time
                FROM items i
                JOIN price_history ph ON i.id = ph.item_id
                WHERE i.item_key = ? AND ph.price IS NOT NULL
                ORDER BY ph.price ASC
                LIMIT 1
                """,
                (key,),
            )
            return cur.fetchone()

    def get_history(
        self, item_key: str, days: int | None = None
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        """アイテムの価格履歴を取得.

        Args:
            item_key: アイテムキー
            days: 期間（日数）

        Returns:
            (アイテム情報, 価格履歴リスト) のタプル
        """
        with self.db.connect() as conn:
            cur = conn.cursor()

            cur.execute(
                """
                SELECT id, item_key, url, name, store, thumb_url,
                       search_keyword, search_cond, created_at, updated_at
                FROM items
                WHERE item_key = ?
                """,
                (item_key,),
            )
            item = cur.fetchone()

            if not item:
                return None, []

            if days and days > 0:
                cur.execute(
                    """
                    SELECT price, stock, time
                    FROM price_history
                    WHERE item_id = ?
                      AND time >= datetime('now', 'localtime', ?)
                    ORDER BY time ASC
                    """,
                    (item["id"], f"-{days} days"),
                )
            else:
                cur.execute(
                    """
                    SELECT price, stock, time
                    FROM price_history
                    WHERE item_id = ?
                    ORDER BY time ASC
                    """,
                    (item["id"],),
                )

            return item, cur.fetchall()

    def get_stats(self, item_id: int, days: int | None = None) -> dict[str, Any]:
        """アイテムの統計情報を取得.

        Args:
            item_id: アイテム ID
            days: 期間（日数）

        Returns:
            統計情報
        """
        with self.db.connect() as conn:
            cur = conn.cursor()

            if days and days > 0:
                cur.execute(
                    """
                    SELECT
                        MIN(price) as lowest_price,
                        MAX(price) as highest_price,
                        COUNT(*) as data_count
                    FROM price_history
                    WHERE item_id = ?
                      AND time >= datetime('now', 'localtime', ?)
                      AND price IS NOT NULL
                    """,
                    (item_id, f"-{days} days"),
                )
            else:
                cur.execute(
                    """
                    SELECT
                        MIN(price) as lowest_price,
                        MAX(price) as highest_price,
                        COUNT(*) as data_count
                    FROM price_history
                    WHERE item_id = ?
                      AND price IS NOT NULL
                    """,
                    (item_id,),
                )

            stats = cur.fetchone()
            return stats or {"lowest_price": None, "highest_price": None, "data_count": 0}

    def get_latest(self, item_id: int) -> dict[str, Any] | None:
        """アイテムの最新価格を取得.

        Args:
            item_id: アイテム ID

        Returns:
            最新価格情報、または None
        """
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT price, stock, time
                FROM price_history
                WHERE item_id = ?
                ORDER BY time DESC
                LIMIT 1
                """,
                (item_id,),
            )
            return cur.fetchone()

    def get_lowest_in_period(self, item_id: int, days: int | None = None) -> int | None:
        """指定期間内の最安値を取得.

        Args:
            item_id: アイテム ID
            days: 期間（日数）。None の場合は全期間。

        Returns:
            最安値。レコードがない場合は None。
        """
        with self.db.connect() as conn:
            cur = conn.cursor()

            if days and days > 0:
                cur.execute(
                    """
                    SELECT MIN(price)
                    FROM price_history
                    WHERE item_id = ?
                      AND time >= datetime('now', 'localtime', ?)
                      AND price IS NOT NULL
                      AND crawl_status = 1
                    """,
                    (item_id, f"-{days} days"),
                )
            else:
                cur.execute(
                    """
                    SELECT MIN(price)
                    FROM price_history
                    WHERE item_id = ?
                      AND price IS NOT NULL
                      AND crawl_status = 1
                    """,
                    (item_id,),
                )

            row = cur.fetchone()
            # dict_factory を使用しているので、row は dict
            if row:
                # MIN(price) の結果は最初のカラム
                values = list(row.values())
                return values[0] if values and values[0] is not None else None
            return None

    def has_successful_crawl_in_hours(self, item_id: int, hours: int) -> bool:
        """指定時間内に成功したクロールがあるか確認.

        Args:
            item_id: アイテム ID
            hours: 確認する時間数

        Returns:
            成功したクロールがあれば True
        """
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT COUNT(*)
                FROM price_history
                WHERE item_id = ?
                  AND time >= datetime('now', 'localtime', ?)
                  AND crawl_status = 1
                """,
                (item_id, f"-{hours} hours"),
            )
            row = cur.fetchone()
            if row:
                values = list(row.values())
                return values[0] > 0 if values else False
            return False

    def get_out_of_stock_duration_hours(self, item_id: int) -> float | None:
        """在庫なし状態の継続時間（時間）を取得.

        Args:
            item_id: アイテム ID

        Returns:
            在庫なしの継続時間（時間）。在庫なし状態でない場合は None。
        """
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT stock, time
                FROM price_history
                WHERE item_id = ?
                  AND crawl_status = 1
                ORDER BY time DESC
                """,
                (item_id,),
            )
            rows = cur.fetchall()

            if not rows:
                return None

            oldest_out_of_stock_time = None

            for row in rows:
                stock = row["stock"]
                time_str = row["time"]
                if stock == 1:
                    break
                elif stock == 0:
                    oldest_out_of_stock_time = time_str

            if oldest_out_of_stock_time is None:
                return None

            now = my_lib.time.now()
            oldest_time = datetime.fromisoformat(oldest_out_of_stock_time)
            if now.tzinfo and oldest_time.tzinfo is None:
                oldest_time = oldest_time.replace(tzinfo=now.tzinfo)

            duration_seconds = (now - oldest_time).total_seconds()
            return duration_seconds / 3600

    def get_last_successful_crawl(self, item_id: int) -> dict[str, Any] | None:
        """最後に成功したクロールを取得.

        Args:
            item_id: アイテム ID

        Returns:
            最後に成功したクロール情報、または None
        """
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT price, stock, crawl_status, time
                FROM price_history
                WHERE item_id = ?
                  AND crawl_status = 1
                ORDER BY time DESC
                LIMIT 1
                """,
                (item_id,),
            )
            return cur.fetchone()

    def get_no_data_duration_hours(self, item_id: int) -> float | None:
        """データ取得失敗の継続時間（時間）を取得.

        Args:
            item_id: アイテム ID

        Returns:
            データ取得失敗の継続時間（時間）。データ取得失敗中でない場合は None。
        """
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT crawl_status, stock, time
                FROM price_history
                WHERE item_id = ?
                ORDER BY time DESC
                """,
                (item_id,),
            )
            rows = cur.fetchall()

            if not rows:
                return None

            oldest_no_data_time = None

            for row in rows:
                crawl_status = row["crawl_status"]
                stock = row["stock"]
                time_str = row["time"]

                if crawl_status == 1 and stock is not None:
                    break
                oldest_no_data_time = time_str

            if oldest_no_data_time is None:
                return None

            now = my_lib.time.now()
            oldest_time = datetime.fromisoformat(oldest_no_data_time)
            if now.tzinfo and oldest_time.tzinfo is None:
                oldest_time = oldest_time.replace(tzinfo=now.tzinfo)

            duration_seconds = (now - oldest_time).total_seconds()
            return duration_seconds / 3600
