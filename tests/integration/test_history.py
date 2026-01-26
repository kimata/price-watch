#!/usr/bin/env python3
# ruff: noqa: S101
"""
HistoryManager integration テスト

SQLite データベース操作の統合テストを行います。
"""

from datetime import timedelta
from typing import TYPE_CHECKING

import my_lib.time
import time_machine

if TYPE_CHECKING:
    from price_watch.managers.history import HistoryManager

# 時間単位で異なる時刻を生成するためのベース時刻
_BASE_TIME = my_lib.time.now().replace(hour=10, minute=0, second=0, microsecond=0)


class TestHistoryInit:
    """HistoryManager 初期化のテスト"""

    def test_init_creates_database(self, history_manager: "HistoryManager") -> None:
        """初期化でデータベースが作成される"""
        db_path = history_manager.db.db_path
        assert db_path.exists()

    def test_init_creates_tables(self, history_manager: "HistoryManager") -> None:
        """初期化で必要なテーブルが作成される"""
        import my_lib.sqlite_util

        db_path = history_manager.db.db_path
        with my_lib.sqlite_util.connect(db_path) as conn:
            cur = conn.cursor()

            # items テーブルの存在確認
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='items'")
            assert cur.fetchone() is not None

            # price_history テーブルの存在確認
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='price_history'")
            assert cur.fetchone() is not None


class TestHistoryInsert:
    """HistoryManager.insert のテスト"""

    def test_insert_creates_item(self, history_manager: "HistoryManager", sample_item: dict) -> None:
        """insert でアイテムが作成される"""
        history_manager.insert(sample_item)

        items = history_manager.get_all_items()
        assert len(items) == 1
        assert items[0].name == sample_item["name"]
        assert items[0].store == sample_item["store"]

    def test_insert_creates_price_history(self, history_manager: "HistoryManager", sample_item: dict) -> None:
        """insert で価格履歴が作成される"""
        history_manager.insert(sample_item)

        items = history_manager.get_all_items()
        _, history = history_manager.get_history(items[0].item_key)

        assert len(history) == 1
        assert history[0].price == sample_item["price"]
        assert history[0].stock == sample_item["stock"]

    def test_insert_same_item_multiple_times(
        self, history_manager: "HistoryManager", sample_item: dict
    ) -> None:
        """同じアイテムを異なる時間帯で insert すると履歴が増える

        Note: insert は1時間単位で重複排除するため、異なる時間帯で挿入する必要がある
        """
        # 1回目: 10:00
        with time_machine.travel(_BASE_TIME, tick=False):
            history_manager.insert(sample_item)

        # 2回目: 11:00（1時間後）
        with time_machine.travel(_BASE_TIME + timedelta(hours=1), tick=False):
            modified_item = sample_item.copy()
            modified_item["price"] = 900
            history_manager.insert(modified_item)

        items = history_manager.get_all_items()
        assert len(items) == 1  # アイテムは1つ

        _, history = history_manager.get_history(items[0].item_key)
        assert len(history) == 2  # 履歴は2つ


class TestHistoryLast:
    """HistoryManager.get_last のテスト"""

    def test_last_returns_latest(self, history_manager: "HistoryManager", sample_item: dict) -> None:
        """get_last は最新の価格を返す"""
        # 1回目: 10:00
        with time_machine.travel(_BASE_TIME, tick=False):
            history_manager.insert(sample_item)

        # 2回目: 11:00（1時間後）- 価格が変わった
        with time_machine.travel(_BASE_TIME + timedelta(hours=1), tick=False):
            modified_item = sample_item.copy()
            modified_item["price"] = 800
            history_manager.insert(modified_item)

        result = history_manager.get_last(sample_item["url"])

        assert result is not None
        assert result.price == 800

    def test_last_returns_none_for_unknown(self, history_manager: "HistoryManager") -> None:
        """存在しない URL の場合は None を返す"""
        result = history_manager.get_last("https://unknown.com/item")

        assert result is None


class TestHistoryLowest:
    """HistoryManager.get_lowest のテスト"""

    def test_lowest_returns_min_price(self, history_manager: "HistoryManager", sample_item: dict) -> None:
        """get_lowest は最安値を返す"""
        # 1回目: 10:00 - 1000円
        with time_machine.travel(_BASE_TIME, tick=False):
            history_manager.insert(sample_item)

        # 2回目: 11:00 - 800円（最安値）
        with time_machine.travel(_BASE_TIME + timedelta(hours=1), tick=False):
            modified_item = sample_item.copy()
            modified_item["price"] = 800
            history_manager.insert(modified_item)

        # 3回目: 12:00 - 1200円
        with time_machine.travel(_BASE_TIME + timedelta(hours=2), tick=False):
            modified_item = sample_item.copy()
            modified_item["price"] = 1200
            history_manager.insert(modified_item)

        result = history_manager.get_lowest(sample_item["url"])

        assert result is not None
        assert result.price == 800


class TestHistoryStats:
    """HistoryManager.get_stats のテスト"""

    def test_get_item_stats(self, history_manager: "HistoryManager", sample_item: dict) -> None:
        """get_stats で統計情報を取得"""
        # 1回目: 10:00 - 1000円
        with time_machine.travel(_BASE_TIME, tick=False):
            history_manager.insert(sample_item)

        # 2回目: 11:00 - 800円
        with time_machine.travel(_BASE_TIME + timedelta(hours=1), tick=False):
            modified_item = sample_item.copy()
            modified_item["price"] = 800
            history_manager.insert(modified_item)

        # 3回目: 12:00 - 1200円
        with time_machine.travel(_BASE_TIME + timedelta(hours=2), tick=False):
            modified_item = sample_item.copy()
            modified_item["price"] = 1200
            history_manager.insert(modified_item)

        items = history_manager.get_all_items()
        stats = history_manager.get_stats(items[0].id)

        assert stats.lowest_price == 800
        assert stats.highest_price == 1200
        assert stats.data_count == 3


class TestHistoryLatestPrice:
    """HistoryManager.get_latest のテスト"""

    def test_get_latest_price(self, history_manager: "HistoryManager", sample_item: dict) -> None:
        """get_latest で最新価格を取得"""
        history_manager.insert(sample_item)

        items = history_manager.get_all_items()
        latest = history_manager.get_latest(items[0].id)

        assert latest is not None
        assert latest.price == sample_item["price"]
        assert latest.stock == sample_item["stock"]

    def test_get_latest_price_returns_none_for_unknown(self, history_manager: "HistoryManager") -> None:
        """存在しないアイテム ID の場合は None を返す"""
        latest = history_manager.get_latest(99999)

        assert latest is None


class TestMultipleItems:
    """複数アイテムのテスト"""

    def test_multiple_items_separate(
        self, history_manager: "HistoryManager", sample_items: list[dict]
    ) -> None:
        """複数の異なる URL のアイテムは別々に管理される"""
        for item in sample_items:
            history_manager.insert(item)

        items = history_manager.get_all_items()

        # URL が異なるので3つのアイテムができる
        assert len(items) == 3

    def test_same_name_different_store(
        self, history_manager: "HistoryManager", sample_items: list[dict]
    ) -> None:
        """同じ名前でも異なるストアは別アイテム"""
        for item in sample_items:
            history_manager.insert(item)

        items = history_manager.get_all_items()

        # 商品Aが2つのストアにある
        product_a_items = [i for i in items if i.name == "商品A"]
        assert len(product_a_items) == 2

        stores = {i.store for i in product_a_items}
        assert stores == {"store1.com", "store2.com"}
