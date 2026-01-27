#!/usr/bin/env python3
"""Price Watch データモデル.

型安全な dataclass を使用したデータモデルを定義します。
dict[str, Any] の代わりにこれらのクラスを使用することで、
型安全性とコードの可読性を向上させます。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from price_watch.target import ResolvedItem


class CrawlStatus(Enum):
    """クロールステータス."""

    SUCCESS = 1
    FAILURE = 0


class StockStatus(Enum):
    """在庫ステータス."""

    IN_STOCK = 1
    OUT_OF_STOCK = 0
    UNKNOWN = -1

    @classmethod
    def from_int(cls, value: int | None) -> StockStatus:
        """整数値から StockStatus に変換.

        Args:
            value: 在庫状態値（0: 在庫なし, 1: 在庫あり, None: 不明）

        Returns:
            対応する StockStatus
        """
        if value is None:
            return cls.UNKNOWN
        if value == 1:
            return cls.IN_STOCK
        return cls.OUT_OF_STOCK

    def to_int(self) -> int | None:
        """整数値に変換.

        Returns:
            1 (在庫あり), 0 (在庫なし), None (不明)
        """
        if self == StockStatus.IN_STOCK:
            return 1
        if self == StockStatus.OUT_OF_STOCK:
            return 0
        return None


@dataclass(frozen=True)
class PriceResult:
    """価格チェック結果.

    スクレイピングや PA-API から取得した価格情報を保持します。
    """

    price: int | None
    stock: StockStatus
    crawl_status: CrawlStatus
    thumb_url: str | None = None


@dataclass
class CheckedItem:
    """チェック済みアイテム.

    価格チェック後のアイテム情報を保持します。
    スクレイピング、PA-API、メルカリ検索で共通のデータ構造として使用します。
    """

    name: str
    store: str
    url: str | None
    price: int | None = None
    stock: StockStatus = StockStatus.UNKNOWN
    crawl_status: CrawlStatus = CrawlStatus.FAILURE
    thumb_url: str | None = None
    price_unit: str = "円"
    point_rate: float = 0.0
    color: str | None = None
    # メルカリ検索用
    search_keyword: str | None = None
    search_cond: str | None = None
    # ASIN（Amazon 用）
    asin: str | None = None
    # 過去の価格（イベント判定用）
    old_price: int | None = None

    def is_success(self) -> bool:
        """クロール成功かどうかを返す."""
        return self.crawl_status == CrawlStatus.SUCCESS

    @classmethod
    def from_resolved_item(cls, item: ResolvedItem) -> CheckedItem:
        """ResolvedItem から CheckedItem を生成.

        Args:
            item: 解決済みアイテム

        Returns:
            初期状態の CheckedItem
        """
        return cls(
            name=item.name,
            store=item.store,
            url=item.url if item.url else None,
            price_unit=item.price_unit,
            point_rate=item.point_rate,
            color=item.color,
            asin=item.asin,
            search_keyword=item.search_keyword,
        )

    def stock_as_int(self) -> int | None:
        """stock を整数値で取得（DB 保存用）."""
        return self.stock.to_int()

    def to_history_dict(self) -> dict[str, Any]:
        """history.insert 用の dict に変換.

        Returns:
            history.py が期待する形式の dict
        """
        result: dict[str, Any] = {
            "name": self.name,
            "store": self.store,
            "url": self.url,
        }
        if self.price is not None:
            result["price"] = self.price
        if self.stock != StockStatus.UNKNOWN:
            result["stock"] = self.stock.to_int()
        if self.thumb_url is not None:
            result["thumb_url"] = self.thumb_url
        if self.search_keyword is not None:
            result["search_keyword"] = self.search_keyword
        if self.search_cond is not None:
            result["search_cond"] = self.search_cond
        return result


@dataclass(frozen=True)
class PriceRecord:
    """価格履歴レコード（シンプル版）.

    価格・在庫・時刻のみの単純なレコード。
    get_history の履歴リストなどで使用します。
    """

    price: int | None
    stock: int | None
    time: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PriceRecord:
        """dict から PriceRecord を生成."""
        return cls(
            price=d.get("price"),
            stock=d.get("stock"),
            time=d.get("time", ""),
        )


@dataclass(frozen=True)
class PriceHistoryRecord:
    """価格履歴レコード（アイテム情報付き）.

    get_last, get_lowest などで使用する、アイテム情報を含む価格履歴。
    """

    url: str | None
    name: str
    store: str
    thumb_url: str | None
    price: int | None
    stock: int | None
    time: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PriceHistoryRecord:
        """dict から PriceHistoryRecord を生成."""
        return cls(
            url=d.get("url"),
            name=d.get("name", ""),
            store=d.get("store", ""),
            thumb_url=d.get("thumb_url"),
            price=d.get("price"),
            stock=d.get("stock"),
            time=d.get("time", ""),
        )


@dataclass(frozen=True)
class LatestPriceRecord:
    """最新価格レコード.

    get_latest, get_last_successful_crawl で使用します。
    """

    price: int | None
    stock: int | None
    crawl_status: int
    time: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> LatestPriceRecord:
        """dict から LatestPriceRecord を生成."""
        return cls(
            price=d.get("price"),
            stock=d.get("stock"),
            crawl_status=d.get("crawl_status", 0),
            time=d.get("time", ""),
        )


@dataclass(frozen=True)
class ItemRecord:
    """アイテムレコード.

    データベースのアイテム情報を表現します。
    """

    id: int
    item_key: str
    url: str | None
    name: str
    store: str
    thumb_url: str | None = None
    search_keyword: str | None = None
    search_cond: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ItemRecord:
        """dict から ItemRecord を生成."""
        return cls(
            id=d.get("id", 0),
            item_key=d.get("item_key", ""),
            url=d.get("url"),
            name=d.get("name", ""),
            store=d.get("store", ""),
            thumb_url=d.get("thumb_url"),
            search_keyword=d.get("search_keyword"),
            search_cond=d.get("search_cond"),
            created_at=d.get("created_at"),
            updated_at=d.get("updated_at"),
        )


@dataclass(frozen=True)
class ItemStats:
    """アイテム統計情報."""

    lowest_price: int | None
    highest_price: int | None
    data_count: int

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ItemStats:
        """dict から ItemStats を生成."""
        return cls(
            lowest_price=d.get("lowest_price"),
            highest_price=d.get("highest_price"),
            data_count=d.get("data_count", 0),
        )


@dataclass(frozen=True)
class EventRecord:
    """イベントレコード.

    データベースのイベント情報を表現します。
    """

    id: int
    item_id: int
    event_type: str
    price: int | None
    old_price: int | None
    threshold_days: int | None
    created_at: str
    notified: bool
    # アイテム情報（JOIN 結果）
    item_name: str | None = None
    store: str | None = None
    url: str | None = None
    thumb_url: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EventRecord:
        """dict から EventRecord を生成."""
        notified_raw = d.get("notified", 0)
        notified = bool(notified_raw) if isinstance(notified_raw, int) else notified_raw
        return cls(
            id=d.get("id", 0),
            item_id=d.get("item_id", 0),
            event_type=d.get("event_type", ""),
            price=d.get("price"),
            old_price=d.get("old_price"),
            threshold_days=d.get("threshold_days"),
            created_at=d.get("created_at", ""),
            notified=notified,
            item_name=d.get("item_name"),
            store=d.get("store"),
            url=d.get("url"),
            thumb_url=d.get("thumb_url"),
        )


@dataclass
class ProcessResult:
    """処理結果.

    アイテムリストの処理結果を集約します。
    """

    total_items: int = 0
    success_count: int = 0
    failed_count: int = 0

    def record_success(self) -> None:
        """成功を記録."""
        self.total_items += 1
        self.success_count += 1

    def record_failure(self) -> None:
        """失敗を記録."""
        self.total_items += 1
        self.failed_count += 1


@dataclass
class SessionStats:
    """セッション統計.

    巡回セッションの統計情報を保持します。
    """

    session_id: int | None = None
    total_items: int = 0
    success_items: int = 0
    failed_items: int = 0

    def record_success(self) -> None:
        """成功を記録."""
        self.total_items += 1
        self.success_items += 1

    def record_failure(self) -> None:
        """失敗を記録."""
        self.total_items += 1
        self.failed_items += 1


@dataclass
class StoreStats:
    """ストア別統計.

    ストアごとの巡回統計情報を保持します。
    """

    store_name: str
    stats_id: int | None = None
    item_count: int = 0
    success_count: int = 0
    failed_count: int = 0
