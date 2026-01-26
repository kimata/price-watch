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
            result = manager.get_resolved_items()

        assert result == mock_items
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
            result = manager.get_resolved_items()

        assert len(result) == 1
        assert manager._target is new_target
