#!/usr/bin/env python3
# ruff: noqa: S101
"""
managers/config_manager.py のユニットテスト

設定管理を検証します。
"""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock, patch

import pytest

import price_watch.exceptions
import price_watch.managers.config_manager


class TestConfigManagerProperties:
    """ConfigManager のプロパティテスト"""

    def test_config_lazy_loads(self, tmp_path: pathlib.Path) -> None:
        """config は遅延読み込み"""
        config_file = tmp_path / "config.yaml"
        target_file = tmp_path / "target.yaml"

        manager = price_watch.managers.config_manager.ConfigManager(
            config_file=config_file, target_file=target_file
        )
        mock_config = MagicMock()

        with patch("price_watch.config.load", return_value=mock_config):
            result = manager.config

        assert result is mock_config
        assert manager._config is mock_config

    def test_config_returns_cached(self, tmp_path: pathlib.Path) -> None:
        """config はキャッシュを返す"""
        config_file = tmp_path / "config.yaml"
        target_file = tmp_path / "target.yaml"

        manager = price_watch.managers.config_manager.ConfigManager(
            config_file=config_file, target_file=target_file
        )
        mock_config = MagicMock()
        manager._config = mock_config

        result = manager.config

        assert result is mock_config

    def test_target_lazy_loads(self, tmp_path: pathlib.Path) -> None:
        """target は遅延読み込み"""
        config_file = tmp_path / "config.yaml"
        target_file = tmp_path / "target.yaml"

        manager = price_watch.managers.config_manager.ConfigManager(
            config_file=config_file, target_file=target_file
        )
        mock_target = MagicMock()

        with patch("price_watch.target.load", return_value=mock_target):
            result = manager.target

        assert result is mock_target
        assert manager._target is mock_target

    def test_target_returns_cached(self, tmp_path: pathlib.Path) -> None:
        """target はキャッシュを返す"""
        config_file = tmp_path / "config.yaml"
        target_file = tmp_path / "target.yaml"

        manager = price_watch.managers.config_manager.ConfigManager(
            config_file=config_file, target_file=target_file
        )
        mock_target = MagicMock()
        manager._target = mock_target

        result = manager.target

        assert result is mock_target


class TestLoadConfig:
    """_load_config メソッドのテスト"""

    def test_loads_config_file(self, tmp_path: pathlib.Path) -> None:
        """設定ファイルを読み込む"""
        config_file = tmp_path / "config.yaml"
        target_file = tmp_path / "target.yaml"

        manager = price_watch.managers.config_manager.ConfigManager(
            config_file=config_file, target_file=target_file
        )
        mock_config = MagicMock()

        with patch("price_watch.config.load", return_value=mock_config) as mock_load:
            result = manager._load_config()

        mock_load.assert_called_once_with(config_file)
        assert result is mock_config

    def test_raises_config_error_on_failure(self, tmp_path: pathlib.Path) -> None:
        """読み込み失敗時は ConfigError を raise"""
        config_file = tmp_path / "config.yaml"
        target_file = tmp_path / "target.yaml"

        manager = price_watch.managers.config_manager.ConfigManager(
            config_file=config_file, target_file=target_file
        )

        with (
            patch("price_watch.config.load", side_effect=Exception("Failed")),
            pytest.raises(price_watch.exceptions.ConfigError),
        ):
            manager._load_config()


class TestLoadTarget:
    """_load_target メソッドのテスト"""

    def test_loads_target_file(self, tmp_path: pathlib.Path) -> None:
        """ターゲットファイルを読み込む"""
        config_file = tmp_path / "config.yaml"
        target_file = tmp_path / "target.yaml"

        manager = price_watch.managers.config_manager.ConfigManager(
            config_file=config_file, target_file=target_file
        )
        mock_target = MagicMock()

        with patch("price_watch.target.load", return_value=mock_target) as mock_load:
            result = manager._load_target()

        mock_load.assert_called_once_with(target_file)
        assert result is mock_target

    def test_raises_config_error_on_failure(self, tmp_path: pathlib.Path) -> None:
        """読み込み失敗時は ConfigError を raise"""
        config_file = tmp_path / "config.yaml"
        target_file = tmp_path / "target.yaml"

        manager = price_watch.managers.config_manager.ConfigManager(
            config_file=config_file, target_file=target_file
        )

        with (
            patch("price_watch.target.load", side_effect=Exception("Failed")),
            pytest.raises(price_watch.exceptions.ConfigError),
        ):
            manager._load_target()


