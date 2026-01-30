#!/usr/bin/env python3
# ruff: noqa: S101
"""
managers/browser_manager.py のユニットテスト

WebDriver ライフサイクルの管理を検証します。
新しい実装では my_lib.browser_manager.BrowserManager をラップしています。
"""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock, patch

import my_lib.selenium_util
import pytest

import price_watch.exceptions
import price_watch.managers.browser_manager


class TestBrowserManagerProperties:
    """BrowserManager のプロパティテスト"""

    def test_driver_returns_none_initially(self, tmp_path: pathlib.Path) -> None:
        """初期状態では driver は None"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)

        # 内部マネージャーの has_driver() が False を返すようにモック
        with patch("my_lib.browser_manager.BrowserManager") as mock_manager_class:
            mock_inner_manager = MagicMock()
            mock_inner_manager.has_driver.return_value = False
            mock_manager_class.return_value = mock_inner_manager

            # 内部マネージャーをリセットして新しいモックを使用
            manager._manager = None
            assert manager.driver is None

    def test_is_active_returns_false_initially(self, tmp_path: pathlib.Path) -> None:
        """初期状態では is_active は False"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)
        # _manager が None の場合、is_active は False
        assert manager.is_active is False

    def test_is_active_returns_true_when_driver_exists(self, tmp_path: pathlib.Path) -> None:
        """driver が存在する場合、is_active は True"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)

        # 内部マネージャーをモックして has_driver() が True を返すようにする
        mock_inner_manager = MagicMock()
        mock_inner_manager.has_driver.return_value = True
        manager._manager = mock_inner_manager

        assert manager.is_active is True


class TestDriverProperty:
    """driver プロパティのテスト"""

    def test_driver_returns_driver_when_exists(self, tmp_path: pathlib.Path) -> None:
        """ドライバーが存在する場合は返す"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)
        mock_driver = MagicMock()
        mock_wait = MagicMock()

        mock_inner_manager = MagicMock()
        mock_inner_manager.has_driver.return_value = True
        mock_inner_manager.get_driver.return_value = (mock_driver, mock_wait)
        manager._manager = mock_inner_manager

        assert manager.driver is mock_driver


class TestEnsureDriver:
    """ensure_driver メソッドのテスト"""

    def test_creates_driver_if_none(self, tmp_path: pathlib.Path) -> None:
        """driver が None の場合は作成"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)
        mock_driver = MagicMock()
        mock_wait = MagicMock()

        with patch("my_lib.browser_manager.BrowserManager") as mock_manager_class:
            mock_inner_manager = MagicMock()
            mock_inner_manager.get_driver.return_value = (mock_driver, mock_wait)
            mock_manager_class.return_value = mock_inner_manager

            result = manager.ensure_driver()

        assert result is mock_driver

    def test_returns_existing_driver(self, tmp_path: pathlib.Path) -> None:
        """driver が存在する場合は返す"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)
        existing_driver = MagicMock()
        existing_wait = MagicMock()

        mock_inner_manager = MagicMock()
        mock_inner_manager.get_driver.return_value = (existing_driver, existing_wait)
        manager._manager = mock_inner_manager

        result = manager.ensure_driver()

        assert result is existing_driver

    def test_raises_browser_error_on_failure(self, tmp_path: pathlib.Path) -> None:
        """作成失敗時は BrowserError を raise"""
        manager = price_watch.managers.browser_manager.BrowserManager(
            selenium_data_dir=tmp_path, max_create_retries=0
        )

        with patch("my_lib.browser_manager.BrowserManager") as mock_manager_class:
            mock_inner_manager = MagicMock()
            mock_inner_manager.get_driver.side_effect = my_lib.selenium_util.SeleniumError("Failed")
            mock_manager_class.return_value = mock_inner_manager

            with pytest.raises(price_watch.exceptions.BrowserError):
                manager.ensure_driver()


