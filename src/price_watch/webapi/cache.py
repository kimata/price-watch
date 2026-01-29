#!/usr/bin/env python3
"""Web API 用キャッシュ管理.

HistoryManager, target.yaml, config.yaml のキャッシュを管理します。
"""

import logging
import pathlib

import price_watch.config
import price_watch.file_cache
import price_watch.managers.history
import price_watch.target
from price_watch.managers import HistoryManager

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
    global _target_config_cache, _config_cache
    _target_config_cache = price_watch.file_cache.FileCache(
        target_file,
        lambda path: price_watch.target.load(path),
    )
    _config_cache = price_watch.file_cache.FileCache(
        config_file,
        lambda path: price_watch.config.load(path),
    )


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
