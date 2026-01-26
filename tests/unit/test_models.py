#!/usr/bin/env python3
# ruff: noqa: S101
"""
models モジュールのユニットテスト

データモデルの動作を検証します。
"""

import json

import pytest

from price_watch.models import (
    CheckedItem,
    CrawlStatus,
    EventRecord,
    ItemRecord,
    ItemStats,
    MercariSearchCondition,
    MercariSearchResult,
    PriceRecord,
    PriceResult,
    ProcessResult,
    SessionStats,
    StockStatus,
    StoreStats,
)


# === CrawlStatus テスト ===
class TestCrawlStatus:
    """CrawlStatus 列挙型のテスト"""

    def test_success_value(self) -> None:
        """SUCCESS は 1"""
        assert CrawlStatus.SUCCESS.value == 1

    def test_failure_value(self) -> None:
        """FAILURE は 0"""
        assert CrawlStatus.FAILURE.value == 0


# === StockStatus テスト ===
class TestStockStatus:
    """StockStatus 列挙型のテスト"""

    def test_values(self) -> None:
        """列挙値の確認"""
        assert StockStatus.IN_STOCK.value == 1
        assert StockStatus.OUT_OF_STOCK.value == 0
        assert StockStatus.UNKNOWN.value == -1

    def test_from_int_in_stock(self) -> None:
        """from_int: 1 は IN_STOCK"""
        assert StockStatus.from_int(1) == StockStatus.IN_STOCK

    def test_from_int_out_of_stock(self) -> None:
        """from_int: 0 は OUT_OF_STOCK"""
        assert StockStatus.from_int(0) == StockStatus.OUT_OF_STOCK

    def test_from_int_none(self) -> None:
        """from_int: None は UNKNOWN"""
        assert StockStatus.from_int(None) == StockStatus.UNKNOWN

    def test_from_int_other_values(self) -> None:
        """from_int: その他の値は OUT_OF_STOCK"""
        assert StockStatus.from_int(2) == StockStatus.OUT_OF_STOCK
        assert StockStatus.from_int(-1) == StockStatus.OUT_OF_STOCK

    def test_to_int_in_stock(self) -> None:
        """to_int: IN_STOCK は 1"""
        assert StockStatus.IN_STOCK.to_int() == 1

    def test_to_int_out_of_stock(self) -> None:
        """to_int: OUT_OF_STOCK は 0"""
        assert StockStatus.OUT_OF_STOCK.to_int() == 0

    def test_to_int_unknown(self) -> None:
        """to_int: UNKNOWN は None"""
        assert StockStatus.UNKNOWN.to_int() is None


# === PriceResult テスト ===
class TestPriceResult:
    """PriceResult dataclass のテスト"""

    def test_create_success_result(self) -> None:
        """成功結果の作成"""
        result = PriceResult(
            price=1000,
            stock=StockStatus.IN_STOCK,
            crawl_status=CrawlStatus.SUCCESS,
            thumb_url="https://example.com/thumb.jpg",
        )
        assert result.price == 1000
        assert result.stock == StockStatus.IN_STOCK
        assert result.crawl_status == CrawlStatus.SUCCESS
        assert result.thumb_url == "https://example.com/thumb.jpg"

    def test_create_failure_result(self) -> None:
        """失敗結果の作成"""
        result = PriceResult(
            price=None,
            stock=StockStatus.UNKNOWN,
            crawl_status=CrawlStatus.FAILURE,
        )
        assert result.price is None
        assert result.stock == StockStatus.UNKNOWN
        assert result.crawl_status == CrawlStatus.FAILURE
        assert result.thumb_url is None

    def test_is_frozen(self) -> None:
        """frozen=True で変更不可"""
        result = PriceResult(
            price=1000,
            stock=StockStatus.IN_STOCK,
            crawl_status=CrawlStatus.SUCCESS,
        )
        with pytest.raises(AttributeError):
            result.price = 2000  # type: ignore[misc]


