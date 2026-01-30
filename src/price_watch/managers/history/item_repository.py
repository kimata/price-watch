#!/usr/bin/env python3
"""アイテム Repository.

アイテムの CRUD 操作を担当します。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import TYPE_CHECKING

import my_lib.time

import price_watch.models
from price_watch.managers.history.utils import generate_item_key, url_hash

if TYPE_CHECKING:
    from typing import Any

    from price_watch.managers.history.connection import HistoryDBConnection


@dataclass
class ItemRepository:
    """アイテム Repository.

    アイテムの CRUD 操作を提供します。
    """

    db: HistoryDBConnection

    def get_or_create(
        self,
        cur: sqlite3.Cursor,
        name: str,
        store: str,
        *,
        url: str | None = None,
        thumb_url: str | None = None,
        search_keyword: str | None = None,
        search_cond: str | None = None,
        price_unit: str | None = None,
    ) -> int:
        """アイテムを取得または作成し、ID を返す.

        Args:
            cur: SQLite カーソル
            name: アイテム名
            store: ストア名
            url: URL（通常ストア用、メルカリは動的に更新される）
            thumb_url: サムネイル URL
            search_keyword: 検索キーワード（メルカリ用）
            search_cond: 検索条件 JSON（メルカリ用）
            price_unit: 通貨単位

        Returns:
            アイテム ID
        """
        item_key = generate_item_key(
            url, search_keyword=search_keyword, search_cond=search_cond, store_name=store
        )

        cur.execute("SELECT id, name, thumb_url, url, price_unit FROM items WHERE item_key = ?", (item_key,))
        row = cur.fetchone()

        if row:
            item_id = row["id"]
            # 名前やサムネイル、URL、price_unit が更新されていたら更新
            updates = []
            params: list[Any] = []
            if row["name"] != name:
                updates.append("name = ?")
                params.append(name)
            if thumb_url and row["thumb_url"] != thumb_url:
                updates.append("thumb_url = ?")
                params.append(thumb_url)
            # メルカリの場合は URL を更新（最安商品の URL）
            if url and row["url"] != url:
                updates.append("url = ?")
                params.append(url)
            # price_unit が指定されていて、異なる場合は更新
            if price_unit and row.get("price_unit") != price_unit:
                updates.append("price_unit = ?")
                params.append(price_unit)
            if updates:
                updates.append("updated_at = ?")
                params.append(my_lib.time.now().strftime("%Y-%m-%d %H:%M:%S"))
                params.append(item_id)
                cur.execute(
                    f"UPDATE items SET {', '.join(updates)} WHERE id = ?",  # noqa: S608
                    params,
                )
            return item_id

        # 新規作成
        now = my_lib.time.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            """
            INSERT INTO items (
                item_key, url, name, store, thumb_url,
                search_keyword, search_cond, price_unit, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_key,
                url,
                name,
                store,
                thumb_url,
                search_keyword,
                search_cond,
                price_unit or "円",
                now,
                now,
            ),
        )
        return cur.lastrowid or 0

    def get_by_id(self, item_id: int) -> price_watch.models.ItemRecord | None:
        """アイテム ID からアイテム情報を取得.

        Args:
            item_id: アイテム ID

        Returns:
            アイテム情報、または None
        """
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, item_key, url, name, store, thumb_url,
                       search_keyword, search_cond, price_unit, created_at, updated_at
                FROM items
                WHERE id = ?
                """,
                (item_id,),
            )
            row = cur.fetchone()
            return price_watch.models.ItemRecord.from_dict(row) if row else None

    def get_id(self, url: str | None = None, *, item_key: str | None = None) -> int | None:
        """アイテム ID を取得.

        Args:
            url: URL（後方互換性のため残す）
            item_key: アイテムキー（優先）

        Returns:
            アイテム ID、または None
        """
        with self.db.connect() as conn:
            cur = conn.cursor()
            key = item_key if item_key is not None else url_hash(url) if url else None
            if key is None:
                return None
            cur.execute("SELECT id FROM items WHERE item_key = ?", (key,))
            row = cur.fetchone()
            return row["id"] if row else None

    def get_all(self) -> list[price_watch.models.ItemRecord]:
        """全アイテムを取得.

        Returns:
            アイテムリスト
        """
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, item_key, url, name, store, thumb_url,
                       search_keyword, search_cond, price_unit, created_at, updated_at
                FROM items
                ORDER BY updated_at DESC
                """
            )
            return [price_watch.models.ItemRecord.from_dict(row) for row in cur.fetchall()]

    def get_by_name(self, name: str) -> list[price_watch.models.ItemRecord]:
        """同じ商品名のアイテムを全ストアから取得.

        Args:
            name: 商品名

        Returns:
            同じ商品名を持つアイテムのリスト
        """
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, item_key, url, name, store, thumb_url,
                       search_keyword, search_cond, price_unit, created_at, updated_at
                FROM items
                WHERE name = ?
                ORDER BY store
                """,
                (name,),
            )
            return [price_watch.models.ItemRecord.from_dict(row) for row in cur.fetchall()]
