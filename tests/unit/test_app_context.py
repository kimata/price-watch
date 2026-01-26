#!/usr/bin/env python3
# ruff: noqa: S101, S108
"""
app_context.py のユニットテスト

アプリケーションコンテキストを検証します。
"""

from __future__ import annotations

import pathlib
import signal
from unittest.mock import MagicMock, patch

import pytest

import price_watch.app_context
import price_watch.exceptions


class TestPriceWatchAppCreate:
    """PriceWatchApp.create のテスト"""

    def test_creates_app_from_config(self, tmp_path: pathlib.Path) -> None:
        """設定ファイルからアプリを作成"""
        config_file = tmp_path / "config.yaml"
        target_file = tmp_path / "target.yaml"

        mock_config = MagicMock()
        mock_config.data.price = tmp_path / "price"
        mock_config.data.selenium = tmp_path / "selenium"
        mock_config.data.metrics = tmp_path / "metrics"

        with patch("price_watch.managers.ConfigManager") as mock_config_manager_class:
            mock_config_manager = MagicMock()
            mock_config_manager.config = mock_config
            mock_config_manager_class.return_value = mock_config_manager

            app = price_watch.app_context.PriceWatchApp.create(
                config_file, target_file, port=5001, debug_mode=True
            )

        assert app.port == 5001
        assert app.debug_mode is True


class TestPriceWatchAppProperties:
    """PriceWatchApp のプロパティテスト"""

    def test_config_returns_config_manager_config(self) -> None:
        """config は config_manager の config を返す"""
        mock_config_manager = MagicMock()
        mock_config = MagicMock()
        mock_config_manager.config = mock_config

        app = price_watch.app_context.PriceWatchApp(
            config_manager=mock_config_manager,
            history_manager=MagicMock(),
            browser_manager=MagicMock(),
            metrics_manager=MagicMock(),
        )

        assert app.config is mock_config

    def test_should_terminate_returns_false_initially(self) -> None:
        """初期状態では should_terminate は False"""
        app = price_watch.app_context.PriceWatchApp(
            config_manager=MagicMock(),
            history_manager=MagicMock(),
            browser_manager=MagicMock(),
            metrics_manager=MagicMock(),
        )

        assert app.should_terminate is False


class TestRequestTerminate:
    """request_terminate メソッドのテスト"""

    def test_sets_terminate_flag(self) -> None:
        """終了フラグを設定"""
        app = price_watch.app_context.PriceWatchApp(
            config_manager=MagicMock(),
            history_manager=MagicMock(),
            browser_manager=MagicMock(),
            metrics_manager=MagicMock(),
        )

        app.request_terminate()

        assert app.should_terminate is True


class TestWaitForTerminate:
    """wait_for_terminate メソッドのテスト"""

    def test_returns_false_without_terminate(self) -> None:
        """終了リクエストがなければ False"""
        app = price_watch.app_context.PriceWatchApp(
            config_manager=MagicMock(),
            history_manager=MagicMock(),
            browser_manager=MagicMock(),
            metrics_manager=MagicMock(),
        )

        result = app.wait_for_terminate(timeout=0.01)

        assert result is False

    def test_returns_true_with_terminate(self) -> None:
        """終了リクエストがあれば True"""
        app = price_watch.app_context.PriceWatchApp(
            config_manager=MagicMock(),
            history_manager=MagicMock(),
            browser_manager=MagicMock(),
            metrics_manager=MagicMock(),
        )
        app.request_terminate()

        result = app.wait_for_terminate(timeout=0.01)

        assert result is True


