#!/usr/bin/env python3
# ruff: noqa: S101
"""
cli/webui.py のユニットテスト

WebUI サーバーの実行を検証します。
"""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock, patch

import price_watch.cli.webui


class TestWebUIRunnerInit:
    """WebUIRunner の初期化テスト"""

    def test_initializes_with_defaults(self, tmp_path: pathlib.Path) -> None:
        """デフォルト値で初期化"""
        config_file = tmp_path / "config.yaml"

        runner = price_watch.cli.webui.WebUIRunner(config_file=config_file, port=5000)

        assert runner.config_file == config_file
        assert runner.port == 5000
        assert runner.debug_mode is False
        assert runner.server_handle is None
        assert runner.config is None

    def test_initializes_with_debug_mode(self, tmp_path: pathlib.Path) -> None:
        """デバッグモードで初期化"""
        config_file = tmp_path / "config.yaml"

        runner = price_watch.cli.webui.WebUIRunner(config_file=config_file, port=5001, debug_mode=True)

        assert runner.debug_mode is True


class TestWebUIRunnerStart:
    """WebUIRunner.start のテスト"""

    def test_starts_server(self, tmp_path: pathlib.Path) -> None:
        """サーバーを起動"""
        config_file = tmp_path / "config.yaml"
        static_dir = tmp_path / "static"
        static_dir.mkdir()

        mock_config = MagicMock()
        mock_config.webapp.static_dir_path = static_dir
        mock_config.data.price = tmp_path

        mock_handle = MagicMock()

        runner = price_watch.cli.webui.WebUIRunner(config_file=config_file, port=5000)

        with (
            patch("price_watch.config.load", return_value=mock_config),
            patch("price_watch.history.init"),
            patch("price_watch.webapi.server.start", return_value=mock_handle) as mock_start,
        ):
            runner.start()

        mock_start.assert_called_once_with(5000, static_dir_path=static_dir)
        assert runner.server_handle is mock_handle
        assert runner.config is mock_config

    def test_warns_if_static_dir_not_exists(self, tmp_path: pathlib.Path) -> None:
        """静的ファイルディレクトリがない場合は警告"""
        config_file = tmp_path / "config.yaml"
        static_dir = tmp_path / "nonexistent"

        mock_config = MagicMock()
        mock_config.webapp.static_dir_path = static_dir
        mock_config.data.price = tmp_path

        runner = price_watch.cli.webui.WebUIRunner(config_file=config_file, port=5000)

        with (
            patch("price_watch.config.load", return_value=mock_config),
            patch("price_watch.history.init"),
            patch("price_watch.webapi.server.start", return_value=MagicMock()),
        ):
            # 警告が出力されるがエラーにはならない
            runner.start()


class TestWebUIRunnerTerm:
    """WebUIRunner.term のテスト"""

    def test_stops_server(self, tmp_path: pathlib.Path) -> None:
        """サーバーを停止"""
        config_file = tmp_path / "config.yaml"
        mock_handle = MagicMock()

        runner = price_watch.cli.webui.WebUIRunner(config_file=config_file, port=5000)
        runner.server_handle = mock_handle

        with patch("price_watch.webapi.server.term") as mock_term:
            runner.term()

        mock_term.assert_called_once_with(mock_handle)
        assert runner.server_handle is None

    def test_does_nothing_if_no_handle(self, tmp_path: pathlib.Path) -> None:
        """ハンドルがない場合は何もしない"""
        config_file = tmp_path / "config.yaml"

        runner = price_watch.cli.webui.WebUIRunner(config_file=config_file, port=5000)

        with patch("price_watch.webapi.server.term") as mock_term:
            runner.term()

        mock_term.assert_not_called()


class TestWebUIRunnerRun:
    """WebUIRunner.run のテスト"""

    def test_starts_and_joins(self, tmp_path: pathlib.Path) -> None:
        """開始してスレッドを join"""
        config_file = tmp_path / "config.yaml"

        mock_thread = MagicMock()
        mock_handle = MagicMock()
        mock_handle.thread = mock_thread

        runner = price_watch.cli.webui.WebUIRunner(config_file=config_file, port=5000)

        with (
            patch.object(runner, "start") as mock_start,
            patch("signal.signal"),
        ):
            # start でハンドルを設定
            def set_handle() -> None:
                runner.server_handle = mock_handle

            mock_start.side_effect = set_handle

            # join がすぐに終了するようにする
            mock_thread.join.return_value = None

            runner.run()

        mock_start.assert_called_once()
        mock_thread.join.assert_called_once()


class TestMain:
    """main 関数のテスト"""

    def test_parses_args_and_runs(self) -> None:
        """引数をパースして実行"""
        mock_args = {
            "-c": "config.yaml",
            "-p": "5001",
            "-D": True,
        }

        mock_runner = MagicMock()

        with (
            patch("docopt.docopt", return_value=mock_args),
            patch("my_lib.logger.init"),
            patch("price_watch.cli.webui.WebUIRunner", return_value=mock_runner) as mock_runner_class,
        ):
            price_watch.cli.webui.main()

        mock_runner_class.assert_called_once_with(pathlib.Path("config.yaml"), 5001, debug_mode=True)
        mock_runner.run.assert_called_once()
