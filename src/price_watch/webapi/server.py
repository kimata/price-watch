#!/usr/bin/env python3
"""
価格履歴を WebUI で提供します。

Usage:
  server.py [-c CONFIG] [-p PORT] [-D]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。[default: config.yaml]
  -p PORT           : Web サーバーを動作させるポートを指定します。[default: 5000]
  -D                : デバッグモードで動作します。
"""

import logging
import pathlib
import threading
from dataclasses import dataclass

import flask
import flask_cors
import my_lib.webapp.base
import my_lib.webapp.config
import my_lib.webapp.event
import my_lib.webapp.util
import werkzeug.serving

URL_PREFIX = "/price"


@dataclass
class ServerHandle:
    """サーバーハンドル."""

    server: werkzeug.serving.BaseWSGIServer
    thread: threading.Thread


def create_app(
    static_dir_path: pathlib.Path | None = None,
) -> flask.Flask:
    """Flask アプリケーションを作成.

    Args:
        static_dir_path: フロントエンドの静的ファイルディレクトリパス（frontend/dist）
    """
    import price_watch.webapi.page

    # NOTE: アクセスログは無効にする
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    # my_lib.webapp の設定
    my_lib.webapp.config.URL_PREFIX = URL_PREFIX
    my_lib.webapp.config.STATIC_DIR_PATH = static_dir_path

    app = flask.Flask("price_watch_webui")

    flask_cors.CORS(app)

    app.json.compat = True  # type: ignore[attr-defined]

    # ブループリント登録
    # フロントエンド静的ファイル（React アプリ）
    if static_dir_path is not None:
        app.register_blueprint(my_lib.webapp.base.blueprint, url_prefix=URL_PREFIX)
        app.register_blueprint(my_lib.webapp.base.blueprint_default)

    # API エンドポイント
    app.register_blueprint(price_watch.webapi.page.blueprint, url_prefix=URL_PREFIX)
    app.register_blueprint(my_lib.webapp.event.blueprint, url_prefix=URL_PREFIX)
    app.register_blueprint(my_lib.webapp.util.blueprint, url_prefix=URL_PREFIX)

    my_lib.webapp.config.show_handler_list(app)

    return app


def start(
    port: int,
    static_dir_path: pathlib.Path | None = None,
) -> ServerHandle:
    """サーバーを開始.

    Args:
        port: サーバーのポート番号
        static_dir_path: フロントエンドの静的ファイルディレクトリパス
    """
    server = werkzeug.serving.make_server(
        "0.0.0.0",  # noqa: S104
        port,
        create_app(static_dir_path),
        threaded=True,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)

    logging.info("Start webui server on port %d", port)

    thread.start()

    return ServerHandle(server=server, thread=thread)


def term(handle: ServerHandle) -> None:
    """サーバーを停止."""
    logging.info("Stop webui server")

    handle.server.shutdown()
    handle.server.server_close()

    handle.thread.join(timeout=10)
    if handle.thread.is_alive():
        logging.error("Server thread did not stop within timeout")
    else:
        logging.info("Server thread stopped successfully")


def main() -> None:
    """エントリポイント."""
    import docopt
    import my_lib.config
    import my_lib.logger

    args = docopt.docopt(__doc__)

    port = int(args["-p"])
    debug_mode = args["-D"]

    my_lib.logger.init("price-watch-webui", level=logging.DEBUG if debug_mode else logging.INFO)

    # 静的ファイルのパス
    static_dir_path = pathlib.Path(__file__).parent.parent.parent.parent / "frontend" / "dist"

    if not static_dir_path.exists():
        logging.warning("Static directory not found: %s", static_dir_path)
        logging.warning("Run 'cd frontend && npm run build' to build the frontend")
        static_dir_path = None

    server_handle = start(port, static_dir_path=static_dir_path)

    try:
        server_handle.thread.join()
    except KeyboardInterrupt:
        logging.info("Stopping server...")
        term(server_handle)


if __name__ == "__main__":
    main()
