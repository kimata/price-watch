#!/usr/bin/env python3
# ruff: noqa: S101
"""
cli/app.py のユニットテスト

価格監視アプリケーションの実行ロジックを検証します。
"""

from __future__ import annotations

import pathlib
import time
from unittest.mock import MagicMock, patch

import pytest

import price_watch.cli.app
from price_watch.target import CheckMethod, ResolvedItem


def _create_resolved_item(
    name: str = "Test",
    store: str = "test-store.com",
    url: str = "https://example.com/item",
    check_method: CheckMethod = CheckMethod.SCRAPE,
    search_keyword: str | None = None,
) -> ResolvedItem:
    """テスト用の ResolvedItem を作成."""
    return ResolvedItem(
        name=name,
        store=store,
        url=url,
        check_method=check_method,
        search_keyword=search_keyword,
    )


class TestAppRunnerProcessor:
    """AppRunner.processor プロパティのテスト"""

    def test_lazy_initializes_processor(self) -> None:
        """processor を遅延初期化"""
        mock_app = MagicMock()

        runner = price_watch.cli.app.AppRunner(app=mock_app)

        with patch("price_watch.processor.ItemProcessor") as mock_processor_class:
            mock_processor = MagicMock()
            mock_processor_class.return_value = mock_processor

            result = runner.processor

        assert result is mock_processor

    def test_returns_cached_processor(self) -> None:
        """キャッシュされた processor を返す"""
        mock_app = MagicMock()
        mock_processor = MagicMock()

        runner = price_watch.cli.app.AppRunner(app=mock_app)
        runner._processor = mock_processor

        result = runner.processor

        assert result is mock_processor


class TestAppRunnerExecute:
    """AppRunner.execute のテスト"""

    def test_execute_initializes_app(self) -> None:
        """execute で app を初期化"""
        mock_app = MagicMock()
        mock_app.debug_mode = True
        mock_app.should_terminate = False

        runner = price_watch.cli.app.AppRunner(app=mock_app)

        with patch.object(runner, "_execute_debug_mode", return_value=True):
            result = runner.execute()

        mock_app.initialize.assert_called_once()
        mock_app.browser_manager.ensure_driver.assert_called_once()
        assert result is True

    def test_execute_returns_false_on_init_error(self) -> None:
        """初期化エラー時は False を返す"""
        mock_app = MagicMock()
        mock_app.initialize.side_effect = Exception("Init failed")

        runner = price_watch.cli.app.AppRunner(app=mock_app)

        result = runner.execute()

        assert result is False

    def test_execute_calls_debug_mode(self) -> None:
        """デバッグモードの場合 _execute_debug_mode を呼ぶ"""
        mock_app = MagicMock()
        mock_app.debug_mode = True

        runner = price_watch.cli.app.AppRunner(app=mock_app)

        with patch.object(runner, "_execute_debug_mode", return_value=True) as mock_debug:
            runner.execute()

        mock_debug.assert_called_once()

    def test_execute_calls_main_loop(self) -> None:
        """通常モードの場合 _execute_main_loop を呼ぶ"""
        mock_app = MagicMock()
        mock_app.debug_mode = False

        runner = price_watch.cli.app.AppRunner(app=mock_app)

        with patch.object(runner, "_execute_main_loop", return_value=True) as mock_loop:
            runner.execute()

        mock_loop.assert_called_once()


class TestAppRunnerExecuteDebugMode:
    """AppRunner._execute_debug_mode のテスト"""

    def test_runs_once_and_shuts_down(self) -> None:
        """1回実行してシャットダウン"""
        mock_app = MagicMock()
        mock_processor = MagicMock()
        mock_processor.check_debug_results.return_value = True

        runner = price_watch.cli.app.AppRunner(app=mock_app)
        runner._processor = mock_processor

        with patch.object(runner, "_do_work"):
            result = runner._execute_debug_mode()

        mock_app.metrics_manager.start_session.assert_called_once()
        mock_app.metrics_manager.end_session.assert_called_once_with("normal")
        mock_app.shutdown.assert_called_once()
        assert result is True


class TestAppRunnerExecuteMainLoop:
    """AppRunner._execute_main_loop のテスト"""

    def test_terminates_when_requested(self) -> None:
        """終了リクエスト時にループを抜ける"""
        mock_app = MagicMock()
        mock_app.should_terminate = True

        runner = price_watch.cli.app.AppRunner(app=mock_app)

        result = runner._execute_main_loop()

        mock_app.metrics_manager.end_session.assert_called_once_with("terminated")
        mock_app.shutdown.assert_called_once()
        assert result is True


class TestAppRunnerDoWork:
    """AppRunner._do_work のテスト"""

    def test_loads_and_processes_items(self) -> None:
        """アイテムを読み込んで処理"""
        mock_app = MagicMock()
        mock_processor = MagicMock()

        runner = price_watch.cli.app.AppRunner(app=mock_app)
        runner._processor = mock_processor

        mock_items = [_create_resolved_item(name="Item1")]
        with patch.object(runner, "_load_item_list", return_value=mock_items):
            runner._do_work()

        mock_processor.process_all.assert_called_once_with(mock_items)


