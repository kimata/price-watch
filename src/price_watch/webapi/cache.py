#!/usr/bin/env python3
"""Web API 用キャッシュ管理.

HistoryManager, target.yaml, config.yaml のキャッシュを管理します。
target.yaml の変更を監視し、変更時にキャッシュを無効化して SSE で通知します。
ヨドバシ検索用のブラウザも管理します。
"""

from __future__ import annotations

import logging
import pathlib
import threading
from typing import TYPE_CHECKING

import my_lib.browser
import my_lib.file_watcher
import my_lib.webapp.event

import price_watch.config
import price_watch.file_cache
import price_watch.managers.history
import price_watch.target
from price_watch.managers import HistoryManager

if TYPE_CHECKING:
    from my_lib.browser import Browser, Page

# HistoryManager のキャッシュ（遅延初期化）
_history_manager: HistoryManager | None = None

# target.yaml のキャッシュ（ファイル更新時刻が変わった場合のみ再読み込み）
_target_config_cache: price_watch.file_cache.FileCache[price_watch.target.TargetConfig] = (
    price_watch.file_cache.FileCache(
        price_watch.target.TARGET_FILE_PATH,
        lambda path: price_watch.target.load(path),
    )
)

# config.yaml のキャッシュ
_config_cache: price_watch.file_cache.FileCache[price_watch.config.AppConfig] = (
    price_watch.file_cache.FileCache(
        price_watch.config.CONFIG_FILE_PATH,
        lambda path: price_watch.config.load(path),
    )
)

# ファイル監視（target.yaml の変更検知用）
_file_watcher: my_lib.file_watcher.FileWatcher | None = None


def _on_target_file_changed() -> None:
    """target.yaml が変更された時のコールバック."""
    logging.info("target.yaml changed, invalidating cache and notifying clients")

    # キャッシュを無効化
    _target_config_cache.invalidate()

    # SSE でフロントエンドに通知（データ再取得を促す）
    my_lib.webapp.event.notify_event(my_lib.webapp.event.EVENT_TYPE.CONTENT)


def get_history_manager() -> HistoryManager:
    """HistoryManager を取得（遅延初期化）."""
    global _history_manager
    if _history_manager is not None:
        return _history_manager
    config = get_app_config()
    if config is None:
        msg = f"App config not available (config path: {_config_cache.file_path}, cwd: {pathlib.Path.cwd()})"
        raise RuntimeError(msg)
    logging.debug("Initializing HistoryManager with data path: %s", config.data.price)
    manager = price_watch.managers.history.HistoryManager.create(config.data.price)
    manager.initialize()
    _history_manager = manager
    return _history_manager


def init_file_paths(
    config_file: pathlib.Path,
    target_file: pathlib.Path,
) -> None:
    """キャッシュのファイルパスを設定.

    CLI 引数で指定されたパスを反映するために、サーバー起動時に呼び出す。

    Args:
        config_file: 設定ファイルパス
        target_file: ターゲット設定ファイルパス
    """
    global _target_config_cache, _config_cache, _file_watcher

    _target_config_cache = price_watch.file_cache.FileCache(
        target_file,
        lambda path: price_watch.target.load(path),
    )
    _config_cache = price_watch.file_cache.FileCache(
        config_file,
        lambda path: price_watch.config.load(path),
    )

    # 既存の FileWatcher があれば停止して再設定
    if _file_watcher is not None:
        _file_watcher.stop()

    new_watcher = my_lib.file_watcher.FileWatcher()
    new_watcher.watch(
        path=target_file,
        on_change=_on_target_file_changed,
        debounce_sec=0.5,
    )
    _file_watcher = new_watcher


def start_file_watcher() -> None:
    """ファイル監視を開始."""
    global _file_watcher

    # init_file_paths が呼ばれていない場合はデフォルトパスで初期化
    watcher = _file_watcher
    if watcher is None:
        watcher = my_lib.file_watcher.FileWatcher()
        watcher.watch(
            path=_target_config_cache.file_path,
            on_change=_on_target_file_changed,
            debounce_sec=0.5,
        )
        _file_watcher = watcher

    watcher.start()
    logging.info("Started file watcher for target.yaml: %s", _target_config_cache.file_path)


def stop_file_watcher() -> None:
    """ファイル監視を停止."""
    global _file_watcher
    if _file_watcher is not None:
        _file_watcher.stop()
        _file_watcher = None
        logging.info("Stopped file watcher for target.yaml")


def get_target_config() -> price_watch.target.TargetConfig | None:
    """target.yaml の設定を取得（キャッシュ使用）."""
    try:
        return _target_config_cache.get()
    except Exception:
        logging.warning("Failed to load target.yaml config")
        return None


def get_app_config() -> price_watch.config.AppConfig | None:
    """config.yaml の設定を取得（キャッシュ使用）."""
    try:
        config = _config_cache.get()
        if config is None:
            logging.warning(
                "config.yaml not found at path: %s (cwd: %s)",
                _config_cache.file_path,
                pathlib.Path.cwd(),
            )
        return config
    except Exception:
        logging.exception("Failed to load config.yaml from %s", _config_cache.file_path)
        return None


def get_config_cache() -> price_watch.file_cache.FileCache[price_watch.config.AppConfig]:
    """config.yaml キャッシュオブジェクトを取得."""
    return _config_cache


def get_target_config_cache() -> price_watch.file_cache.FileCache[price_watch.target.TargetConfig]:
    """target.yaml キャッシュオブジェクトを取得."""
    return _target_config_cache


# ヨドバシ検索用ブラウザ管理
_yodobashi_browser: Browser | None = None
_yodobashi_browser_lock: threading.Lock = threading.Lock()


def get_yodobashi_page() -> Page | None:
    """ヨドバシ検索用のブラウザページを取得（遅延初期化）.

    Returns:
        Page インスタンス（初期化失敗時は None）
    """
    global _yodobashi_browser

    with _yodobashi_browser_lock:
        if _yodobashi_browser is not None:
            pages = _yodobashi_browser.pages()
            return pages[0] if pages else _yodobashi_browser.new_page()

        config = get_app_config()
        if config is None:
            logging.error("Cannot create Yodobashi browser: config not available")
            return None

        try:
            logging.info("Creating Yodobashi search browser")
            browser = my_lib.browser.launch(
                my_lib.browser.BrowserProfile(
                    name="yodobashi_search",
                    data_dir=config.data.selenium,
                ),
            )
            _yodobashi_browser = browser
            pages = browser.pages()
            return pages[0] if pages else browser.new_page()
        except my_lib.browser.BrowserError:
            logging.exception("Failed to create Yodobashi search browser")
            return None


def quit_yodobashi_browser() -> None:
    """ヨドバシ検索用ブラウザを終了."""
    global _yodobashi_browser

    with _yodobashi_browser_lock:
        if _yodobashi_browser is not None:
            logging.info("Quitting Yodobashi search browser")
            _yodobashi_browser.close()
            _yodobashi_browser = None