class TestInitialize:
    """initialize メソッドのテスト"""

    def test_initializes_all_managers(self) -> None:
        """全マネージャーを初期化"""
        mock_config_manager = MagicMock()
        mock_config = MagicMock()
        mock_config.data.thumb = pathlib.Path("/tmp/thumb")
        mock_config_manager.config = mock_config
        mock_history_manager = MagicMock()
        mock_metrics_manager = MagicMock()

        app = price_watch.app_context.PriceWatchApp(
            config_manager=mock_config_manager,
            history_manager=mock_history_manager,
            browser_manager=MagicMock(),
            metrics_manager=mock_metrics_manager,
        )

        with patch("price_watch.thumbnail.init"):
            app.initialize()

        mock_history_manager.initialize.assert_called_once()
        mock_metrics_manager.initialize.assert_called_once()

    def test_initialize_idempotent(self) -> None:
        """initialize は冪等"""
        mock_config_manager = MagicMock()
        mock_config = MagicMock()
        mock_config.data.thumb = pathlib.Path("/tmp/thumb")
        mock_config_manager.config = mock_config
        mock_history_manager = MagicMock()

        app = price_watch.app_context.PriceWatchApp(
            config_manager=mock_config_manager,
            history_manager=mock_history_manager,
            browser_manager=MagicMock(),
            metrics_manager=MagicMock(),
        )

        with patch("price_watch.thumbnail.init"):
            app.initialize()
            app.initialize()

        mock_history_manager.initialize.assert_called_once()

    def test_raises_on_error(self) -> None:
        """初期化エラー時は例外を raise"""
        mock_config_manager = MagicMock()
        mock_config = MagicMock()
        mock_config.data.thumb = pathlib.Path("/tmp/thumb")
        mock_config_manager.config = mock_config
        mock_history_manager = MagicMock()
        mock_history_manager.initialize.side_effect = Exception("Failed")

        app = price_watch.app_context.PriceWatchApp(
            config_manager=mock_config_manager,
            history_manager=mock_history_manager,
            browser_manager=MagicMock(),
            metrics_manager=MagicMock(),
        )

        with pytest.raises(price_watch.exceptions.PriceWatchError):
            app.initialize()


class TestSetupSignalHandlers:
    """setup_signal_handlers メソッドのテスト"""

    def test_sets_up_handlers(self) -> None:
        """シグナルハンドラを設定"""
        app = price_watch.app_context.PriceWatchApp(
            config_manager=MagicMock(),
            history_manager=MagicMock(),
            browser_manager=MagicMock(),
            metrics_manager=MagicMock(),
        )

        with patch("signal.signal") as mock_signal:
            app.setup_signal_handlers()

        assert mock_signal.call_count >= 2


class TestStartWebuiServer:
    """start_webui_server メソッドのテスト"""

    def test_starts_server(self) -> None:
        """サーバーを起動"""
        mock_config_manager = MagicMock()
        mock_config = MagicMock()
        mock_config.webapp.static_dir_path = pathlib.Path("/tmp/static")
        mock_config_manager.config = mock_config

        app = price_watch.app_context.PriceWatchApp(
            config_manager=mock_config_manager,
            history_manager=MagicMock(),
            browser_manager=MagicMock(),
            metrics_manager=MagicMock(),
            port=5001,
        )

        mock_handle = MagicMock()
        with patch("price_watch.webapi.server.start", return_value=mock_handle) as mock_start:
            app.start_webui_server()

        mock_start.assert_called_once()
        assert app._server_handle is mock_handle

    def test_warns_if_static_not_found(self, tmp_path: pathlib.Path) -> None:
        """静的ファイルディレクトリがない場合は警告"""
        mock_config_manager = MagicMock()
        mock_config = MagicMock()
        mock_config.webapp.static_dir_path = tmp_path / "nonexistent"
        mock_config_manager.config = mock_config

        app = price_watch.app_context.PriceWatchApp(
            config_manager=mock_config_manager,
            history_manager=MagicMock(),
            browser_manager=MagicMock(),
            metrics_manager=MagicMock(),
        )

        with patch("price_watch.webapi.server.start", return_value=MagicMock()):
            app.start_webui_server()
        # 警告がログされる（エラーにはならない）


class TestStopWebuiServer:
    """stop_webui_server メソッドのテスト"""

    def test_stops_server(self) -> None:
        """サーバーを停止"""
        app = price_watch.app_context.PriceWatchApp(
            config_manager=MagicMock(),
            history_manager=MagicMock(),
            browser_manager=MagicMock(),
            metrics_manager=MagicMock(),
        )
        mock_handle = MagicMock()
        app._server_handle = mock_handle

        with patch("price_watch.webapi.server.term") as mock_term:
            app.stop_webui_server()

        mock_term.assert_called_once_with(mock_handle)
        assert app._server_handle is None

    def test_does_nothing_if_no_server(self) -> None:
        """サーバーがない場合は何もしない"""
        app = price_watch.app_context.PriceWatchApp(
            config_manager=MagicMock(),
            history_manager=MagicMock(),
            browser_manager=MagicMock(),
            metrics_manager=MagicMock(),
        )

        with patch("price_watch.webapi.server.term") as mock_term:
            app.stop_webui_server()

        mock_term.assert_not_called()