class TestAppRunnerLoadItemList:
    """AppRunner._load_item_list のテスト"""

    def test_loads_and_converts_items(self) -> None:
        """アイテムを読み込んで変換"""
        mock_app = MagicMock()
        mock_item = _create_resolved_item(
            name="Item1",
            check_method=CheckMethod.SCRAPE,
            url="http://example.com",
        )
        mock_app.get_resolved_items.return_value = [mock_item]

        mock_processor = MagicMock()
        mock_processor.error_count = {}

        runner = price_watch.cli.app.AppRunner(app=mock_app)
        runner._processor = mock_processor

        result = runner._load_item_list()

        assert len(result) == 1
        assert result[0].name == "Item1"

    def test_handles_mercari_search(self) -> None:
        """メルカリ検索アイテムを処理"""
        mock_app = MagicMock()
        mock_item = _create_resolved_item(
            name="Item1",
            check_method=CheckMethod.MERCARI_SEARCH,
            search_keyword="keyword",
            url="",
        )
        mock_app.get_resolved_items.return_value = [mock_item]

        mock_processor = MagicMock()
        mock_processor.error_count = {}

        runner = price_watch.cli.app.AppRunner(app=mock_app)
        runner._processor = mock_processor

        with patch("price_watch.history.generate_item_key", return_value="mercari_key"):
            result = runner._load_item_list()

        assert len(result) == 1
        assert result[0].search_keyword == "keyword"


class TestAppRunnerSleepUntil:
    """AppRunner._sleep_until のテスト"""

    def test_returns_if_already_past(self) -> None:
        """既に過ぎている場合は即座に返る"""
        mock_app = MagicMock()
        mock_app.should_terminate = False
        mock_app.wait_for_terminate.return_value = False

        runner = price_watch.cli.app.AppRunner(app=mock_app)

        # 過去の時刻を指定
        runner._sleep_until(time.time() - 1)

        # update_liveness は呼ばれるが、すぐに終了
        mock_app.update_liveness.assert_called()

    def test_returns_on_terminate(self) -> None:
        """終了リクエスト時に返る"""
        mock_app = MagicMock()
        mock_app.should_terminate = True

        runner = price_watch.cli.app.AppRunner(app=mock_app)

        runner._sleep_until(time.time() + 100)

        mock_app.update_liveness.assert_called_once()


class TestRun:
    """run 関数のテスト"""

    def test_creates_and_runs_app(self, tmp_path: pathlib.Path) -> None:
        """アプリを作成して実行"""
        config_file = tmp_path / "config.yaml"
        target_file = tmp_path / "target.yaml"

        mock_app = MagicMock()

        with (
            patch("price_watch.app_context.PriceWatchApp.create", return_value=mock_app),
            patch("price_watch.cli.app.AppRunner") as mock_runner_class,
            pytest.raises(SystemExit),  # sys.exit を捕捉
        ):
            mock_runner = MagicMock()
            mock_runner.execute.return_value = True
            mock_runner_class.return_value = mock_runner

            price_watch.cli.app.run(config_file, target_file, 5000, debug_mode=True)

        mock_app.setup_signal_handlers.assert_called_once()

    def test_does_not_start_webui_in_debug_mode(self, tmp_path: pathlib.Path) -> None:
        """デバッグモードでは WebUI を起動しない"""
        config_file = tmp_path / "config.yaml"
        target_file = tmp_path / "target.yaml"

        mock_app = MagicMock()

        with (
            patch("price_watch.app_context.PriceWatchApp.create", return_value=mock_app),
            patch("price_watch.cli.app.AppRunner") as mock_runner_class,
            pytest.raises(SystemExit),
        ):
            mock_runner = MagicMock()
            mock_runner.execute.return_value = True
            mock_runner_class.return_value = mock_runner

            price_watch.cli.app.run(config_file, target_file, 5000, debug_mode=True)

        mock_app.start_webui_server.assert_not_called()

    def test_starts_webui_in_normal_mode(self, tmp_path: pathlib.Path) -> None:
        """通常モードでは WebUI を起動"""
        config_file = tmp_path / "config.yaml"
        target_file = tmp_path / "target.yaml"

        mock_app = MagicMock()

        with (
            patch("price_watch.app_context.PriceWatchApp.create", return_value=mock_app),
            patch("price_watch.cli.app.AppRunner") as mock_runner_class,
            pytest.raises(SystemExit),
        ):
            mock_runner = MagicMock()
            mock_runner.execute.return_value = True
            mock_runner_class.return_value = mock_runner

            price_watch.cli.app.run(config_file, target_file, 5000, debug_mode=False)

        mock_app.start_webui_server.assert_called_once()


class TestMain:
    """main 関数のテスト"""

    def test_parses_args_and_runs(self) -> None:
        """引数をパースして実行"""
        mock_args = {
            "-c": "config.yaml",
            "-t": "target.yaml",
            "-p": "5001",
            "-D": True,
        }

        with (
            patch("docopt.docopt", return_value=mock_args),
            patch("my_lib.logger.init"),
            patch("price_watch.cli.app.run") as mock_run,
        ):
            price_watch.cli.app.main()

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == pathlib.Path("config.yaml")
        assert call_args[0][1] == pathlib.Path("target.yaml")
        assert call_args[0][2] == 5001
        assert call_args[1]["debug_mode"] is True
