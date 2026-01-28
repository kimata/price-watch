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
import sqlite3
import threading
import time
from dataclasses import dataclass

import flask
import flask_cors
import my_lib.webapp.base
import my_lib.webapp.config
import my_lib.webapp.event
import my_lib.webapp.util
import werkzeug.serving

URL_PREFIX = "/price"


@dataclass(frozen=True)
class _MetricsDataState:
    """メトリクス DB データ状態（変化検出用）."""

    has_active_session: bool
    is_crawling: bool
    last_heartbeat_at: str | None
    total_items: int


# DB ファイル監視用
_db_path: pathlib.Path | None = None
_last_mtime: float = 0
_last_data_state: _MetricsDataState | None = None
_watch_thread: threading.Thread | None = None
_should_terminate = threading.Event()


def _get_metrics_data_state(db_path: pathlib.Path) -> _MetricsDataState | None:
    """メトリクス DB のデータ状態を取得."""
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                """
                SELECT last_heartbeat_at, work_ended_at, total_items
                FROM crawl_sessions
                WHERE ended_at IS NULL
                ORDER BY started_at DESC
                LIMIT 1
                """
            )
            row = cursor.fetchone()
            if row is None:
                return _MetricsDataState(
                    has_active_session=False,
                    is_crawling=False,
                    last_heartbeat_at=None,
                    total_items=0,
                )
            heartbeat_str, work_ended_at_str, total_items = row
            return _MetricsDataState(
                has_active_session=True,
                is_crawling=work_ended_at_str is None,
                last_heartbeat_at=heartbeat_str,
                total_items=total_items or 0,
            )
    except Exception:
        logging.exception("Error getting metrics data state")
        return None


def _watch_db_file() -> None:
    """DB ファイルの変更を監視し、データに変化があれば SSE イベントを送信."""
    global _last_mtime, _last_data_state
    while not _should_terminate.is_set():
        try:
            if _db_path and _db_path.exists():
                current_mtime = _db_path.stat().st_mtime
                if current_mtime > _last_mtime:
                    _last_mtime = current_mtime

                    current_state = _get_metrics_data_state(_db_path)
                    if _last_data_state is None or current_state != _last_data_state:
                        if _last_data_state is not None:
                            logging.debug("Metrics data changed, notifying clients")
                            my_lib.webapp.event.notify_event(my_lib.webapp.event.EVENT_TYPE.CONTROL)
                        _last_data_state = current_state
        except Exception:
            logging.exception("Error checking metrics db file")

        time.sleep(1.0)


def start_db_watcher(db_path: pathlib.Path) -> None:
    """メトリクス DB ファイル監視スレッドを開始."""
    global _db_path, _last_mtime, _last_data_state, _watch_thread
    if _watch_thread is not None and _watch_thread.is_alive():
        stop_db_watcher()

    _db_path = db_path
    _last_data_state = None
    if _db_path and _db_path.exists():
        _last_mtime = _db_path.stat().st_mtime

    _should_terminate.clear()
    _watch_thread = threading.Thread(target=_watch_db_file, daemon=True)
    _watch_thread.start()
    logging.info("Metrics db watcher thread started")


def stop_db_watcher() -> None:
    """メトリクス DB ファイル監視スレッドを停止."""
    global _watch_thread
    if _watch_thread is None:
        return

    _should_terminate.set()
    _watch_thread.join(timeout=5.0)
    _watch_thread = None
    logging.info("Metrics db watcher thread stopped")


@dataclass
class ServerHandle:
    """サーバーハンドル."""

    server: werkzeug.serving.BaseWSGIServer
    thread: threading.Thread


def create_app(
    static_dir_path: pathlib.Path,
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
    # API エンドポイント（OGP 対応ルートを含むため、静的ファイルより先に登録）
    app.register_blueprint(price_watch.webapi.page.blueprint, url_prefix=URL_PREFIX)

    # フロントエンド静的ファイル（React アプリ）
    if static_dir_path.exists():
        app.register_blueprint(my_lib.webapp.base.blueprint, url_prefix=URL_PREFIX)
        app.register_blueprint(my_lib.webapp.base.blueprint_default)
    app.register_blueprint(my_lib.webapp.event.blueprint, url_prefix=URL_PREFIX)
    app.register_blueprint(my_lib.webapp.util.blueprint, url_prefix=URL_PREFIX)

    my_lib.webapp.config.show_handler_list(app)

    return app


def start(
    port: int,
    static_dir_path: pathlib.Path,
    metrics_db_path: pathlib.Path | None = None,
) -> ServerHandle:
    """サーバーを開始.

    Args:
        port: サーバーのポート番号
        static_dir_path: フロントエンドの静的ファイルディレクトリパス
        metrics_db_path: メトリクス DB パス（指定時に DB ウォッチャーを開始）
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

    # メトリクス DB ウォッチャーを開始
    if metrics_db_path is not None:
        start_db_watcher(metrics_db_path)

    return ServerHandle(server=server, thread=thread)


def term(handle: ServerHandle) -> None:
    """サーバーを停止."""
    logging.info("Stop webui server")

    stop_db_watcher()
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
    import my_lib.logger

    import price_watch.config

    assert __doc__ is not None  # noqa: S101
    args = docopt.docopt(__doc__)

    config_file = pathlib.Path(args["-c"])
    port = int(args["-p"])
    debug_mode = args["-D"]

    my_lib.logger.init("price-watch-webui", level=logging.DEBUG if debug_mode else logging.INFO)

    # 設定を読み込む
    config = price_watch.config.load(config_file)
    static_dir_path = config.webapp.static_dir_path

    if not static_dir_path.exists():
        logging.warning("Static directory not found: %s", static_dir_path)
        logging.warning("Run 'cd frontend && npm run build' to build the frontend")

    server_handle = start(port, static_dir_path=static_dir_path)

    try:
        server_handle.thread.join()
    except KeyboardInterrupt:
        logging.info("Stopping server...")
        term(server_handle)


if __name__ == "__main__":
    main()
