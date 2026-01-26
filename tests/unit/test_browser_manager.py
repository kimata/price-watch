#!/usr/bin/env python3
# ruff: noqa: S101
"""
managers/browser_manager.py のユニットテスト

WebDriver ライフサイクルの管理を検証します。
"""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock, patch

import pytest

import price_watch.exceptions
import price_watch.managers.browser_manager


class TestBrowserManagerProperties:
    """BrowserManager のプロパティテスト"""

    def test_driver_returns_none_initially(self, tmp_path: pathlib.Path) -> None:
        """初期状態では driver は None"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)
        assert manager.driver is None

    def test_is_active_returns_false_initially(self, tmp_path: pathlib.Path) -> None:
        """初期状態では is_active は False"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)
        assert manager.is_active is False

    def test_is_active_returns_true_when_driver_exists(self, tmp_path: pathlib.Path) -> None:
        """driver が存在する場合、is_active は True"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)
        manager._driver = MagicMock()
        assert manager.is_active is True


class TestEnsureDriver:
    """ensure_driver メソッドのテスト"""

    def test_creates_driver_if_none(self, tmp_path: pathlib.Path) -> None:
        """driver が None の場合は作成"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)
        mock_driver = MagicMock()

        with patch("my_lib.selenium_util.create_driver", return_value=mock_driver):
            result = manager.ensure_driver()

        assert result is mock_driver
        assert manager._driver is mock_driver

    def test_returns_existing_driver(self, tmp_path: pathlib.Path) -> None:
        """driver が存在する場合は返す"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)
        existing_driver = MagicMock()
        manager._driver = existing_driver

        result = manager.ensure_driver()

        assert result is existing_driver

    def test_raises_browser_error_on_failure(self, tmp_path: pathlib.Path) -> None:
        """作成失敗時は BrowserError を raise"""
        manager = price_watch.managers.browser_manager.BrowserManager(
            selenium_data_dir=tmp_path, max_create_retries=0
        )

        with (
            patch("my_lib.selenium_util.create_driver", side_effect=Exception("Failed")),
            pytest.raises(price_watch.exceptions.BrowserError),
        ):
            manager.ensure_driver()


class TestCreateDriverWithRetry:
    """_create_driver_with_retry メソッドのテスト"""

    def test_success_on_first_attempt(self, tmp_path: pathlib.Path) -> None:
        """初回成功"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)
        mock_driver = MagicMock()

        with patch("my_lib.selenium_util.create_driver", return_value=mock_driver):
            result = manager._create_driver_with_retry()

        assert result is mock_driver
        assert manager._create_failures == 0

    def test_success_on_retry(self, tmp_path: pathlib.Path) -> None:
        """リトライで成功"""
        manager = price_watch.managers.browser_manager.BrowserManager(
            selenium_data_dir=tmp_path, max_create_retries=2
        )
        mock_driver = MagicMock()

        call_count = 0

        def create_with_failure(*_: object, **__: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Temporary failure")
            return mock_driver

        with (
            patch("my_lib.selenium_util.create_driver", side_effect=create_with_failure),
            patch("my_lib.chrome_util.delete_profile"),
        ):
            result = manager._create_driver_with_retry()

        assert result is mock_driver

    def test_failure_after_all_retries(self, tmp_path: pathlib.Path) -> None:
        """全リトライ失敗"""
        manager = price_watch.managers.browser_manager.BrowserManager(
            selenium_data_dir=tmp_path, max_create_retries=1
        )

        with (
            patch("my_lib.selenium_util.create_driver", side_effect=Exception("Failed")),
            patch("my_lib.chrome_util.delete_profile"),
        ):
            result = manager._create_driver_with_retry()

        assert result is None
        assert manager._create_failures == 2


class TestRecreateDriver:
    """recreate_driver メソッドのテスト"""

    def test_recreates_driver(self, tmp_path: pathlib.Path) -> None:
        """ドライバーを再作成"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)
        old_driver = MagicMock()
        new_driver = MagicMock()
        manager._driver = old_driver

        with (
            patch("my_lib.selenium_util.quit_driver_gracefully"),
            patch("my_lib.chrome_util.delete_profile"),
            patch("my_lib.selenium_util.create_driver", return_value=new_driver),
        ):
            result = manager.recreate_driver()

        assert result is True
        assert manager._driver is new_driver

    def test_returns_false_on_failure(self, tmp_path: pathlib.Path) -> None:
        """作成失敗時は False を返す"""
        manager = price_watch.managers.browser_manager.BrowserManager(
            selenium_data_dir=tmp_path, max_create_retries=0
        )
        manager._driver = MagicMock()

        with (
            patch("my_lib.selenium_util.quit_driver_gracefully"),
            patch("my_lib.chrome_util.delete_profile"),
            patch("my_lib.selenium_util.create_driver", side_effect=Exception("Failed")),
        ):
            result = manager.recreate_driver()

        assert result is False


class TestQuit:
    """quit メソッドのテスト"""

    def test_quits_driver(self, tmp_path: pathlib.Path) -> None:
        """ドライバーを終了"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)
        mock_driver = MagicMock()
        manager._driver = mock_driver

        with patch("my_lib.selenium_util.quit_driver_gracefully") as mock_quit:
            manager.quit()

        mock_quit.assert_called_once_with(mock_driver)
        assert manager._driver is None

    def test_does_nothing_if_no_driver(self, tmp_path: pathlib.Path) -> None:
        """ドライバーがない場合は何もしない"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)

        with patch("my_lib.selenium_util.quit_driver_gracefully") as mock_quit:
            manager.quit()

        mock_quit.assert_not_called()


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

        with manager as ctx:
            assert ctx is manager

    def test_exit_cleans_up(self, tmp_path: pathlib.Path) -> None:
        """__exit__ でクリーンアップ"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)
        manager._driver = MagicMock()

        with (
            patch("my_lib.selenium_util.quit_driver_gracefully") as mock_quit,
            patch("my_lib.chrome_util.cleanup_profile_lock") as mock_cleanup,
            manager,
        ):
            pass

        mock_quit.assert_called_once()
        mock_cleanup.assert_called_once()