class TestReloadConfig:
    """reload_config メソッドのテスト"""

    def test_reloads_config(self, tmp_path: pathlib.Path) -> None:
        """設定をリロード"""
        config_file = tmp_path / "config.yaml"
        target_file = tmp_path / "target.yaml"

        manager = price_watch.managers.config_manager.ConfigManager(
            config_file=config_file, target_file=target_file
        )
        old_config = MagicMock()
        new_config = MagicMock()
        manager._config = old_config

        with patch("price_watch.config.load", return_value=new_config):
            manager.reload_config()

        assert manager._config is new_config


class TestReloadTarget:
    """reload_target メソッドのテスト"""

    def test_reloads_target(self, tmp_path: pathlib.Path) -> None:
        """ターゲットをリロード"""
        config_file = tmp_path / "config.yaml"
        target_file = tmp_path / "target.yaml"

        manager = price_watch.managers.config_manager.ConfigManager(
            config_file=config_file, target_file=target_file
        )
        old_target = MagicMock()
        new_target = MagicMock()
        manager._target = old_target

        with patch("price_watch.target.load", return_value=new_target):
            manager.reload_target()

        assert manager._target is new_target


class TestGetResolvedItems:
    """get_resolved_items メソッドのテスト"""

    def test_returns_resolved_items(self, tmp_path: pathlib.Path) -> None:
        """解決済みアイテムを返す"""
        config_file = tmp_path / "config.yaml"
        target_file = tmp_path / "target.yaml"

        manager = price_watch.managers.config_manager.ConfigManager(
            config_file=config_file, target_file=target_file
        )
        mock_items = [MagicMock(), MagicMock()]
        mock_target = MagicMock()
        mock_target.resolve_items.return_value = mock_items

        with patch("price_watch.target.load", return_value=mock_target):
            items, diff = manager.get_resolved_items()

        assert items == mock_items
        mock_target.resolve_items.assert_called_once()

    def test_reloads_target_before_resolve(self, tmp_path: pathlib.Path) -> None:
        """解決前にターゲットをリロード"""
        config_file = tmp_path / "config.yaml"
        target_file = tmp_path / "target.yaml"

        manager = price_watch.managers.config_manager.ConfigManager(
            config_file=config_file, target_file=target_file
        )
        old_target = MagicMock()
        old_target.resolve_items.return_value = []
        manager._target = old_target

        new_target = MagicMock()
        new_target.resolve_items.return_value = [MagicMock()]

        with patch("price_watch.target.load", return_value=new_target):
            items, _diff = manager.get_resolved_items()

        assert len(items) == 1
        assert manager._target is new_target

    def test_first_call_returns_none_diff(self, tmp_path: pathlib.Path) -> None:
        """初回呼び出し時は diff が None"""
        config_file = tmp_path / "config.yaml"
        target_file = tmp_path / "target.yaml"

        manager = price_watch.managers.config_manager.ConfigManager(
            config_file=config_file, target_file=target_file
        )
        mock_target = MagicMock()
        mock_target.resolve_items.return_value = []

        with patch("price_watch.target.load", return_value=mock_target):
            _items, diff = manager.get_resolved_items()

        assert diff is None

    def test_second_call_returns_diff(self, tmp_path: pathlib.Path) -> None:
        """2回目以降の呼び出しで diff を返す"""
        config_file = tmp_path / "config.yaml"
        target_file = tmp_path / "target.yaml"

        manager = price_watch.managers.config_manager.ConfigManager(
            config_file=config_file, target_file=target_file
        )
        mock_target = MagicMock()
        mock_target.resolve_items.return_value = []

        with patch("price_watch.target.load", return_value=mock_target):
            _items1, diff1 = manager.get_resolved_items()
            _items2, diff2 = manager.get_resolved_items()

        assert diff1 is None
        assert diff2 is not None
        assert not diff2.has_changes()