# === CheckedItem テスト ===
class TestCheckedItem:
    """CheckedItem dataclass のテスト"""

    def test_create_with_defaults(self) -> None:
        """デフォルト値での作成"""
        item = CheckedItem(name="テスト商品", store="test-store", url="https://example.com")
        assert item.name == "テスト商品"
        assert item.store == "test-store"
        assert item.url == "https://example.com"
        assert item.price is None
        assert item.stock == StockStatus.UNKNOWN
        assert item.crawl_status == CrawlStatus.FAILURE
        assert item.price_unit == "円"

    def test_is_success_true(self) -> None:
        """is_success: 成功時は True"""
        item = CheckedItem(
            name="テスト商品",
            store="test-store",
            url="https://example.com",
            crawl_status=CrawlStatus.SUCCESS,
        )
        assert item.is_success() is True

    def test_is_success_false(self) -> None:
        """is_success: 失敗時は False"""
        item = CheckedItem(
            name="テスト商品",
            store="test-store",
            url="https://example.com",
            crawl_status=CrawlStatus.FAILURE,
        )
        assert item.is_success() is False

    def test_mercari_fields(self) -> None:
        """メルカリ用フィールド"""
        item = CheckedItem(
            name="テスト商品",
            store="mercari",
            url="https://mercari.com/item/xxx",
            search_keyword="キーワード",
            search_cond='{"price_min": 100}',
        )
        assert item.search_keyword == "キーワード"
        assert item.search_cond == '{"price_min": 100}'


# === PriceRecord テスト ===
class TestPriceRecord:
    """PriceRecord dataclass のテスト"""

    def test_create(self) -> None:
        """作成"""
        record = PriceRecord(price=1000, stock=1, time="2024-01-15 10:00:00")
        assert record.price == 1000
        assert record.stock == 1
        assert record.time == "2024-01-15 10:00:00"

    def test_from_dict(self) -> None:
        """dict から作成"""
        d = {"price": 1000, "stock": 1, "time": "2024-01-15 10:00:00"}
        record = PriceRecord.from_dict(d)
        assert record.price == 1000
        assert record.stock == 1
        assert record.time == "2024-01-15 10:00:00"


# === ItemRecord テスト ===
class TestItemRecord:
    """ItemRecord dataclass のテスト"""

    def test_create(self) -> None:
        """作成"""
        record = ItemRecord(
            id=1,
            item_key="abc123",
            url="https://example.com",
            name="テスト商品",
            store="test-store",
        )
        assert record.id == 1
        assert record.item_key == "abc123"
        assert record.name == "テスト商品"


# === ItemStats テスト ===
class TestItemStats:
    """ItemStats dataclass のテスト"""

    def test_create(self) -> None:
        """作成"""
        stats = ItemStats(lowest_price=800, highest_price=1200, data_count=10)
        assert stats.lowest_price == 800
        assert stats.highest_price == 1200
        assert stats.data_count == 10


# === EventRecord テスト ===
class TestEventRecord:
    """EventRecord dataclass のテスト"""

    def test_create(self) -> None:
        """作成"""
        record = EventRecord(
            id=1,
            item_id=10,
            event_type="PRICE_DROP",
            price=800,
            old_price=1000,
            threshold_days=7,
            created_at="2024-01-15 10:00:00",
            notified=False,
        )
        assert record.id == 1
        assert record.event_type == "PRICE_DROP"
        assert record.price == 800
        assert record.old_price == 1000


