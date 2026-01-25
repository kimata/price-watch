#!/usr/bin/env python3
"""
価格履歴を WebUI で表示するサーバーです。

Usage:
  price-watch-webui [-c CONFIG] [-p PORT] [-D]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。[default: config.yaml]
  -p PORT           : Web サーバーを動作させるポートを指定します。[default: 5000]
  -D                : デバッグモードで動作します。
"""

from __future__ import annotations

import logging
import pathlib
import signal
import sys

import price_watch.config
import price_watch.history
import price_watch.webapi.server


class WebUIRunner:
    """WebUI サーバーの実行を管理するクラス."""

    def __init__(
        self,
        config_file: pathlib.Path,
        port: int,
        *,
        debug_mode: bool = False,
    ):
        """WebUIRunner を初期化.

        Args:
            config_file: 設定ファイルパス
            port: ポート番号
            debug_mode: デバッグモード
        """
        self.config_file = config_file
        self.port = port
        self.debug_mode = debug_mode
        self.server_handle: price_watch.webapi.server.ServerHandle | None = None
        self.config: price_watch.config.AppConfig | None = None

    def start(self) -> None:
        """サーバーを開始."""
        self.config = price_watch.config.load(self.config_file)
        static_dir_path = self.config.webapp.static_dir_path

        if not static_dir_path.exists():
            logging.warning("Static directory not found: %s", static_dir_path)
            logging.warning("Run 'cd frontend && npm run build' to build the frontend")

        # 設定ファイルのデータパスで history モジュールを初期化
        data_path = self.config.data.price
        db_file = data_path / "price_history.db"
        logging.info("Data path: %s (absolute: %s)", data_path, data_path.resolve())
        logging.info("DB file exists: %s", db_file.exists())
        price_watch.history.init(data_path)

        self.server_handle = price_watch.webapi.server.start(self.port, static_dir_path=static_dir_path)

    def term(self) -> None:
        """サーバーを停止."""
        if self.server_handle is not None:
            price_watch.webapi.server.term(self.server_handle)
            self.server_handle = None

    def run(self) -> None:
        """サーバーを実行（ブロッキング）."""

        # シグナルハンドラを設定
        def signal_handler(signum: int, frame: object) -> None:
            logging.info("Received signal %d, shutting down...", signum)
            self.term()
            sys.exit(0)

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        self.start()

        try:
            if self.server_handle is not None:
                self.server_handle.thread.join()
        except KeyboardInterrupt:
            logging.info("Received KeyboardInterrupt, shutting down...")
            self.term()


def main() -> None:
    """Console script entry point."""
    import docopt
    import my_lib.logger

    assert __doc__ is not None  # noqa: S101
    args = docopt.docopt(__doc__)

    config_file = pathlib.Path(args["-c"])
    port = int(args["-p"])
    debug_mode = args["-D"]

    my_lib.logger.init("price-watch-webui", level=logging.DEBUG if debug_mode else logging.INFO)

    logging.info("Using config: %s", config_file)

    runner = WebUIRunner(config_file, port, debug_mode=debug_mode)
    runner.run()


if __name__ == "__main__":
    main()
