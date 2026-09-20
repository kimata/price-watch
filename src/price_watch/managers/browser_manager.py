#!/usr/bin/env python3
"""ブラウザ管理.

ブラウザのライフサイクルを管理します。
my_lib.browser.BrowserManager をラップして price-watch 固有のインターフェースを提供します。

Page は `page()` スコープ内でのみ存在し、with を抜けるとタブごと閉じられます。
タブに紐づくリソース（CDP セッション・iframe・Route）はタブ単位でしか解放されないため、
スコープの単位は「1 アイテムのチェック」とし、巡回全体を 1 つのスコープで包まないこと。
"""

from __future__ import annotations

import contextlib
import logging
import pathlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import my_lib.browser
import my_lib.chrome_util

import price_watch.exceptions

if TYPE_CHECKING:
    from my_lib.browser import Page


PROFILE_NAME = "Default"


@dataclass
class BrowserManager:
    """ブラウザ管理クラス.

    ブラウザの起動、再起動、終了を管理します。
    内部で my_lib.browser.BrowserManager を使用します。
    """

    selenium_data_dir: pathlib.Path
    max_create_retries: int = 2

    # 内部状態
    _manager: my_lib.browser.BrowserManager | None = field(default=None, init=False, repr=False)

    def _get_or_create_manager(self) -> my_lib.browser.BrowserManager:
        """内部の BrowserManager を取得（必要に応じて作成）"""
        if self._manager is None:
            self._manager = my_lib.browser.BrowserManager(
                my_lib.browser.BrowserProfile(
                    name=PROFILE_NAME,
                    data_dir=self.selenium_data_dir,
                    # NOTE: 公開検索ページは bot 検出が無く headless で通るため headless 起動（Xvfb 不要）。
                    headless=True,
                ),
            )
        return self._manager

    @property
    def is_active(self) -> bool:
        """ブラウザがアクティブかどうかを確認.

        Returns:
            ブラウザが存在し、アクティブな場合 True
        """
        if self._manager is None:
            return False
        return self._manager.has_browser()

    def ensure_browser(self) -> None:
        """ブラウザを起動する（起動済みなら何もしない）.

        Raises:
            BrowserError: ブラウザの起動に失敗した場合
        """
        try:
            self._get_or_create_manager().get_browser()
        except my_lib.browser.BrowserError as e:
            raise price_watch.exceptions.BrowserError(f"Failed to create browser: {e}") from e

    @contextlib.contextmanager
    def page(self) -> Iterator[Page]:
        """新しいタブを開いて返し、with を抜けると閉じる.

        ブラウザが未起動なら起動します。

        Raises:
            BrowserError: ブラウザの起動に失敗した場合
        """
        try:
            cm = self._get_or_create_manager().page()
            page = cm.__enter__()
        except my_lib.browser.BrowserError as e:
            raise price_watch.exceptions.BrowserError(f"Failed to create browser: {e}") from e
        try:
            yield page
        finally:
            cm.__exit__(None, None, None)

    def restart(self) -> bool:
        """ブラウザを再起動.

        セッションエラー発生時にプロファイルを削除して再起動します。

        Returns:
            成功時 True
        """
        logging.warning("ブラウザを再起動します")

        try:
            self._get_or_create_manager().restart_with_clean_profile()
            return True
        except my_lib.browser.BrowserError:
            logging.exception("ブラウザの再起動に失敗しました")
            return False

    def quit(self) -> None:
        """ブラウザを終了."""
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