class TestComputeDiff:
    """_compute_diff メソッドのテスト"""

    def test_detects_added_items(self, tmp_path: pathlib.Path) -> None:
        """追加されたアイテムを検出"""
        import price_watch.target

        config_file = tmp_path / "config.yaml"
        target_file = tmp_path / "target.yaml"

        manager = price_watch.managers.config_manager.ConfigManager(
            config_file=config_file, target_file=target_file
        )

        old_items: list[price_watch.target.ResolvedItem] = []
        new_item = price_watch.target.ResolvedItem(
            name="商品A",
            store="Amazon",
            url="https://amazon.co.jp/dp/B0123456",
        )
        new_items = [new_item]

        diff = manager._compute_diff(old_items, new_items)

        assert len(diff.added) == 1
        assert diff.added[0].name == "商品A"
        assert not diff.removed
        assert not diff.changed

    def test_detects_removed_items(self, tmp_path: pathlib.Path) -> None:
        """削除されたアイテムを検出"""
        import price_watch.target

        config_file = tmp_path / "config.yaml"
        target_file = tmp_path / "target.yaml"

        manager = price_watch.managers.config_manager.ConfigManager(
            config_file=config_file, target_file=target_file
        )

        old_item = price_watch.target.ResolvedItem(
            name="商品A",
            store="Amazon",
            url="https://amazon.co.jp/dp/B0123456",
        )
        old_items = [old_item]
        new_items: list[price_watch.target.ResolvedItem] = []

        diff = manager._compute_diff(old_items, new_items)

        assert not diff.added
        assert len(diff.removed) == 1
        assert diff.removed[0].name == "商品A"
        assert not diff.changed

    def test_detects_changed_items(self, tmp_path: pathlib.Path) -> None:
        """変更されたアイテムを検出"""
        import price_watch.target

        config_file = tmp_path / "config.yaml"
        target_file = tmp_path / "target.yaml"

        manager = price_watch.managers.config_manager.ConfigManager(
            config_file=config_file, target_file=target_file
        )

        old_item = price_watch.target.ResolvedItem(
            name="商品A",
            store="Amazon",
            url="https://amazon.co.jp/dp/B0123456",
            search_keyword="古いキーワード",
        )
        new_item = price_watch.target.ResolvedItem(
            name="商品A",
            store="Amazon",
            url="https://amazon.co.jp/dp/B0123456",
            search_keyword="新しいキーワード",
        )

        diff = manager._compute_diff([old_item], [new_item])

        assert not diff.added
        assert not diff.removed
        assert len(diff.changed) == 1
        item, changes = diff.changed[0]
        assert item.name == "商品A"
        assert len(changes) == 1
        assert changes[0].field == "検索キーワード"
        assert changes[0].old_value == "古いキーワード"
        assert changes[0].new_value == "新しいキーワード"

    def test_no_changes_when_items_identical(self, tmp_path: pathlib.Path) -> None:
        """変更がない場合は空の diff を返す"""
        import price_watch.target

        config_file = tmp_path / "config.yaml"
        target_file = tmp_path / "target.yaml"

        manager = price_watch.managers.config_manager.ConfigManager(
            config_file=config_file, target_file=target_file
        )

        item = price_watch.target.ResolvedItem(
            name="商品A",
            store="Amazon",
            url="https://amazon.co.jp/dp/B0123456",
        )

        diff = manager._compute_diff([item], [item])

        assert not diff.has_changes()

    def test_detects_multiple_field_changes(self, tmp_path: pathlib.Path) -> None:
        """複数フィールドの変更を検出"""
        import price_watch.target

        config_file = tmp_path / "config.yaml"
        target_file = tmp_path / "target.yaml"

        manager = price_watch.managers.config_manager.ConfigManager(
            config_file=config_file, target_file=target_file
        )

        old_item = price_watch.target.ResolvedItem(
            name="商品A",
            store="メルカリ",
            url="",
            search_keyword="古いキーワード",
            exclude_keyword="ジャンク",
            category="フリマ",
        )
        new_item = price_watch.target.ResolvedItem(
            name="商品A",
            store="メルカリ",
            url="",
            search_keyword="新しいキーワード",
            exclude_keyword=None,
            category="家電",
        )

        diff = manager._compute_diff([old_item], [new_item])

        assert len(diff.changed) == 1
        _item, changes = diff.changed[0]
        assert len(changes) == 3

        field_names = {c.field for c in changes}
        assert "検索キーワード" in field_names
        assert "除外キーワード" in field_names
        assert "カテゴリー" in field_names


