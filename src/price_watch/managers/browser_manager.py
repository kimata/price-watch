#!/usr/bin/env python3
"""ブラウザ管理.

WebDriver のライフサイクルを管理します。
"""

from __future__ import annotations

import logging
import pathlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

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
    遅延初期化により、必要になるまでブラウザを起動しません。
    """

    selenium_data_dir: pathlib.Path
    max_create_retries: int = 2
    _driver: WebDriver | None = field(default=None, init=False, repr=False)
    _create_failures: int = field(default=0, init=False)

    @property
    def driver(self) -> WebDriver | None:
        """WebDriver を取得.

        Returns:
            WebDriver インスタンス、または None
        """
        return self._driver

    @property
    def is_active(self) -> bool:
        """ドライバーがアクティブかどうかを確認.

        Returns:
            ドライバーが存在し、アクティブな場合 True
        """
        return self._driver is not None

    def ensure_driver(self) -> WebDriver:
        """WebDriver を取得。存在しない場合は作成.

        Returns:
            WebDriver インスタンス

        Raises:
            BrowserError: ドライバーの作成に失敗した場合
        """
        if self._driver is None:
            self._driver = self._create_driver_with_retry()
            if self._driver is None:
                raise price_watch.exceptions.BrowserError(
                    f"Failed to create driver after {self.max_create_retries + 1} attempts"
                )
        return self._driver

    def _create_driver_with_retry(self) -> WebDriver | None:
        """プロファイル削除を伴うリトライ付きでドライバーを作成.

        Returns:
            成功時は WebDriver、全て失敗時は None
        """
        for attempt in range(self.max_create_retries + 1):
            try:
                driver = my_lib.selenium_util.create_driver(PROFILE_NAME, self.selenium_data_dir)
                self._create_failures = 0
                logging.info("WebDriver created successfully")
                return driver
            except Exception as e:
                self._create_failures += 1
                logging.warning(
                    "ドライバー作成失敗（%d/%d）: %s",
                    attempt + 1,
                    self.max_create_retries + 1,
                    e,
                )

                if attempt < self.max_create_retries:
                    # プロファイルを削除してリトライ
                    logging.warning("プロファイルを削除してリトライします")
                    my_lib.chrome_util.delete_profile(PROFILE_NAME, self.selenium_data_dir)

        logging.error("ドライバー作成に %d 回失敗しました", self.max_create_retries + 1)
        return None

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

        # 新しいドライバーを作成
        self._driver = self._create_driver_with_retry()
        return self._driver is not None

    def quit(self) -> None:
        """ドライバーを終了.

        プロセス終了待機・強制終了も含む graceful な終了を行います。
        """
        if self._driver is not None:
            my_lib.selenium_util.quit_driver_gracefully(self._driver)
            self._driver = None

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
