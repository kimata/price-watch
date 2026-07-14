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

import my_lib.healthz
import my_lib.healthz.cli

import price_watch.config
import price_watch.metrics


def _load_config(config_file, args):
    return price_watch.config.load(pathlib.Path(config_file))


def _targets(config, args):
    return [
        my_lib.healthz.HealthzTarget(
            name="price-watch",
            liveness_file=config.liveness.file.crawler,
            interval=config.liveness.interval_sec,
        ),
    ]


def _check_crawler_session(config, args):
    """メトリクス DB によるセッション状態チェック"""
    metrics_db_path = config.data.metrics / "metrics.db"
    if not metrics_db_path.exists():
        logging.warning("Metrics DB not found: %s (skipping session check)", metrics_db_path)
        return True

    metrics_db = price_watch.metrics.MetricsDB(metrics_db_path)

    # ハートビートが古すぎないかチェック（interval_sec * 2 を許容）
    max_age_sec = config.liveness.interval_sec * 2
    if not metrics_db.is_crawler_healthy(max_age_sec=max_age_sec):
        logging.error("Crawler session is not healthy (heartbeat too old or no active session)")
        return False

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

    return True


SPEC = my_lib.healthz.cli.HealthzCliSpec(
    logger_name="bot.price_watch",
    config_loader=_load_config,
    targets_builder=_targets,
    extra_checks=(_check_crawler_session,),
)


def main() -> None:
    """Console script entry point."""
    assert __doc__ is not None  # noqa: S101
    my_lib.healthz.cli.run(SPEC, __doc__)


if __name__ == "__main__":
    main()