# === ProcessResult テスト ===
class TestProcessResult:
    """ProcessResult dataclass のテスト"""

    def test_initial_state(self) -> None:
        """初期状態"""
        result = ProcessResult()
        assert result.total_items == 0
        assert result.success_count == 0
        assert result.failed_count == 0

    def test_record_success(self) -> None:
        """record_success で成功を記録"""
        result = ProcessResult()
        result.record_success()
        result.record_success()

        assert result.total_items == 2
        assert result.success_count == 2
        assert result.failed_count == 0

    def test_record_failure(self) -> None:
        """record_failure で失敗を記録"""
        result = ProcessResult()
        result.record_failure()

        assert result.total_items == 1
        assert result.success_count == 0
        assert result.failed_count == 1

    def test_mixed_results(self) -> None:
        """成功と失敗が混在"""
        result = ProcessResult()
        result.record_success()
        result.record_failure()
        result.record_success()

        assert result.total_items == 3
        assert result.success_count == 2
        assert result.failed_count == 1


# === SessionStats テスト ===
class TestSessionStats:
    """SessionStats dataclass のテスト"""

    def test_initial_state(self) -> None:
        """初期状態"""
        stats = SessionStats()
        assert stats.session_id is None
        assert stats.total_items == 0
        assert stats.success_items == 0
        assert stats.failed_items == 0

    def test_record_success(self) -> None:
        """record_success で成功を記録"""
        stats = SessionStats(session_id=1)
        stats.record_success()

        assert stats.session_id == 1
        assert stats.total_items == 1
        assert stats.success_items == 1

    def test_record_failure(self) -> None:
        """record_failure で失敗を記録"""
        stats = SessionStats(session_id=1)
        stats.record_failure()

        assert stats.total_items == 1
        assert stats.failed_items == 1


# === StoreStats テスト ===
class TestStoreStats:
    """StoreStats dataclass のテスト"""

    def test_create(self) -> None:
        """作成"""
        stats = StoreStats(store_name="amazon", stats_id=1, item_count=10, success_count=8, failed_count=2)
        assert stats.store_name == "amazon"
        assert stats.item_count == 10


# === MercariSearchResult テスト ===
class TestMercariSearchResult:
    """MercariSearchResult dataclass のテスト"""

    def test_create(self) -> None:
        """作成"""
        result = MercariSearchResult(
            name="商品名",
            price=1000,
            url="https://mercari.com/item/xxx",
            thumb_url="https://example.com/thumb.jpg",
            status="新品・未使用",
        )
        assert result.name == "商品名"
        assert result.price == 1000
        assert result.status == "新品・未使用"


# === MercariSearchCondition テスト ===
class TestMercariSearchCondition:
    """MercariSearchCondition dataclass のテスト"""

    def test_create_minimal(self) -> None:
        """最小構成での作成"""
        cond = MercariSearchCondition(keyword="テスト")
        assert cond.keyword == "テスト"
        assert cond.exclude_keyword is None
        assert cond.price_min is None
        assert cond.price_max is None
        assert cond.conditions == []

    def test_create_full(self) -> None:
        """全フィールド指定での作成"""
        cond = MercariSearchCondition(
            keyword="テスト",
            exclude_keyword="除外",
            price_min=100,
            price_max=10000,
            conditions=["NEW", "LIKE_NEW"],
        )
        assert cond.keyword == "テスト"
        assert cond.exclude_keyword == "除外"
        assert cond.price_min == 100
        assert cond.price_max == 10000
        assert cond.conditions == ["NEW", "LIKE_NEW"]

    def test_to_json(self) -> None:
        """to_json で JSON 文字列に変換"""
        cond = MercariSearchCondition(
            keyword="テスト",
            price_min=100,
            conditions=["NEW"],
        )
        json_str = cond.to_json()
        data = json.loads(json_str)

        assert data["keyword"] == "テスト"
        assert data["exclude_keyword"] is None
        assert data["price_min"] == 100
        assert data["price_max"] is None
        assert data["conditions"] == ["NEW"]

    def test_to_json_with_japanese(self) -> None:
        """to_json で日本語がエスケープされない"""
        cond = MercariSearchCondition(keyword="日本語キーワード")
        json_str = cond.to_json()

        # ensure_ascii=False で日本語がそのまま出力される
        assert "日本語キーワード" in json_str
