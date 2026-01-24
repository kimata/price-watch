#!/usr/bin/env python3
"""
Liveness のチェックを行います（軽量版）

重いモジュール（selenium, undetected_chromedriver 等）を import せずに
liveness ファイルの存在と更新時刻をチェックします。

Usage:
  price-watch-healthz [-c CONFIG] [-D]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。[default: config.yaml]
  -D                : デバッグモードで動作します。
"""

from __future__ import annotations

import logging
import sys

import docopt
import my_lib.config
import my_lib.healthz
import my_lib.logger


def main() -> None:
    """Console script entry point."""
    assert __doc__ is not None  # noqa: S101
    args = docopt.docopt(__doc__)

    config_file = args["-c"]
    debug_mode = args["-D"]

    my_lib.logger.init("bot.price_watch", level=logging.DEBUG if debug_mode else logging.INFO)

    logging.info("Using config: %s", config_file)
    config = my_lib.config.load(config_file)

    liveness_config = config.get("liveness", {})
    liveness_file = liveness_config.get("file", "/dev/shm/price_watch_healthz")  # noqa: S108
    liveness_interval = liveness_config.get("interval", 300)

    target_list = [
        my_lib.healthz.HealthzTarget(name="price-watch", file=liveness_file, interval=liveness_interval),
    ]
    failed_targets = my_lib.healthz.check_liveness_all(target_list)

    if not failed_targets:
        logging.info("OK.")
        sys.exit(0)
    else:
        logging.error("Failed: %s", ", ".join(failed_targets))
        sys.exit(1)


if __name__ == "__main__":
    main()