class TestCompareItems:
    """_compare_items メソッドのテスト"""

    def test_compares_url(self, tmp_path: pathlib.Path) -> None:
        """URL の変更を検出"""
        import price_watch.target

        config_file = tmp_path / "config.yaml"
        target_file = tmp_path / "target.yaml"

        manager = price_watch.managers.config_manager.ConfigManager(
            config_file=config_file, target_file=target_file
        )

        old_item = price_watch.target.ResolvedItem(
            name="商品A",
            store="ヨドバシ",
            url="https://old.url",
        )
        new_item = price_watch.target.ResolvedItem(
            name="商品A",
            store="ヨドバシ",
            url="https://new.url",
        )

        changes = manager._compare_items(old_item, new_item)

        assert len(changes) == 1
        assert changes[0].field == "URL"
        assert changes[0].old_value == "https://old.url"
        assert changes[0].new_value == "https://new.url"

    def test_compares_price_range(self, tmp_path: pathlib.Path) -> None:
        """価格範囲の変更を検出"""
        import price_watch.target

        config_file = tmp_path / "config.yaml"
        target_file = tmp_path / "target.yaml"

        manager = price_watch.managers.config_manager.ConfigManager(
            config_file=config_file, target_file=target_file
        )

        old_item = price_watch.target.ResolvedItem(
            name="商品A",
            store="メルカリ",
            url="",
            price_range=[10000],
        )
        new_item = price_watch.target.ResolvedItem(
            name="商品A",
            store="メルカリ",
            url="",
            price_range=[10000, 50000],
        )

        changes = manager._compare_items(old_item, new_item)

        assert len(changes) == 1
        assert changes[0].field == "価格範囲"
        assert changes[0].old_value == "[10000]"
        assert changes[0].new_value == "[10000, 50000]"


class TestFormatValue:
    """_format_value メソッドのテスト"""

    def test_formats_none(self, tmp_path: pathlib.Path) -> None:
        """None を (なし) に変換"""
        config_file = tmp_path / "config.yaml"
        target_file = tmp_path / "target.yaml"

        manager = price_watch.managers.config_manager.ConfigManager(
            config_file=config_file, target_file=target_file
        )

        assert manager._format_value(None) == "(なし)"

    def test_formats_list(self, tmp_path: pathlib.Path) -> None:
        """リストを文字列に変換"""
        config_file = tmp_path / "config.yaml"
        target_file = tmp_path / "target.yaml"

        manager = price_watch.managers.config_manager.ConfigManager(
            config_file=config_file, target_file=target_file
        )

        assert manager._format_value([1, 2, 3]) == "[1, 2, 3]"

    def test_formats_string(self, tmp_path: pathlib.Path) -> None:
        """文字列をそのまま返す"""
        config_file = tmp_path / "config.yaml"
        target_file = tmp_path / "target.yaml"

        manager = price_watch.managers.config_manager.ConfigManager(
            config_file=config_file, target_file=target_file
        )

        assert manager._format_value("test") == "test"
