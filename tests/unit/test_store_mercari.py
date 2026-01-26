#!/usr/bin/env python3
# ruff: noqa: S101
"""
store/mercari.py のユニットテスト

メルカリ検索による価格チェックを検証します。
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import price_watch.models
import price_watch.store.mercari
from price_watch.target import CheckMethod, ResolvedItem


def _create_resolved_item(
    name: str = "テスト商品",
    store: str = "mercari",
    search_keyword: str | None = None,
    exclude_keyword: str | None = None,
    price_range: list[int] | None = None,
    cond: str | None = None,
) -> ResolvedItem:
    """テスト用の ResolvedItem を作成."""
    return ResolvedItem(
        name=name,
        store=store,
        url="",  # メルカリは URL なしで OK
        check_method=CheckMethod.MERCARI_SEARCH,
        search_keyword=search_keyword,
        exclude_keyword=exclude_keyword,
        price_range=price_range,
        cond=cond,
    )


def _create_checked_item(
    name: str = "テスト商品",
    store: str = "mercari",
    search_keyword: str | None = None,
    search_cond: str | None = None,
) -> price_watch.models.CheckedItem:
    """テスト用の CheckedItem を作成."""
    item = price_watch.models.CheckedItem(
        name=name,
        store=store,
        url=None,
        search_keyword=search_keyword,
        search_cond=search_cond,
    )
    return item


@dataclass
class MockSearchResult:
    """モック用の検索結果"""

    title: str
    price: int
    url: str


class TestParseCond:
    """_parse_cond 関数のテスト"""

    def test_none_returns_none(self):
        """None は None を返す"""
        result = price_watch.store.mercari._parse_cond(None)
        assert result is None

    def test_empty_string_returns_none(self):
        """空文字列は None を返す"""
        result = price_watch.store.mercari._parse_cond("")
        assert result is None

    def test_single_condition(self):
        """単一の状態"""
        result = price_watch.store.mercari._parse_cond("NEW")

        assert result is not None
        assert len(result) == 1
        assert result[0].name == "NEW"

    def test_multiple_conditions(self):
        """複数の状態"""
        result = price_watch.store.mercari._parse_cond("NEW|LIKE_NEW|GOOD")

        assert result is not None
        assert len(result) == 3

    def test_case_insensitive(self):
        """大文字小文字を区別しない"""
        result = price_watch.store.mercari._parse_cond("new|LIKE_NEW|Good")

        assert result is not None
        assert len(result) == 3

    def test_unknown_condition_warning(self):
        """不明な状態は警告"""
        with patch("logging.warning") as mock_warn:
            result = price_watch.store.mercari._parse_cond("NEW|UNKNOWN")

            mock_warn.assert_called_once()
            assert result is not None
            assert len(result) == 1

    def test_all_unknown_returns_none(self):
        """全て不明な場合は None"""
        with patch("logging.warning"):
            result = price_watch.store.mercari._parse_cond("UNKNOWN|INVALID")

        assert result is None


class TestBuildSearchCondition:
    """_build_search_condition 関数のテスト"""

    def test_basic(self):
        """基本的な検索条件"""
        item = _create_resolved_item(name="テスト商品")

        result = price_watch.store.mercari._build_search_condition(item)

        assert result.keyword == "テスト商品"
        assert result.exclude_keyword is None
        assert result.price_min is None
        assert result.price_max is None

    def test_with_search_keyword(self):
        """検索キーワード指定"""
        item = _create_resolved_item(name="テスト商品", search_keyword="カスタムキーワード")

        result = price_watch.store.mercari._build_search_condition(item)

        assert result.keyword == "カスタムキーワード"

    def test_with_exclude_keyword(self):
        """除外キーワード"""
        item = _create_resolved_item(name="テスト商品", exclude_keyword="ジャンク")

        result = price_watch.store.mercari._build_search_condition(item)

        assert result.exclude_keyword == "ジャンク"

    def test_with_price_range_single(self):
        """価格範囲（最小値のみ）"""
        item = _create_resolved_item(name="テスト商品", price_range=[1000])

        result = price_watch.store.mercari._build_search_condition(item)

        assert result.price_min == 1000
        assert result.price_max is None

    def test_with_price_range_full(self):
        """価格範囲（最小・最大）"""
        item = _create_resolved_item(name="テスト商品", price_range=[1000, 5000])

        result = price_watch.store.mercari._build_search_condition(item)

        assert result.price_min == 1000
        assert result.price_max == 5000

    def test_with_cond(self):
        """商品状態"""
        item = _create_resolved_item(name="テスト商品", cond="NEW|LIKE_NEW")

        result = price_watch.store.mercari._build_search_condition(item)

        assert result.item_conditions is not None
        assert len(result.item_conditions) == 2


class TestBuildSearchCondJson:
    """_build_search_cond_json 関数のテスト"""

    def test_empty_condition(self):
        """空の検索条件"""
        condition = MagicMock()
        condition.exclude_keyword = None
        condition.price_min = None
        condition.price_max = None
        condition.item_conditions = None

        result = price_watch.store.mercari._build_search_cond_json(condition)

        assert result == ""

    def test_with_exclude(self):
        """除外キーワード"""
        condition = MagicMock()
        condition.exclude_keyword = "ジャンク"
        condition.price_min = None
        condition.price_max = None
        condition.item_conditions = None

        result = price_watch.store.mercari._build_search_cond_json(condition)

        assert '"exclude": "ジャンク"' in result

    def test_with_price_range(self):
        """価格範囲"""
        condition = MagicMock()
        condition.exclude_keyword = None
        condition.price_min = 1000
        condition.price_max = 5000
        condition.item_conditions = None

        result = price_watch.store.mercari._build_search_cond_json(condition)

        assert '"price_min": 1000' in result
        assert '"price_max": 5000' in result

    def test_with_conditions(self):
        """商品状態"""
        mock_cond = MagicMock()
        mock_cond.value = "NEW"

        condition = MagicMock()
        condition.exclude_keyword = None
        condition.price_min = None
        condition.price_max = None
        condition.item_conditions = [mock_cond]

        result = price_watch.store.mercari._build_search_cond_json(condition)

        assert '"cond": ["NEW"]' in result


class TestCheck:
    """check 関数のテスト"""

    def test_no_results(self):
        """検索結果なし"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        item = _create_resolved_item(name="テスト商品")

        with patch("my_lib.store.mercari.search.search", return_value=[]):
            result = price_watch.store.mercari.check(mock_config, mock_driver, item)

        assert result.stock == price_watch.models.StockStatus.OUT_OF_STOCK
        assert result.crawl_status == price_watch.models.CrawlStatus.SUCCESS

    def test_with_results(self):
        """検索結果あり"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        item = _create_resolved_item(name="テスト商品")

        mock_results = [
            MockSearchResult(title="商品A", price=3000, url="https://mercari.com/a"),
            MockSearchResult(title="商品B", price=2000, url="https://mercari.com/b"),  # 最安
            MockSearchResult(title="商品C", price=4000, url="https://mercari.com/c"),
        ]

        with patch("my_lib.store.mercari.search.search", return_value=mock_results):
            result = price_watch.store.mercari.check(mock_config, mock_driver, item)

        # 最安値の商品を選択
        assert result.url == "https://mercari.com/b"
        assert result.price == 2000
        assert result.stock == price_watch.models.StockStatus.IN_STOCK
        assert result.crawl_status == price_watch.models.CrawlStatus.SUCCESS

    def test_filters_by_price_range(self):
        """価格範囲でフィルタリング"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        item = _create_resolved_item(name="テスト商品", price_range=[2000, 3500])

        mock_results = [
            MockSearchResult(title="商品A", price=1000, url="https://mercari.com/a"),  # 範囲外
            MockSearchResult(title="商品B", price=2500, url="https://mercari.com/b"),  # 範囲内
            MockSearchResult(title="商品C", price=5000, url="https://mercari.com/c"),  # 範囲外
        ]

        with patch("my_lib.store.mercari.search.search", return_value=mock_results):
            result = price_watch.store.mercari.check(mock_config, mock_driver, item)

        # 範囲内の商品のみ
        assert result.url == "https://mercari.com/b"
        assert result.price == 2500

    def test_no_results_after_filter(self):
        """フィルタリング後に結果なし"""
        mock_config = MagicMock()
        mock_driver = MagicMock()
        item = _create_resolved_item(name="テスト商品", price_range=[10000, 20000])

        mock_results = [
            MockSearchResult(title="商品A", price=1000, url="https://mercari.com/a"),
        ]

        with patch("my_lib.store.mercari.search.search", return_value=mock_results):
            result = price_watch.store.mercari.check(mock_config, mock_driver, item)

        assert result.stock == price_watch.models.StockStatus.OUT_OF_STOCK


class TestGenerateItemKey:
    """generate_item_key 関数のテスト"""

    def test_basic(self):
        """基本的なキー生成"""
        item = _create_checked_item(
            search_keyword="テスト",
            search_cond='{"exclude": "ジャンク"}',
        )

        with patch("price_watch.history.generate_item_key", return_value="generated_key"):
            result = price_watch.store.mercari.generate_item_key(item)

        assert result == "generated_key"

    def test_without_search_cond(self):
        """search_cond なし"""
        item = _create_checked_item(search_keyword="テスト")

        with patch("price_watch.history.generate_item_key", return_value="key"):
            result = price_watch.store.mercari.generate_item_key(item)

        assert result == "key"
