#!/usr/bin/env python3
# ruff: noqa: S101
"""
webapi/server.py のユニットテスト

Web API サーバーの作成・起動・停止を検証します。
"""

from __future__ import annotations

import pathlib
import threading
from unittest.mock import MagicMock, patch

import flask

import price_watch.webapi.server


class TestGetCorsOrigins:
    """_get_cors_origins 関数のテスト"""

    def test_with_valid_external_url(self):
        """有効な external_url から正しいオリジンを抽出"""
        result = price_watch.webapi.server._get_cors_origins("https://example.com/price/")

        assert result == ["https://example.com"]

    def test_with_external_url_no_path(self):
        """パスなしの external_url"""
        result = price_watch.webapi.server._get_cors_origins("https://example.com")

        assert result == ["https://example.com"]

    def test_with_external_url_with_port(self):
        """ポート指定付きの external_url"""
        result = price_watch.webapi.server._get_cors_origins("https://example.com:8443/app/")

        assert result == ["https://example.com:8443"]

    def test_with_http_url(self):
        """HTTP スキームの external_url"""
        result = price_watch.webapi.server._get_cors_origins("http://localhost:5000/price/")

        assert result == ["http://localhost:5000"]

    def test_with_none(self):
        """external_url が None の場合は全許可"""
        result = price_watch.webapi.server._get_cors_origins(None)

        assert result == "*"

    def test_with_empty_string(self):
        """external_url が空文字の場合は全許可"""
        result = price_watch.webapi.server._get_cors_origins("")

        assert result == "*"

    def test_with_invalid_url_no_scheme(self):
        """スキームなしの不正な URL"""
        result = price_watch.webapi.server._get_cors_origins("example.com/price/")

        assert result == "*"

    def test_with_invalid_url_no_netloc(self):
        """ホストなしの不正な URL"""
        result = price_watch.webapi.server._get_cors_origins("/price/")

        assert result == "*"


class TestCreateApp:
    """create_app 関数のテスト"""

    def test_create_app_basic(self, tmp_path: pathlib.Path):
        """基本的なアプリ作成"""
        static_dir = tmp_path / "static"
        static_dir.mkdir()

        mock_config = MagicMock()
        mock_config.webapp.external_url = None

        with patch("price_watch.webapi.cache.get_app_config", return_value=mock_config):
            app = price_watch.webapi.server.create_app(static_dir_path=static_dir)

        assert app is not None
        assert isinstance(app, flask.Flask)
        assert app.name == "price_watch_webui"

    def test_create_app_without_static_dir(self, tmp_path: pathlib.Path):
        """静的ディレクトリが存在しない場合"""
        static_dir = tmp_path / "nonexistent"

        mock_config = MagicMock()
        mock_config.webapp.external_url = None

        with patch("price_watch.webapi.cache.get_app_config", return_value=mock_config):
            app = price_watch.webapi.server.create_app(static_dir_path=static_dir)

        assert app is not None
        assert isinstance(app, flask.Flask)

    def test_create_app_with_existing_static_dir(self, tmp_path: pathlib.Path):
        """静的ディレクトリが存在する場合"""
        static_dir = tmp_path / "static"
        static_dir.mkdir()
        (static_dir / "index.html").write_text("<html></html>")

        mock_config = MagicMock()
        mock_config.webapp.external_url = None

        with patch("price_watch.webapi.cache.get_app_config", return_value=mock_config):
            app = price_watch.webapi.server.create_app(static_dir_path=static_dir)

        assert app is not None
        # 静的ファイルのブループリントが登録されていることを確認
        assert "webapp-base" in [bp.name for bp in app.iter_blueprints()]


class TestServerHandle:
    """ServerHandle クラスのテスト"""

    def test_dataclass_fields(self):
        """データクラスフィールドの確認"""
        mock_server = MagicMock()
        mock_thread = MagicMock(spec=threading.Thread)

        handle = price_watch.webapi.server.ServerHandle(
            server=mock_server,
            thread=mock_thread,
        )

        assert handle.server is mock_server
        assert handle.thread is mock_thread


class TestServerStart:
    """start 関数のテスト"""

    def test_start_server(self, tmp_path: pathlib.Path):
        """サーバー起動"""
        static_dir = tmp_path / "static"
        static_dir.mkdir()

        mock_server = MagicMock()
        mock_thread = MagicMock(spec=threading.Thread)
        mock_config = MagicMock()
        mock_config.webapp.external_url = None

        with (
            patch("price_watch.webapi.cache.get_app_config", return_value=mock_config),
            patch("price_watch.webapi.cache.start_file_watcher"),
            patch("werkzeug.serving.make_server", return_value=mock_server),
            patch("threading.Thread", return_value=mock_thread) as mock_thread_class,
        ):
            handle = price_watch.webapi.server.start(port=5000, static_dir_path=static_dir)

        assert handle is not None
        assert handle.server is mock_server
        mock_thread.start.assert_called_once()
        mock_thread_class.assert_called_once()

    def test_start_server_with_port(self, tmp_path: pathlib.Path):
        """指定ポートでサーバー起動"""
        static_dir = tmp_path / "static"
        static_dir.mkdir()

        mock_server = MagicMock()
        mock_thread = MagicMock(spec=threading.Thread)
        mock_config = MagicMock()
        mock_config.webapp.external_url = None

        with (
            patch("price_watch.webapi.cache.get_app_config", return_value=mock_config),
            patch("price_watch.webapi.cache.start_file_watcher"),
            patch("werkzeug.serving.make_server", return_value=mock_server) as mock_make_server,
            patch("threading.Thread", return_value=mock_thread),
        ):
            price_watch.webapi.server.start(port=8080, static_dir_path=static_dir)

        # 指定したポートが使われていることを確認
        call_args = mock_make_server.call_args
        assert call_args[0][1] == 8080


