#!/usr/bin/env python3
"""履歴管理.

価格履歴データベースを管理します。
グローバル init() を不要にし、DI 対応の設計にします。
"""

from __future__ import annotations

import logging
import pathlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import price_watch.exceptions
import price_watch.history

if TYPE_CHECKING:
    from price_watch.models import CheckedItem


@dataclass
class HistoryManager:
    """履歴管理クラス.

    価格履歴データベースの初期化とアクセスを管理します。
    """

    data_path: pathlib.Path
    _initialized: bool = field(default=False, init=False)

    def initialize(self) -> None:
        """データベースを初期化.

        Raises:
            HistoryError: 初期化に失敗した場合
        """
        if self._initialized:
            return

        try:
            logging.info("Initializing history database at %s", self.data_path)
            price_watch.history.init(self.data_path)
            self._initialized = True
        except Exception as e:
            raise price_watch.exceptions.HistoryError(
                f"Failed to initialize history database: {self.data_path}"
            ) from e

    def _ensure_initialized(self) -> None:
        """初期化されていることを確認."""
        if not self._initialized:
            self.initialize()

    def insert(self, item: dict[str, Any], *, crawl_status: int = 1) -> int:
        """価格履歴を挿入.

        Args:
            item: アイテム情報
            crawl_status: クロール状態（0: 失敗, 1: 成功）

        Returns:
            アイテム ID
        """
        self._ensure_initialized()
        return price_watch.history.insert(item, crawl_status=crawl_status)

    def insert_checked_item(self, item: CheckedItem) -> int:
        """CheckedItem から価格履歴を挿入.

        Args:
            item: チェック済みアイテム

        Returns:
            アイテム ID
        """
        self._ensure_initialized()

        item_dict = {
            "name": item.name,
            "store": item.store,
            "url": item.url,
            "thumb_url": item.thumb_url,
            "search_keyword": item.search_keyword,
            "search_cond": item.search_cond,
            "price": item.price,
            "stock": item.stock.to_int(),
        }

        crawl_status = 1 if item.is_success() else 0
        return price_watch.history.insert(item_dict, crawl_status=crawl_status)

    def last(self, url: str | None = None, *, item_key: str | None = None) -> dict[str, Any] | None:
        """最新の価格履歴を取得.

        Args:
            url: URL
            item_key: アイテムキー

        Returns:
            最新の価格履歴、または None
        """
        self._ensure_initialized()
        return price_watch.history.last(url, item_key=item_key)

    def lowest(self, url: str | None = None, *, item_key: str | None = None) -> dict[str, Any] | None:
        """最安値の価格履歴を取得.

        Args:
            url: URL
            item_key: アイテムキー

        Returns:
            最安値の価格履歴、または None
        """
        self._ensure_initialized()
        return price_watch.history.lowest(url, item_key=item_key)

    def get_item_id(self, url: str | None = None, *, item_key: str | None = None) -> int | None:
        """アイテム ID を取得.

        Args:
            url: URL
            item_key: アイテムキー

        Returns:
            アイテム ID、または None
        """
        self._ensure_initialized()
        return price_watch.history.get_item_id(url, item_key=item_key)

    def get_item_by_id(self, item_id: int) -> dict[str, Any] | None:
        """アイテム ID からアイテム情報を取得.

        Args:
            item_id: アイテム ID

        Returns:
            アイテム情報、または None
        """
        self._ensure_initialized()
        return price_watch.history.get_item_by_id(item_id)

    def get_all_items(self) -> list[dict[str, Any]]:
        """全アイテムを取得.

        Returns:
            全アイテムのリスト
        """
        self._ensure_initialized()
        return price_watch.history.get_all_items()

    def get_item_history(
        self, item_key: str, days: int | None = None
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        """アイテムの価格履歴を取得.

        Args:
            item_key: アイテムキー
            days: 期間（日数）

        Returns:
            (アイテム情報, 価格履歴リスト) のタプル
        """
        self._ensure_initialized()
        return price_watch.history.get_item_history(item_key, days)

    def get_item_stats(self, item_id: int, days: int | None = None) -> dict[str, Any]:
        """アイテムの統計情報を取得.

        Args:
            item_id: アイテム ID
            days: 期間（日数）

        Returns:
            統計情報
        """
        self._ensure_initialized()
        return price_watch.history.get_item_stats(item_id, days)

    def get_latest_price(self, item_id: int) -> dict[str, Any] | None:
        """アイテムの最新価格を取得.

        Args:
            item_id: アイテム ID

        Returns:
            最新価格情報、または None
        """
        self._ensure_initialized()
        return price_watch.history.get_latest_price(item_id)

    def get_lowest_price_in_period(self, item_id: int, days: int | None = None) -> int | None:
        """指定期間内の最安値を取得.

        Args:
            item_id: アイテム ID
            days: 期間（日数）

        Returns:
            最安値、または None
        """
        self._ensure_initialized()
        return price_watch.history.get_lowest_price_in_period(item_id, days)

    def has_successful_crawl_in_hours(self, item_id: int, hours: int) -> bool:
        """指定時間内に成功したクロールがあるか確認.

        Args:
            item_id: アイテム ID
            hours: 確認する時間数

        Returns:
            成功したクロールがあれば True
        """
        self._ensure_initialized()
        return price_watch.history.has_successful_crawl_in_hours(item_id, hours)

    def get_out_of_stock_duration_hours(self, item_id: int) -> float | None:
        """在庫なし状態の継続時間を取得.

        Args:
            item_id: アイテム ID

        Returns:
            継続時間（時間）、または None
        """
        self._ensure_initialized()
        return price_watch.history.get_out_of_stock_duration_hours(item_id)

    def get_no_data_duration_hours(self, item_id: int) -> float | None:
        """データ取得失敗の継続時間を取得.

        Args:
            item_id: アイテム ID

        Returns:
            継続時間（時間）、または None
        """
        self._ensure_initialized()
        return price_watch.history.get_no_data_duration_hours(item_id)

    # --- イベント関連 ---

    def insert_event(
        self,
        item_id: int,
        event_type: str,
        *,
        price: int | None = None,
        old_price: int | None = None,
        threshold_days: int | None = None,
        notified: bool = False,
    ) -> int:
        """イベントを記録.

        Args:
            item_id: アイテム ID
            event_type: イベントタイプ
            price: 現在価格
            old_price: 以前の価格
            threshold_days: 判定に使用した期間
            notified: 通知済みフラグ

        Returns:
            イベント ID
        """
        self._ensure_initialized()
        return price_watch.history.insert_event(
            item_id=item_id,
            event_type=event_type,
            price=price,
            old_price=old_price,
            threshold_days=threshold_days,
            notified=notified,
        )

    def has_event_in_hours(self, item_id: int, event_type: str, hours: int) -> bool:
        """指定時間内に同じイベントが発生しているか確認.

        Args:
            item_id: アイテム ID
            event_type: イベントタイプ
            hours: 確認する時間数

        Returns:
            イベントがあれば True
        """
        self._ensure_initialized()
        return price_watch.history.has_event_in_hours(item_id, event_type, hours)

    def get_recent_events(self, limit: int = 10) -> list[dict[str, Any]]:
        """最新のイベントを取得.

        Args:
            limit: 取得件数

        Returns:
            イベントリスト
        """
        self._ensure_initialized()
        return price_watch.history.get_recent_events(limit)

    def get_item_events(self, item_key: str, limit: int = 50) -> list[dict[str, Any]]:
        """指定アイテムのイベント履歴を取得.

        Args:
            item_key: アイテムキー
            limit: 取得件数上限

        Returns:
            イベントリスト
        """
        self._ensure_initialized()
        return price_watch.history.get_item_events(item_key, limit)

    @staticmethod
    def generate_item_key(
        url: str | None = None,
        *,
        search_keyword: str | None = None,
        search_cond: str | None = None,
    ) -> str:
        """アイテムキーを生成.

        Args:
            url: URL（通常ストア用）
            search_keyword: 検索キーワード（メルカリ用）
            search_cond: 検索条件（未使用）

        Returns:
            12文字のハッシュ
        """
        return price_watch.history.generate_item_key(
            url, search_keyword=search_keyword, search_cond=search_cond
        )
