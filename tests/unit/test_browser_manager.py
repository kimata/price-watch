#!/usr/bin/env python3
# ruff: noqa: S101
"""
managers/browser_manager.py のユニットテスト

ブラウザライフサイクルの管理を検証します。
新しい実装では my_lib.browser.BrowserManager をラップしています。
"""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock, patch

import my_lib.browser
import pytest

import price_watch.exceptions
import price_watch.managers.browser_manager


class TestBrowserManagerProperties:
    """BrowserManager のプロパティテスト"""

    def test_is_active_returns_false_initially(self, tmp_path: pathlib.Path) -> None:
        """初期状態では is_active は False"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)
        assert manager.is_active is False

    def test_is_active_returns_true_when_browser_exists(self, tmp_path: pathlib.Path) -> None:
        """ブラウザが存在する場合、is_active は True"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)

        mock_inner_manager = MagicMock()
        mock_inner_manager.has_browser.return_value = True
        manager._manager = mock_inner_manager

        assert manager.is_active is True


class TestPageScope:
    """page() コンテキストマネージャのテスト"""

    def test_yields_scoped_page_and_closes_on_exit(self, tmp_path: pathlib.Path) -> None:
        """内部マネージャーの page() スコープを開き、with 終了で閉じる"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)
        mock_page = MagicMock()

        mock_inner_manager = MagicMock()
        mock_scope = mock_inner_manager.page.return_value
        mock_scope.__enter__.return_value = mock_page
        manager._manager = mock_inner_manager

        with manager.page() as page:
            assert page is mock_page
            mock_scope.__exit__.assert_not_called()

        mock_scope.__exit__.assert_called_once()

    def test_closes_scope_on_exception(self, tmp_path: pathlib.Path) -> None:
        """例外発生時もスコープを閉じる"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)

        mock_inner_manager = MagicMock()
        mock_scope = mock_inner_manager.page.return_value
        manager._manager = mock_inner_manager

        with pytest.raises(ValueError, match="boom"), manager.page():
            raise ValueError("boom")

        mock_scope.__exit__.assert_called_once()

    def test_raises_browser_error_on_launch_failure(self, tmp_path: pathlib.Path) -> None:
        """ブラウザ起動失敗時は price_watch の BrowserError を raise"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)

        mock_inner_manager = MagicMock()
        mock_inner_manager.page.return_value.__enter__.side_effect = my_lib.browser.BrowserError("Failed")
        manager._manager = mock_inner_manager

        with pytest.raises(price_watch.exceptions.BrowserError), manager.page():
            pass


class TestEnsureBrowser:
    """ensure_browser メソッドのテスト"""

    def test_creates_manager_and_launches(self, tmp_path: pathlib.Path) -> None:
        """内部マネージャーが未作成の場合は作成してブラウザを起動する"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)

        with patch("my_lib.browser.BrowserManager") as mock_manager_class:
            mock_inner_manager = MagicMock()
            mock_manager_class.return_value = mock_inner_manager

            manager.ensure_browser()

        mock_inner_manager.get_browser.assert_called_once()

    def test_raises_browser_error_on_failure(self, tmp_path: pathlib.Path) -> None:
        """起動失敗時は BrowserError を raise"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)

        mock_inner_manager = MagicMock()
        mock_inner_manager.get_browser.side_effect = my_lib.browser.BrowserError("Failed")
        manager._manager = mock_inner_manager

        with pytest.raises(price_watch.exceptions.BrowserError):
            manager.ensure_browser()


class TestRestart:
    """restart メソッドのテスト"""

    def test_restarts_browser(self, tmp_path: pathlib.Path) -> None:
        """ブラウザを再起動"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)

        mock_inner_manager = MagicMock()
        manager._manager = mock_inner_manager

        result = manager.restart()

        assert result is True
        mock_inner_manager.restart_with_clean_profile.assert_called_once()

    def test_returns_false_on_failure(self, tmp_path: pathlib.Path) -> None:
        """再起動失敗時は False を返す"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)

        mock_inner_manager = MagicMock()
        mock_inner_manager.restart_with_clean_profile.side_effect = my_lib.browser.BrowserError("Failed")
        manager._manager = mock_inner_manager

        result = manager.restart()

        assert result is False


class TestQuit:
    """quit メソッドのテスト"""

    def test_quits_browser(self, tmp_path: pathlib.Path) -> None:
        """ブラウザを終了"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)

        mock_inner_manager = MagicMock()
        manager._manager = mock_inner_manager

        manager.quit()

        mock_inner_manager.quit.assert_called_once()

    def test_does_nothing_if_no_manager(self, tmp_path: pathlib.Path) -> None:
        """内部マネージャーがない場合は何もしない"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)

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
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)

        with patch("my_lib.browser.BrowserManager") as mock_manager_class:
            mock_inner = MagicMock()
            mock_manager_class.return_value = mock_inner

            # ensure_browser で内部マネージャーを作成
            manager.ensure_browser()

            mock_manager_class.assert_called_once()
            profile = mock_manager_class.call_args[0][0]
            assert isinstance(profile, my_lib.browser.BrowserProfile)
            assert profile.name == price_watch.managers.browser_manager.PROFILE_NAME
            assert profile.data_dir == tmp_path
            assert profile.headless is True

    def test_reuses_existing_manager(self, tmp_path: pathlib.Path) -> None:
        """既存の内部マネージャーを再利用"""
        manager = price_watch.managers.browser_manager.BrowserManager(selenium_data_dir=tmp_path)

        mock_inner_manager = MagicMock()
        manager._manager = mock_inner_manager

        with patch("my_lib.browser.BrowserManager") as mock_manager_class:
            # 2 回起動を要求
            manager.ensure_browser()
            manager.ensure_browser()

            # 新しいマネージャーは作成されない
            mock_manager_class.assert_not_called()
