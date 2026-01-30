#!/usr/bin/env python3
"""ブラウザ管理.

WebDriver のライフサイクルを管理します。
my_lib.browser_manager をラップして price-watch 固有のインターフェースを提供します。
"""

from __future__ import annotations

import logging
import pathlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import my_lib.browser_manager
import my_lib.chrome_util
import my_lib.selenium_util

import price_watch.exceptions

if TYPE_CHECKING:
    from selenium.webdriver.remote.webdriver import WebDriver


PROFILE_NAME = "Default"


@dataclass
class BrowserManager:
    """ブラウザ管理クラス.

    WebDriver の作成、再作成、終了を管理します。
    内部で my_lib.browser_manager.BrowserManager を使用します。
    """

    selenium_data_dir: pathlib.Path
    max_create_retries: int = 2

    # 内部状態
    _manager: my_lib.browser_manager.BrowserManager | None = field(default=None, init=False, repr=False)

    def _get_or_create_manager(self) -> my_lib.browser_manager.BrowserManager:
        """内部の BrowserManager を取得（必要に応じて作成）"""
        if self._manager is None:
            self._manager = my_lib.browser_manager.BrowserManager(
                profile_name=PROFILE_NAME,
                data_dir=self.selenium_data_dir,
                clear_profile_on_error=True,
                max_retry_on_error=self.max_create_retries,
            )
        return self._manager

    @property
    def driver(self) -> WebDriver | None:
        """WebDriver を取得.

        Returns:
            WebDriver インスタンス、または None
        """
        manager = self._get_or_create_manager()
        if manager.has_driver():
            driver, _ = manager.get_driver()
            return driver
        return None

    @property
    def is_active(self) -> bool:
        """ドライバーがアクティブかどうかを確認.

        Returns:
            ドライバーが存在し、アクティブな場合 True
        """
        if self._manager is None:
            return False
        return self._manager.has_driver()

    def ensure_driver(self) -> WebDriver:
        """WebDriver を取得。存在しない場合は作成.

        Returns:
            WebDriver インスタンス

        Raises:
            BrowserError: ドライバーの作成に失敗した場合
        """
        manager = self._get_or_create_manager()
        try:
            driver, _ = manager.get_driver()
            return driver
        except my_lib.selenium_util.SeleniumError as e:
            raise price_watch.exceptions.BrowserError(f"Failed to create driver: {e}") from e

    def recreate_driver(self) -> bool:
        """ドライバーを再作成.

        セッションエラー発生時にプロファイルを削除して再作成します。

        Returns:
            成功時 True
        """
        logging.warning("ドライバーを再作成します")

        # 既存ドライバーを終了
        self.quit()

        # プロファイルを削除
        my_lib.chrome_util.delete_profile(PROFILE_NAME, self.selenium_data_dir)

        # 内部マネージャーをリセット（新しいドライバー作成のため）
        self._manager = None

        # 新しいドライバーを作成
        try:
            self.ensure_driver()
            return True
        except price_watch.exceptions.BrowserError:
            logging.exception("ドライバーの再作成に失敗しました")
            return False

    def quit(self) -> None:
        """ドライバーを終了.

        プロセス終了待機・強制終了も含む graceful な終了を行います。
        """
        if self._manager is not None:
            self._manager.quit()

    def cleanup_profile_lock(self) -> None:
        """Chrome プロファイルのロックファイルをクリーンアップ."""
        my_lib.chrome_util.cleanup_profile_lock(PROFILE_NAME, self.selenium_data_dir)

    def __enter__(self) -> BrowserManager:
        """コンテキストマネージャーのエントリポイント."""
        return self

    def __exit__(
        self,
        _exc_type: type | None,
        _exc_val: Exception | None,
        _exc_tb: object,
    ) -> None:
        """コンテキストマネージャーの終了処理."""
        self.quit()
        self.cleanup_profile_lock()
