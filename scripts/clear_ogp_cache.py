#!/usr/bin/env python3
"""
OGP 画像キャッシュを削除するスクリプト。

Usage:
  clear_ogp_cache.py [-c CONFIG] [-k ITEM_KEY] [-a] [-D]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。
                      [default: config.yaml]
  -k ITEM_KEY       : 削除する OGP 画像の item_key。省略時は全削除。
  -a                : 全ての OGP キャッシュを削除します。
  -D                : デバッグモードで動作します。
"""

from __future__ import annotations

import logging
import pathlib


def clear_ogp_cache(cache_dir: pathlib.Path, item_key: str | None = None) -> int:
    """OGP キャッシュを削除.

    Args:
        cache_dir: キャッシュディレクトリのパス
        item_key: 削除対象の item_key（None の場合は全削除）

    Returns:
        削除したファイル数
    """
    ogp_cache_dir = cache_dir / "ogp"

    if not ogp_cache_dir.exists():
        logging.info("OGP cache directory does not exist: %s", ogp_cache_dir)
        return 0

    deleted_count = 0

    if item_key:
        # 特定のアイテムのキャッシュを削除
        cache_file = ogp_cache_dir / f"{item_key}.png"
        if cache_file.exists():
            cache_file.unlink()
            logging.info("Deleted: %s", cache_file)
            deleted_count = 1
        else:
            logging.info("Cache file not found: %s", cache_file)
    else:
        # 全キャッシュを削除
        for cache_file in ogp_cache_dir.glob("*.png"):
            cache_file.unlink()
            logging.info("Deleted: %s", cache_file)
            deleted_count += 1

    return deleted_count


if __name__ == "__main__":
    import docopt
    import my_lib.logger

    import price_watch.config

    assert __doc__ is not None  # noqa: S101
    args = docopt.docopt(__doc__)

    config_file = pathlib.Path(args["-c"])
    item_key: str | None = args["-k"]
    clear_all = args["-a"]
    debug_mode = args["-D"]

    my_lib.logger.init("clear-ogp-cache", level=logging.DEBUG if debug_mode else logging.INFO)

    # 設定を読み込む
    config = price_watch.config.load(config_file)
    cache_dir = config.data.cache

    # 引数チェック
    if not item_key and not clear_all:
        logging.error("Either -k ITEM_KEY or -a (all) must be specified")
        raise SystemExit(1)

    # キャッシュを削除
    deleted_count = clear_ogp_cache(cache_dir, item_key)

    logging.info("Deleted %d OGP cache file(s)", deleted_count)