class TestUpdateLiveness:
    """update_liveness メソッドのテスト"""

    def test_updates_footprint_and_heartbeat(self) -> None:
        """フットプリントとハートビートを更新"""
        mock_config_manager = MagicMock()
        mock_config = MagicMock()
        mock_config.liveness.file.crawler = pathlib.Path("/dev/shm/healthz")
        mock_config_manager.config = mock_config
        mock_metrics_manager = MagicMock()

        app = price_watch.app_context.PriceWatchApp(
            config_manager=mock_config_manager,
            history_manager=MagicMock(),
            browser_manager=MagicMock(),
            metrics_manager=mock_metrics_manager,
        )

        with patch("my_lib.footprint.update") as mock_footprint:
            app.update_liveness()

        mock_footprint.assert_called_once()
        mock_metrics_manager.update_heartbeat.assert_called_once()


class TestGetResolvedItems:
    """get_resolved_items メソッドのテスト"""

    def test_returns_resolved_items(self) -> None:
        """解決済みアイテムを返す"""
        mock_config_manager = MagicMock()
        mock_items = [MagicMock(), MagicMock()]
        mock_config_manager.get_resolved_items.return_value = mock_items

        app = price_watch.app_context.PriceWatchApp(
            config_manager=mock_config_manager,
            history_manager=MagicMock(),
            browser_manager=MagicMock(),
            metrics_manager=MagicMock(),
        )

        result = app.get_resolved_items()

        assert result == mock_items


class TestShutdown:
    """shutdown メソッドのテスト"""

    def test_cleans_up_all_resources(self) -> None:
        """全リソースをクリーンアップ"""
        mock_browser_manager = MagicMock()
        app = price_watch.app_context.PriceWatchApp(
            config_manager=MagicMock(),
            history_manager=MagicMock(),
            browser_manager=mock_browser_manager,
            metrics_manager=MagicMock(),
        )
        mock_handle = MagicMock()
        app._server_handle = mock_handle

        with patch("price_watch.webapi.server.term"):
            app.shutdown()

        mock_browser_manager.quit.assert_called_once()
        mock_browser_manager.cleanup_profile_lock.assert_called_once()

    def test_logs_received_signal(self) -> None:
        """受信シグナルをログ出力"""
        app = price_watch.app_context.PriceWatchApp(
            config_manager=MagicMock(),
            history_manager=MagicMock(),
            browser_manager=MagicMock(),
            metrics_manager=MagicMock(),
        )
        app._received_signal = signal.SIGTERM

        app.shutdown()
        # シグナルがログされる（エラーにはならない）


class TestContextManager:
    """コンテキストマネージャーのテスト"""

    def test_enter_initializes(self) -> None:
        """__enter__ で初期化"""
        mock_config_manager = MagicMock()
        mock_config = MagicMock()
        mock_config.data.thumb = pathlib.Path("/tmp/thumb")
        mock_config_manager.config = mock_config

        app = price_watch.app_context.PriceWatchApp(
            config_manager=mock_config_manager,
            history_manager=MagicMock(),
            browser_manager=MagicMock(),
            metrics_manager=MagicMock(),
        )

        with patch("price_watch.thumbnail.init"), app as ctx:
            assert ctx is app
            assert app._initialized is True

    def test_exit_shuts_down(self) -> None:
        """__exit__ で終了処理"""
        mock_config_manager = MagicMock()
        mock_config = MagicMock()
        mock_config.data.thumb = pathlib.Path("/tmp/thumb")
        mock_config_manager.config = mock_config
        mock_browser_manager = MagicMock()

        app = price_watch.app_context.PriceWatchApp(
            config_manager=mock_config_manager,
            history_manager=MagicMock(),
            browser_manager=mock_browser_manager,
            metrics_manager=MagicMock(),
        )

        with patch("price_watch.thumbnail.init"), app:
            pass

        mock_browser_manager.quit.assert_called_once()
