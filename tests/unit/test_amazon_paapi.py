#!/usr/bin/env python3
# ruff: noqa: S101
"""
store/amazon/paapi.py のユニットテスト

Amazon PA-API による価格チェックを検証します。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch

import price_watch.store.amazon.paapi


@dataclass
class MockAmazonItem:
    """モック用の AmazonItem"""

    asin: str
    price: int | None = None
    thumb_url: str | None = None


class TestCheckItemList:
    """check_item_list 関数のテスト"""

    def test_empty_list_returns_empty(self):
        """空のリストは空のリストを返す"""
        mock_config = MagicMock()
        result = price_watch.store.amazon.paapi.check_item_list(mock_config, [])
        assert result == []

    def test_no_amazon_api_config_returns_empty(self):
        """Amazon API 設定がない場合は空のリストを返す"""
        mock_config = MagicMock()
        mock_config.store.amazon_api = None

        item_list: list[dict[str, Any]] = [{"name": "Test", "asin": "B12345"}]
        result = price_watch.store.amazon.paapi.check_item_list(mock_config, item_list)

        assert result == []

    def test_successful_price_check(self):
        """価格チェック成功"""
        mock_config = MagicMock()
        mock_config.store.amazon_api = MagicMock()

        item_list: list[dict[str, Any]] = [
            {"name": "Product A", "asin": "B001"},
            {"name": "Product B", "asin": "B002"},
        ]

        # API 結果をモック
        mock_result_items = [
            MockAmazonItem(asin="B001", price=1000, thumb_url="https://example.com/a.jpg"),
            MockAmazonItem(asin="B002", price=2000, thumb_url=None),
        ]

        with (
            patch("my_lib.store.amazon.api.check_item_list", return_value=mock_result_items),
            patch("my_lib.store.amazon.config.AmazonItem.parse", side_effect=lambda x: x),
            patch("price_watch.store.amazon.paapi_rate_limiter.get_rate_limiter") as mock_rate_limiter,
            patch("price_watch.thumbnail.save_thumb", return_value="/price/thumb/abc.png"),
        ):
            mock_rate_limiter.return_value.__enter__ = MagicMock(return_value=None)
            mock_rate_limiter.return_value.__exit__ = MagicMock(return_value=None)

            result = price_watch.store.amazon.paapi.check_item_list(mock_config, item_list)

        assert len(result) == 2
        assert result[0]["stock"] == 1
        assert result[0]["price"] == 1000
        assert result[0]["thumb_url"] == "/price/thumb/abc.png"
        assert result[1]["stock"] == 1
        assert result[1]["price"] == 2000

    def test_item_not_in_result(self):
        """結果にないアイテムは在庫なし"""
        mock_config = MagicMock()
        mock_config.store.amazon_api = MagicMock()

        item_list: list[dict[str, Any]] = [{"name": "Product A", "asin": "B001"}]

        # 空の結果を返す
        mock_result_items: list[MockAmazonItem] = []

        with (
            patch("my_lib.store.amazon.api.check_item_list", return_value=mock_result_items),
            patch("my_lib.store.amazon.config.AmazonItem.parse", side_effect=lambda x: x),
            patch("price_watch.store.amazon.paapi_rate_limiter.get_rate_limiter") as mock_rate_limiter,
        ):
            mock_rate_limiter.return_value.__enter__ = MagicMock(return_value=None)
            mock_rate_limiter.return_value.__exit__ = MagicMock(return_value=None)

            result = price_watch.store.amazon.paapi.check_item_list(mock_config, item_list)

        assert result[0]["stock"] == 0

    def test_item_with_no_price(self):
        """価格がない場合は在庫なし"""
        mock_config = MagicMock()
        mock_config.store.amazon_api = MagicMock()

        item_list: list[dict[str, Any]] = [{"name": "Product A", "asin": "B001"}]

        mock_result_items = [MockAmazonItem(asin="B001", price=None)]

        with (
            patch("my_lib.store.amazon.api.check_item_list", return_value=mock_result_items),
            patch("my_lib.store.amazon.config.AmazonItem.parse", side_effect=lambda x: x),
            patch("price_watch.store.amazon.paapi_rate_limiter.get_rate_limiter") as mock_rate_limiter,
        ):
            mock_rate_limiter.return_value.__enter__ = MagicMock(return_value=None)
            mock_rate_limiter.return_value.__exit__ = MagicMock(return_value=None)

            result = price_watch.store.amazon.paapi.check_item_list(mock_config, item_list)

        assert result[0]["stock"] == 0

    def test_thumb_url_fallback(self):
        """サムネイル保存失敗時はオリジナル URL"""
        mock_config = MagicMock()
        mock_config.store.amazon_api = MagicMock()

        item_list: list[dict[str, Any]] = [{"name": "Product A", "asin": "B001"}]

        mock_result_items = [
            MockAmazonItem(asin="B001", price=1000, thumb_url="https://original.com/thumb.jpg")
        ]

        with (
            patch("my_lib.store.amazon.api.check_item_list", return_value=mock_result_items),
            patch("my_lib.store.amazon.config.AmazonItem.parse", side_effect=lambda x: x),
            patch("price_watch.store.amazon.paapi_rate_limiter.get_rate_limiter") as mock_rate_limiter,
            patch("price_watch.thumbnail.save_thumb", return_value=None),  # 保存失敗
        ):
            mock_rate_limiter.return_value.__enter__ = MagicMock(return_value=None)
            mock_rate_limiter.return_value.__exit__ = MagicMock(return_value=None)

            result = price_watch.store.amazon.paapi.check_item_list(mock_config, item_list)

        assert result[0]["thumb_url"] == "https://original.com/thumb.jpg"

    def test_exception_returns_empty(self):
        """例外発生時は空のリストを返す"""
        mock_config = MagicMock()
        mock_config.store.amazon_api = MagicMock()

        item_list: list[dict[str, Any]] = [{"name": "Product A", "asin": "B001"}]

        with (
            patch(
                "my_lib.store.amazon.api.check_item_list",
                side_effect=Exception("API Error"),
            ),
            patch("my_lib.store.amazon.config.AmazonItem.parse", side_effect=lambda x: x),
            patch("price_watch.store.amazon.paapi_rate_limiter.get_rate_limiter") as mock_rate_limiter,
        ):
            mock_rate_limiter.return_value.__enter__ = MagicMock(return_value=None)
            mock_rate_limiter.return_value.__exit__ = MagicMock(return_value=None)

            result = price_watch.store.amazon.paapi.check_item_list(mock_config, item_list)

        assert result == []