class TestServerTerm:
    """term 関数のテスト"""

    def test_term_server_success(self):
        """サーバー正常終了"""
        mock_server = MagicMock()
        mock_thread = MagicMock(spec=threading.Thread)
        mock_thread.is_alive.return_value = False

        handle = price_watch.webapi.server.ServerHandle(
            server=mock_server,
            thread=mock_thread,
        )

        price_watch.webapi.server.term(handle)

        mock_server.shutdown.assert_called_once()
        mock_server.server_close.assert_called_once()
        mock_thread.join.assert_called_once_with(timeout=10)

    def test_term_server_timeout(self):
        """サーバー終了タイムアウト"""
        mock_server = MagicMock()
        mock_thread = MagicMock(spec=threading.Thread)
        mock_thread.is_alive.return_value = True  # タイムアウト

        handle = price_watch.webapi.server.ServerHandle(
            server=mock_server,
            thread=mock_thread,
        )

        with patch("logging.error") as mock_error:
            price_watch.webapi.server.term(handle)

        mock_error.assert_called_once()
        assert "timeout" in mock_error.call_args[0][0].lower()


class TestMain:
    """main 関数のテスト"""

    def test_main_keyboard_interrupt(self, tmp_path: pathlib.Path):
        """KeyboardInterrupt での終了"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
data:
  price: /tmp/price
  thumb: /tmp/thumb
  metrics: /tmp/metrics
webapp:
  static_dir_path: /tmp/static
edit:
  password_hash: "$2b$12$test_hash"
"""
        )

        mock_args = {
            "-c": str(config_file),
            "-p": "5000",
            "-D": False,
        }

        mock_server = MagicMock()
        mock_thread = MagicMock(spec=threading.Thread)
        mock_thread.join.side_effect = KeyboardInterrupt

        mock_config = MagicMock()
        mock_config.webapp.external_url = None

        with (
            patch("docopt.docopt", return_value=mock_args),
            patch("my_lib.logger.init"),
            patch("price_watch.webapi.cache.get_app_config", return_value=mock_config),
            patch("price_watch.webapi.cache.start_file_watcher"),
            patch("werkzeug.serving.make_server", return_value=mock_server),
            patch("threading.Thread", return_value=mock_thread),
            patch.object(price_watch.webapi.server, "term") as mock_term,
        ):
            price_watch.webapi.server.main()

        mock_term.assert_called_once()

    def test_main_with_debug_mode(self, tmp_path: pathlib.Path):
        """デバッグモードでの起動"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
data:
  price: /tmp/price
  thumb: /tmp/thumb
  metrics: /tmp/metrics
webapp:
  static_dir_path: /tmp/static
edit:
  password_hash: "$2b$12$test_hash"
"""
        )

        mock_args = {
            "-c": str(config_file),
            "-p": "5000",
            "-D": True,
        }

        mock_server = MagicMock()
        mock_thread = MagicMock(spec=threading.Thread)
        mock_thread.join.side_effect = KeyboardInterrupt

        mock_config = MagicMock()
        mock_config.webapp.external_url = None

        with (
            patch("docopt.docopt", return_value=mock_args),
            patch("my_lib.logger.init") as mock_logger_init,
            patch("price_watch.webapi.cache.get_app_config", return_value=mock_config),
            patch("price_watch.webapi.cache.start_file_watcher"),
            patch("werkzeug.serving.make_server", return_value=mock_server),
            patch("threading.Thread", return_value=mock_thread),
            patch.object(price_watch.webapi.server, "term"),
        ):
            import logging

            price_watch.webapi.server.main()

        # デバッグレベルで初期化されていることを確認
        mock_logger_init.assert_called_once()
        call_args = mock_logger_init.call_args
        assert call_args.kwargs.get("level") == logging.DEBUG or call_args[1].get("level") == logging.DEBUG

    def test_main_missing_static_dir_warning(self, tmp_path: pathlib.Path):
        """静的ディレクトリがない場合の警告"""
        nonexistent_static = tmp_path / "nonexistent_static"
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            f"""
data:
  price: /tmp/price
  thumb: /tmp/thumb
  metrics: /tmp/metrics
webapp:
  static_dir_path: {nonexistent_static}
edit:
  password_hash: "$2b$12$test_hash"
"""
        )

        mock_args = {
            "-c": str(config_file),
            "-p": "5000",
            "-D": False,
        }

        mock_server = MagicMock()
        mock_thread = MagicMock(spec=threading.Thread)
        mock_thread.join.side_effect = KeyboardInterrupt

        mock_config = MagicMock()
        mock_config.webapp.external_url = None

        with (
            patch("docopt.docopt", return_value=mock_args),
            patch("my_lib.logger.init"),
            patch("logging.warning") as mock_warning,
            patch("price_watch.webapi.cache.get_app_config", return_value=mock_config),
            patch("price_watch.webapi.cache.start_file_watcher"),
            patch("werkzeug.serving.make_server", return_value=mock_server),
            patch("threading.Thread", return_value=mock_thread),
            patch.object(price_watch.webapi.server, "term"),
        ):
            price_watch.webapi.server.main()

        # 警告が出力されていることを確認
        assert mock_warning.call_count >= 1
