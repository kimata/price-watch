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
_watch_thread: threading.Thread | None = None
_watch_stop_event: threading.Event | None = None


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


def start_db_watcher(db_path: pathlib.Path) -> None:
    """メトリクス DB ファイル監視スレッドを開始."""
    global _watch_thread, _watch_stop_event
    if _watch_thread is not None and _watch_thread.is_alive():
        stop_db_watcher()

    _watch_stop_event, _watch_thread = my_lib.webapp.event.start_db_state_watcher(
        db_path,
        _get_metrics_data_state,
        my_lib.webapp.event.EVENT_TYPE.CONTROL,
    )
    logging.info("Metrics db watcher thread started")


def stop_db_watcher() -> None:
    """メトリクス DB ファイル監視スレッドを停止."""
    global _watch_thread, _watch_stop_event
    if _watch_thread is None or _watch_stop_event is None:
        return

    my_lib.webapp.event.stop_db_state_watcher(_watch_stop_event, _watch_thread)
    _watch_thread = None
    _watch_stop_event = None
    logging.info("Metrics db watcher thread stopped")


@dataclass
class ServerHandle:
    """サーバーハンドル."""

    server: werkzeug.serving.BaseWSGIServer
    thread: threading.Thread


def create_app(
    static_dir_path: pathlib.Path,
    config_file: pathlib.Path | None = None,
    target_file: pathlib.Path | None = None,
) -> flask.Flask:
    """Flask アプリケーションを作成.

    Args:
        static_dir_path: フロントエンドの静的ファイルディレクトリパス（frontend/dist）
        config_file: 設定ファイルパス（指定時にキャッシュパスを更新）
        target_file: ターゲット設定ファイルパス（指定時にキャッシュパスを更新）
    """
    import price_watch.webapi.check_job
    import price_watch.webapi.page
    import price_watch.webapi.target_editor

    # CLI 引数で指定されたファイルパスをキャッシュに反映
    if config_file is not None and target_file is not None:
        price_watch.webapi.page.init_file_paths(config_file, target_file)

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
    # target.yaml エディタ API
    app.register_blueprint(price_watch.webapi.target_editor.blueprint, url_prefix=URL_PREFIX)
    # 動作確認ジョブ API
    app.register_blueprint(price_watch.webapi.check_job.check_job_bp, url_prefix=URL_PREFIX)

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
    config_file: pathlib.Path | None = None,
    target_file: pathlib.Path | None = None,
) -> ServerHandle:
    """サーバーを開始.

    Args:
        port: サーバーのポート番号
        static_dir_path: フロントエンドの静的ファイルディレクトリパス
        metrics_db_path: メトリクス DB パス（指定時に DB ウォッチャーを開始）
        config_file: 設定ファイルパス
        target_file: ターゲット設定ファイルパス
    """
    server = werkzeug.serving.make_server(
        "0.0.0.0",  # noqa: S104
        port,
        create_app(static_dir_path, config_file=config_file, target_file=target_file),
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
