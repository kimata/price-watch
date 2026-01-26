#!/usr/bin/env python3
# ruff: noqa: S101
"""
item モジュールのユニットテスト

アイテムリスト管理機能を検証します。
"""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock, patch

import price_watch.item
import price_watch.target


class TestLoadResolvedItems:
    """_load_resolved_items 関数のテスト"""

    def test_loads_items_from_target_file(self, tmp_path: pathlib.Path) -> None:
        """ターゲットファイルからアイテムを読み込む"""
        # モックの ResolvedItem を作成
        mock_item1 = MagicMock(spec=price_watch.target.ResolvedItem)
        mock_item1.url = "https://example.com/item1"
        mock_item2 = MagicMock(spec=price_watch.target.ResolvedItem)
        mock_item2.url = "https://example.com/item2"

        mock_config = MagicMock()
        mock_config.resolve_items.return_value = [mock_item1, mock_item2]

        with patch("price_watch.target.load", return_value=mock_config) as mock_load:
            target_file = tmp_path / "target.yaml"
            result = price_watch.item._load_resolved_items(target_file)

            mock_load.assert_called_once_with(target_file)
            assert len(result) == 2
            assert result[0].url == "https://example.com/item1"
            assert result[1].url == "https://example.com/item2"

    def test_loads_items_with_none_target_file(self) -> None:
        """ターゲットファイルが None の場合はデフォルトを使用"""
        mock_config = MagicMock()
        mock_config.resolve_items.return_value = []

        with patch("price_watch.target.load", return_value=mock_config) as mock_load:
            result = price_watch.item._load_resolved_items(None)

            mock_load.assert_called_once_with(None)
            assert result == []


class TestGetTargetUrls:
    """get_target_urls 関数のテスト"""

    def test_returns_set_of_urls(self, tmp_path: pathlib.Path) -> None:
        """URLのセットを返す"""
        mock_item1 = MagicMock(spec=price_watch.target.ResolvedItem)
        mock_item1.url = "https://example.com/item1"
        mock_item2 = MagicMock(spec=price_watch.target.ResolvedItem)
        mock_item2.url = "https://example.com/item2"

        mock_config = MagicMock()
        mock_config.resolve_items.return_value = [mock_item1, mock_item2]

        with patch("price_watch.target.load", return_value=mock_config):
            target_file = tmp_path / "target.yaml"
            result = price_watch.item.get_target_urls(target_file)

            assert isinstance(result, set)
            assert result == {"https://example.com/item1", "https://example.com/item2"}

    def test_returns_empty_set_when_no_items(self) -> None:
        """アイテムがない場合は空のセットを返す"""
        mock_config = MagicMock()
        mock_config.resolve_items.return_value = []

        with patch("price_watch.target.load", return_value=mock_config):
            result = price_watch.item.get_target_urls(None)

            assert result == set()

    def test_removes_duplicate_urls(self) -> None:
        """重複するURLは1つにまとめる"""
        mock_item1 = MagicMock(spec=price_watch.target.ResolvedItem)
        mock_item1.url = "https://example.com/same"
        mock_item2 = MagicMock(spec=price_watch.target.ResolvedItem)
        mock_item2.url = "https://example.com/same"
        mock_item3 = MagicMock(spec=price_watch.target.ResolvedItem)
        mock_item3.url = "https://example.com/different"

        mock_config = MagicMock()
        mock_config.resolve_items.return_value = [mock_item1, mock_item2, mock_item3]

        with patch("price_watch.target.load", return_value=mock_config):
            result = price_watch.item.get_target_urls(None)

            assert len(result) == 2
            assert "https://example.com/same" in result
            assert "https://example.com/different" in result