class TestRecreateDriver:
    """recreate_driver メソッドのテスト"""

    def test_recreates_driver(self, tmp_path: pathlib.Path) -> None:
        """ドライバーを再作成"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)
        new_driver = MagicMock()
        new_wait = MagicMock()

        # 既存の内部マネージャーをモック
        old_inner_manager = MagicMock()
        manager._manager = old_inner_manager

        with (
            patch("my_lib.chrome_util.delete_profile"),
            patch("my_lib.browser_manager.BrowserManager") as mock_manager_class,
        ):
            new_inner_manager = MagicMock()
            new_inner_manager.get_driver.return_value = (new_driver, new_wait)
            mock_manager_class.return_value = new_inner_manager

            result = manager.recreate_driver()

        assert result is True
        old_inner_manager.quit.assert_called_once()

    def test_returns_false_on_failure(self, tmp_path: pathlib.Path) -> None:
        """作成失敗時は False を返す"""
        manager = price_watch.managers.browser_manager.BrowserManager(
            selenium_data_dir=tmp_path, max_create_retries=0
        )

        # 既存の内部マネージャーをモック
        old_inner_manager = MagicMock()
        manager._manager = old_inner_manager

        with (
            patch("my_lib.chrome_util.delete_profile"),
            patch("my_lib.browser_manager.BrowserManager") as mock_manager_class,
        ):
            new_inner_manager = MagicMock()
            new_inner_manager.get_driver.side_effect = my_lib.selenium_util.SeleniumError("Failed")
            mock_manager_class.return_value = new_inner_manager

            result = manager.recreate_driver()

        assert result is False


class TestQuit:
    """quit メソッドのテスト"""

    def test_quits_driver(self, tmp_path: pathlib.Path) -> None:
        """ドライバーを終了"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)

        mock_inner_manager = MagicMock()
        manager._manager = mock_inner_manager

        manager.quit()

        mock_inner_manager.quit.assert_called_once()

    def test_does_nothing_if_no_manager(self, tmp_path: pathlib.Path) -> None:
        """内部マネージャーがない場合は何もしない"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)
        # _manager が None のまま

        # 例外が発生しないことを確認
        manager.quit()


class TestCleanupProfileLock:
    """cleanup_profile_lock メソッドのテスト"""

    def test_calls_cleanup_function(self, tmp_path: pathlib.Path) -> None:
        """クリーンアップ関数を呼び出す"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)

        with patch("my_lib.chrome_util.cleanup_profile_lock") as mock_cleanup:
            manager.cleanup_profile_lock()

        mock_cleanup.assert_called_once_with(price_watch.managers.browser_manager.PROFILE_NAME, tmp_path)


class TestContextManager:
    """コンテキストマネージャーのテスト"""

    def test_enter_returns_self(self, tmp_path: pathlib.Path) -> None:
        """__enter__ は self を返す"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)

        with patch("my_lib.chrome_util.cleanup_profile_lock"), manager as ctx:
            assert ctx is manager

    def test_exit_cleans_up(self, tmp_path: pathlib.Path) -> None:
        """__exit__ でクリーンアップ"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)

        mock_inner_manager = MagicMock()
        manager._manager = mock_inner_manager

        with patch("my_lib.chrome_util.cleanup_profile_lock") as mock_cleanup, manager:
            pass

        mock_inner_manager.quit.assert_called_once()
        mock_cleanup.assert_called_once()


class TestInternalManagerCreation:
    """内部マネージャー作成のテスト"""

    def test_creates_manager_with_correct_parameters(self, tmp_path: pathlib.Path) -> None:
        """正しいパラメータで内部マネージャーを作成"""
        manager = price_watch.managers.browser_manager.BrowserManager(
            selenium_data_dir=tmp_path, max_create_retries=3
        )

        with patch("my_lib.browser_manager.BrowserManager") as mock_manager_class:
            mock_inner = MagicMock()
            mock_inner.has_driver.return_value = False
            mock_manager_class.return_value = mock_inner

            # driver プロパティにアクセスして内部マネージャーを作成
            _ = manager.driver

            mock_manager_class.assert_called_once_with(
                profile_name=price_watch.managers.browser_manager.PROFILE_NAME,
                data_dir=tmp_path,
                clear_profile_on_error=True,
                max_retry_on_error=3,
            )

    def test_reuses_existing_manager(self, tmp_path: pathlib.Path) -> None:
        """既存の内部マネージャーを再利用"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)

        mock_inner_manager = MagicMock()
        mock_inner_manager.has_driver.return_value = False
        manager._manager = mock_inner_manager

        with patch("my_lib.browser_manager.BrowserManager") as mock_manager_class:
            # driver プロパティに2回アクセス
            _ = manager.driver
            _ = manager.driver

            # 新しいマネージャーは作成されない
            mock_manager_class.assert_not_called()
