#!/usr/bin/env python3
"""
Liveness のチェックを行います（軽量版）

重いモジュール（selenium, undetected_chromedriver 等）を import せずに
liveness ファイルの存在と更新時刻、およびメトリクス DB のセッション状態をチェックします。

Usage:
  price-watch-healthz [-c CONFIG] [-D]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。[default: config.yaml]
  -D                : デバッグモードで動作します。
"""

from __future__ import annotations

import logging
import pathlib
import sys

import docopt
import my_lib.healthz
import my_lib.logger

import price_watch.config
import price_watch.metrics


def main() -> None:
    """Console script entry point."""
    assert __doc__ is not None  # noqa: S101
    args = docopt.docopt(__doc__)

    config_file = pathlib.Path(args["-c"])
    debug_mode = args["-D"]

    my_lib.logger.init("bot.price_watch", level=logging.DEBUG if debug_mode else logging.INFO)

    logging.info("Using config: %s", config_file)

    # 型付き設定を読み込む
    config = price_watch.config.load(config_file)

    # 1. liveness ファイルチェック（従来方式）
    liveness_file = config.liveness.file.crawler
    liveness_interval = config.liveness.interval_sec

    target_list = [
        my_lib.healthz.HealthzTarget(
            name="price-watch",
            liveness_file=liveness_file,
            interval=liveness_interval,
        ),
    ]
    failed_targets = my_lib.healthz.check_liveness_all(target_list)

    if failed_targets:
        logging.error("Liveness check failed: %s", ", ".join(failed_targets))
        sys.exit(1)

    # 2. メトリクス DB によるセッション状態チェック
    metrics_db_path = config.data.metrics / "metrics.db"
    if metrics_db_path.exists():
        metrics_db = price_watch.metrics.MetricsDB(metrics_db_path)

        # ハートビートが古すぎないかチェック（interval_sec * 2 を許容）
        max_age_sec = liveness_interval * 2
        if not metrics_db.is_crawler_healthy(max_age_sec=max_age_sec):
            logging.error("Crawler session is not healthy (heartbeat too old or no active session)")
            sys.exit(1)

        # 現在のセッション情報をログ出力
        status = metrics_db.get_current_session_status()
        if status.is_running and status.uptime_sec is not None:
            hours = int(status.uptime_sec // 3600)
            minutes = int((status.uptime_sec % 3600) // 60)
            logging.info(
                "Crawler running: session=%d, uptime=%dh%dm, items=%d (success=%d, failed=%d)",
                status.session_id or 0,
                hours,
                minutes,
                status.total_items,
                status.success_items,
                status.failed_items,
            )
    else:
        logging.warning("Metrics DB not found: %s (skipping session check)", metrics_db_path)

    logging.info("OK.")
    sys.exit(0)


if __name__ == "__main__":
    main()
