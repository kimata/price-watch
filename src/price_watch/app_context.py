#!/usr/bin/env python3
"""アプリケーションコンテキスト.

全ての Manager を統合し、アプリケーションのライフサイクルを管理する
ファサードパターンの実装です。
"""

from __future__ import annotations

import logging
import pathlib
import signal
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import my_lib.footprint

import price_watch.exceptions
import price_watch.managers
import price_watch.thumbnail
import price_watch.webapi.server

if TYPE_CHECKING:
    from price_watch.config import AppConfig
    from price_watch.managers import (
        BrowserManager,
        ConfigManager,
        HistoryManager,
        MetricsManager,
    )
    from price_watch.target import ResolvedItem
    from price_watch.webapi.server import ServerHandle


@dataclass
class PriceWatchApp:
    """Price Watch アプリケーションコンテキスト.

    全ての Manager を統合し、依存関係を管理するファサードクラス。
    アプリケーションのライフサイクル（初期化、実行、終了）を一元管理します。
    """

    config_manager: ConfigManager
    history_manager: HistoryManager
    browser_manager: BrowserManager
    metrics_manager: MetricsManager
    port: int = 5000
    debug_mode: bool = False

    # 内部状態
    _server_handle: ServerHandle | None = field(default=None, init=False, repr=False)
    _should_terminate: threading.Event = field(default_factory=threading.Event, init=False)
    _received_signal: int | None = field(default=None, init=False)
    _initialized: bool = field(default=False, init=False)

    @classmethod
    def create(
        cls,
        config_file: pathlib.Path,
        target_file: pathlib.Path,
        port: int = 5000,
        *,
        debug_mode: bool = False,
    ) -> PriceWatchApp:
        """設定ファイルから PriceWatchApp を生成.

        Args:
            config_file: 設定ファイルパス
            target_file: ターゲット設定ファイルパス
            port: WebUI ポート番号
            debug_mode: デバッグモード

        Returns:
            PriceWatchApp インスタンス
        """
        # ConfigManager を作成して設定を読み込む
        config_manager = price_watch.managers.ConfigManager(
            config_file=config_file,
            target_file=target_file,
        )
        config = config_manager.config

        # 各 Manager を作成
        history_manager = price_watch.managers.HistoryManager(
            data_path=config.data.price,
        )
        browser_manager = price_watch.managers.BrowserManager(
            selenium_data_dir=config.data.selenium,
        )
        metrics_manager = price_watch.managers.MetricsManager(
            metrics_dir=config.data.metrics,
        )

        return cls(
            config_manager=config_manager,
            history_manager=history_manager,
            browser_manager=browser_manager,
            metrics_manager=metrics_manager,
            port=port,
            debug_mode=debug_mode,
        )

    @property
    def config(self) -> AppConfig:
        """アプリケーション設定を取得."""
        return self.config_manager.config

    @property
    def should_terminate(self) -> bool:
        """終了フラグを確認."""
        return self._should_terminate.is_set()

    def request_terminate(self) -> None:
        """終了をリクエスト."""
        self._should_terminate.set()

    def wait_for_terminate(self, timeout: float | None = None) -> bool:
        """終了リクエストを待機.

        Args:
            timeout: タイムアウト秒数

        Returns:
            終了リクエストがあれば True
        """
        return self._should_terminate.wait(timeout=timeout)

    def initialize(self) -> None:
        """アプリケーションを初期化.

        全ての Manager を初期化し、必要なリソースを準備します。

        Raises:
            PriceWatchError: 初期化に失敗した場合
        """
        if self._initialized:
            return

        try:
            logging.info("Initializing Price Watch application...")

            # 履歴 DB を初期化
            self.history_manager.initialize()

            # サムネイル保存ディレクトリを初期化
            price_watch.thumbnail.init(self.config.data.thumb)

            # メトリクス DB を初期化
            self.metrics_manager.initialize()

            self._initialized = True
            logging.info("Application initialized successfully")

        except Exception as e:
            raise price_watch.exceptions.PriceWatchError("Failed to initialize application") from e

    def setup_signal_handlers(self) -> None:
        """シグナルハンドラを設定."""

        def sig_handler(num: int, _frame: Any) -> None:
            # シグナルハンドラ内では logging を使わない（再入問題を避けるため）
            self._received_signal = num
            if num in (signal.SIGTERM, signal.SIGINT):
                self._should_terminate.set()

        signal.signal(signal.SIGTERM, sig_handler)
        signal.signal(signal.SIGINT, sig_handler)

    def start_webui_server(self) -> None:
        """WebUI サーバーを起動."""
        static_dir_path = self.config.webapp.static_dir_path

        if not static_dir_path.exists():
            logging.warning("Static directory not found: %s", static_dir_path)
            logging.warning("Run 'cd frontend && npm run build' to build the frontend")

        self._server_handle = price_watch.webapi.server.start(self.port, static_dir_path=static_dir_path)
        logging.info("WebUI server started on port %d", self.port)

    def stop_webui_server(self) -> None:
        """WebUI サーバーを停止."""
        if self._server_handle is not None:
            price_watch.webapi.server.term(self._server_handle)
            self._server_handle = None

    def update_liveness(self) -> None:
        """Liveness を更新."""
        my_lib.footprint.update(self.config.liveness.file.crawler)
        self.metrics_manager.update_heartbeat()

    def get_resolved_items(self) -> list[ResolvedItem]:
        """解決済みアイテムリストを取得.

        ターゲット設定を再読み込みしてから解決します。

        Returns:
            解決済みアイテムのリスト
        """
        return self.config_manager.get_resolved_items()

    def shutdown(self) -> None:
        """アプリケーションを終了.

        全てのリソースをクリーンアップします。
        """
        logging.info("Shutting down Price Watch application...")

        # シグナル受信をログ出力
        if self._received_signal is not None:
            logging.warning("Received signal %d", self._received_signal)

        # WebUI サーバーを停止
        self.stop_webui_server()

        # ブラウザを終了
        self.browser_manager.quit()
        self.browser_manager.cleanup_profile_lock()

        logging.info("Application shutdown complete")

    def __enter__(self) -> PriceWatchApp:
        """コンテキストマネージャーのエントリポイント."""
        self.initialize()
        return self

    def __exit__(
        self,
        _exc_type: type | None,
        _exc_val: Exception | None,
        _exc_tb: object,
    ) -> None:
        """コンテキストマネージャーの終了処理."""
        self.shutdown()
