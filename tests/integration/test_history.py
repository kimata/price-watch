#!/usr/bin/env python3
# ruff: noqa: S101
"""
history モジュール integration テスト

SQLite データベース操作の統合テストを行います。
"""

import pathlib

import price_watch.history


class TestHistoryInit:
    """history.init のテスト"""

    def test_init_creates_database(self, temp_data_dir: pathlib.Path) -> None:
        """init でデータベースが作成される"""
        price_watch.history.init(temp_data_dir)

        db_path = temp_data_dir / "price_history.db"
        assert db_path.exists()

    def test_init_creates_tables(self, temp_data_dir: pathlib.Path) -> None:
        """init で必要なテーブルが作成される"""
        import my_lib.sqlite_util

        price_watch.history.init(temp_data_dir)

        db_path = temp_data_dir / "price_history.db"
        with my_lib.sqlite_util.connect(db_path) as conn:
            cur = conn.cursor()

            # items テーブルの存在確認
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='items'")
            assert cur.fetchone() is not None

            # price_history テーブルの存在確認
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='price_history'")
            assert cur.fetchone() is not None


class TestHistoryInsert:
    """history.insert のテスト"""

    def test_insert_creates_item(self, initialized_db: pathlib.Path, sample_item: dict) -> None:
        """insert でアイテムが作成される"""
        price_watch.history.insert(sample_item)

        items = price_watch.history.get_all_items()
        assert len(items) == 1
        assert items[0]["name"] == sample_item["name"]
        assert items[0]["store"] == sample_item["store"]

    def test_insert_creates_price_history(self, initialized_db: pathlib.Path, sample_item: dict) -> None:
        """insert で価格履歴が作成される"""
        price_watch.history.insert(sample_item)

        items = price_watch.history.get_all_items()
        _, history = price_watch.history.get_item_history(items[0]["url_hash"])

        assert len(history) == 1
        assert history[0]["price"] == sample_item["price"]
        assert history[0]["stock"] == sample_item["stock"]

    def test_insert_same_item_multiple_times(self, initialized_db: pathlib.Path, sample_item: dict) -> None:
        """同じアイテムを複数回 insert すると履歴が増える"""
        price_watch.history.insert(sample_item)

        modified_item = sample_item.copy()
        modified_item["price"] = 900
        price_watch.history.insert(modified_item)

        items = price_watch.history.get_all_items()
        assert len(items) == 1  # アイテムは1つ

        _, history = price_watch.history.get_item_history(items[0]["url_hash"])
        assert len(history) == 2  # 履歴は2つ


class TestHistoryLast:
    """history.last のテスト"""

    def test_last_returns_latest(self, initialized_db: pathlib.Path, sample_item: dict) -> None:
        """last は最新の価格を返す"""
        import time

        price_watch.history.insert(sample_item)

        # SQLite の DATETIME は秒単位の精度のため、1秒待つ
        time.sleep(1.1)

        modified_item = sample_item.copy()
        modified_item["price"] = 800
        price_watch.history.insert(modified_item)

        result = price_watch.history.last(sample_item["url"])

        assert result is not None
        assert result["price"] == 800

    def test_last_returns_none_for_unknown(self, initialized_db: pathlib.Path) -> None:
        """存在しない URL の場合は None を返す"""
        result = price_watch.history.last("https://unknown.com/item")

        assert result is None


class TestHistoryLowest:
    """history.lowest のテスト"""

    def test_lowest_returns_min_price(self, initialized_db: pathlib.Path, sample_item: dict) -> None:
        """lowest は最安値を返す"""
        price_watch.history.insert(sample_item)  # 1000円

        modified_item = sample_item.copy()
        modified_item["price"] = 800  # 最安値
        price_watch.history.insert(modified_item)

        modified_item["price"] = 1200
        price_watch.history.insert(modified_item)

        result = price_watch.history.lowest(sample_item["url"])

        assert result is not None
        assert result["price"] == 800


class TestHistoryStats:
    """history.get_item_stats のテスト"""

    def test_get_item_stats(self, initialized_db: pathlib.Path, sample_item: dict) -> None:
        """get_item_stats で統計情報を取得"""
        price_watch.history.insert(sample_item)  # 1000円

        modified_item = sample_item.copy()
        modified_item["price"] = 800
        price_watch.history.insert(modified_item)

        modified_item["price"] = 1200
        price_watch.history.insert(modified_item)

        items = price_watch.history.get_all_items()
        stats = price_watch.history.get_item_stats(items[0]["id"])

        assert stats["lowest_price"] == 800
        assert stats["highest_price"] == 1200
        assert stats["data_count"] == 3


class TestHistoryLatestPrice:
    """history.get_latest_price のテスト"""

    def test_get_latest_price(self, initialized_db: pathlib.Path, sample_item: dict) -> None:
        """get_latest_price で最新価格を取得"""
        price_watch.history.insert(sample_item)

        items = price_watch.history.get_all_items()
        latest = price_watch.history.get_latest_price(items[0]["id"])

        assert latest is not None
        assert latest["price"] == sample_item["price"]
        assert latest["stock"] == sample_item["stock"]

    def test_get_latest_price_returns_none_for_unknown(self, initialized_db: pathlib.Path) -> None:
        """存在しないアイテム ID の場合は None を返す"""
        latest = price_watch.history.get_latest_price(99999)

        assert latest is None


class TestMultipleItems:
    """複数アイテムのテスト"""

    def test_multiple_items_separate(self, initialized_db: pathlib.Path, sample_items: list[dict]) -> None:
        """複数の異なる URL のアイテムは別々に管理される"""
        for item in sample_items:
            price_watch.history.insert(item)

        items = price_watch.history.get_all_items()

        # URL が異なるので3つのアイテムができる
        assert len(items) == 3

    def test_same_name_different_store(self, initialized_db: pathlib.Path, sample_items: list[dict]) -> None:
        """同じ名前でも異なるストアは別アイテム"""
        for item in sample_items:
            price_watch.history.insert(item)

        items = price_watch.history.get_all_items()

        # 商品Aが2つのストアにある
        product_a_items = [i for i in items if i["name"] == "商品A"]
        assert len(product_a_items) == 2

        stores = {i["store"] for i in product_a_items}
        assert stores == {"store1.com", "store2.com"}
