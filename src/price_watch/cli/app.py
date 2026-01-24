#!/usr/bin/env python3
"""
商品価格を監視し、価格変動を通知します。

Usage:
  price-watch [-c CONFIG] [-t TARGET] [-p PORT] [-D]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。[default: config.yaml]
  -t TARGET         : TARGET を価格監視対象の設定ファイルとして読み込んで実行します。[default: target.yaml]
  -p PORT           : WebUI サーバーを動かすポート番号。[default: 5000]
  -D                : デバッグモードで動作します。
"""

from __future__ import annotations

import logging
import pathlib
import signal
import sys
import threading
import time
import traceback
from typing import TYPE_CHECKING, Any

import my_lib.footprint
import my_lib.logger
import my_lib.notify.slack
import my_lib.proc_util
import my_lib.selenium_util

from price_watch import config as config_module
from price_watch import history, notify, thumbnail
from price_watch import target as target_module
from price_watch.config import AppConfig
from price_watch.const import ERROR_NOTIFY_COUNT, SCRAPE_INTERVAL_SEC, SLEEP_UNIT
from price_watch.store import amazon_paapi, scrape
from price_watch.webapi import server as webapi_server

if TYPE_CHECKING:
    from price_watch.webapi.server import ServerHandle

PROFILE_NAME = "Default"


class AppRunner:
    """価格監視ボットの実行を管理するクラス."""

    def __init__(
        self,
        config_file: str,
        target_file: str,
        port: int,
        *,
        debug_mode: bool = False,
    ):
        """AppRunner を初期化.

        Args:
            config_file: 設定ファイルパス
            target_file: ターゲット設定ファイルパス
            port: WebUI ポート番号
            debug_mode: デバッグモード
        """
        self.config_file = config_file
        self.target_file = target_file
        self.port = port
        self.debug_mode = debug_mode

        self.config: AppConfig | None = None
        self.driver: my_lib.selenium_util.WebDriverType | None = None
        self.server_handle: ServerHandle | None = None
        self.should_terminate = threading.Event()
        self.error_count: dict[str, int] = {}
        self.loop = 0
        self._received_signal: int | None = None

    def sig_handler(self, num: int, _frame: Any) -> None:
        """シグナルハンドラ.

        Args:
            num: シグナル番号
            _frame: スタックフレーム（未使用）
        """
        # シグナルハンドラ内では logging を使わない（再入問題を避けるため）
        self._received_signal = num

        if num in (signal.SIGTERM, signal.SIGINT):
            self.should_terminate.set()

    def setup_signal_handlers(self) -> None:
        """シグナルハンドラを設定."""
        signal.signal(signal.SIGTERM, self.sig_handler)
        signal.signal(signal.SIGINT, self.sig_handler)

    def start_webui_server(self) -> None:
        """WebUI サーバーを起動."""
        # 静的ファイルのパス
        static_dir_path = pathlib.Path(__file__).parent.parent.parent.parent / "frontend" / "dist"

        if not static_dir_path.exists():
            logging.warning("Static directory not found: %s", static_dir_path)
            logging.warning("Run 'cd frontend && npm run build' to build the frontend")
            static_dir_path = None

        self.server_handle = webapi_server.start(self.port, static_dir_path=static_dir_path)
        logging.info("WebUI server started on port %d", self.port)

    def cleanup(self) -> None:
        """終了処理."""
        logging.info("Cleaning up...")

        # WebUI サーバーを停止
        if self.server_handle is not None:
            webapi_server.term(self.server_handle)
            self.server_handle = None

        # ブラウザを終了
        if self.driver is not None:
            try:
                self.driver.quit()
            except Exception:
                logging.exception("Failed to quit driver")
            self.driver = None

        # Chrome がファイル（SingletonLock等）を削除する時間を確保
        time.sleep(2)

        # 子プロセスを終了
        my_lib.proc_util.kill_child()

    def _update_liveness(self) -> None:
        """liveness を更新."""
        if self.config is not None:
            my_lib.footprint.update(self.config.liveness.file.crawler)

    def _sleep_until(self, end_time: float) -> None:
        """指定時刻までスリープ."""
        sleep_remain = end_time - time.time()
        logging.info("sleep %d sec...", int(sleep_remain))

        while True:
            self._update_liveness()

            if self.should_terminate.is_set():
                return

            sleep_remain = end_time - time.time()
            if sleep_remain < 0:
                return
            elif sleep_remain < SLEEP_UNIT:
                time.sleep(sleep_remain)
            else:
                time.sleep(SLEEP_UNIT)

    def _process_data(
        self,
        slack_config: my_lib.notify.slack.SlackConfigTypes,
        item: dict[str, Any],
        last: dict[str, Any] | None,
    ) -> bool:
        """データを処理."""
        price_changed = (last is not None) and (item["stock"] == 1) and (item["price"] != last["price"])
        stock_changed = (last is not None) and (item["stock"] != last["stock"])
        if ((last is None) and (item["stock"] == 1)) or price_changed or stock_changed:
            if (last is not None) and (item["stock"] == 0):
                item["price"] = last["price"]

            history.insert(item)

        if last is None:
            if item["stock"] == 1:
                logging.warning(
                    "%s: watch start %d%s. (%s)",
                    item["name"],
                    item["price"],
                    item["price_unit"],
                    "in stock",
                )
            else:
                logging.warning("%s: watch start (%s)", item["name"], "out of stock")
        else:
            item["old_price"] = last["price"]

            if item["stock"] == 1:
                if item["price"] < last["price"]:
                    logging.warning(
                        "%s: price updated %d%s ➡ %d%s.",
                        item["name"],
                        last["price"],
                        item["price_unit"],
                        item["price"],
                        item["price_unit"],
                    )
                    lowest = history.lowest(item["url"])
                    is_record = lowest is not None and item["price"] < lowest["price"]
                    notify.info(slack_config, item, is_record)
                elif last["stock"] == 0:
                    logging.warning(
                        "%s: back in stock %d%s.",
                        item["name"],
                        item["price"],
                        item["price_unit"],
                    )
                    notify.info(slack_config, item)
                else:
                    logging.info(
                        "%s: %d%s (%s).",
                        item["name"],
                        item["price"],
                        item["price_unit"],
                        "out of stock" if item["stock"] == 0 else "in stock",
                    )
            else:
                logging.info("%s: (%s).", item["name"], "out of stock")

        return True

    def _load_item_list(self) -> list[dict[str, Any]]:
        """監視対象アイテムリストを読み込む."""
        target_config = target_module.load(self.target_file)
        items = target_config.resolve_items()
        result: list[dict[str, Any]] = []

        for item in items:
            item_dict = item.to_dict()

            if item_dict["url"] not in self.error_count:
                self.error_count[item_dict["url"]] = 0

            result.append(item_dict)

        return result

    def _do_work(self, item_list: list[dict[str, Any]]) -> None:
        """監視処理を実行."""
        if self.config is None or self.driver is None:
            return

        for item in filter(lambda item: item["check_method"] == "scrape", item_list):
            if self.should_terminate.is_set():
                return

            try:
                scrape.check(self.config, self.driver, item, self.loop)
                self._process_data(self.config.slack, item, history.last(item["url"]))

                self._update_liveness()
                self.error_count[item["url"]] = 0
            except Exception:
                self.error_count[item["url"]] += 1
                logging.debug("error_count = %d.", self.error_count[item["url"]])
                if self.error_count[item["url"]] >= ERROR_NOTIFY_COUNT:
                    notify.error(self.config.slack, item, traceback.format_exc())
                    self.error_count[item["url"]] = 0
            time.sleep(SCRAPE_INTERVAL_SEC)

        for item in amazon_paapi.check_item_list(
            self.config,
            list(filter(lambda item: item["check_method"] == "amazon-paapi", item_list)),
        ):
            self._process_data(self.config.slack, item, history.last(item["url"]))
        self._update_liveness()

    def execute(self) -> bool:
        """メイン実行ループ.

        Returns:
            正常終了の場合 True
        """
        try:
            self.config = config_module.load(self.config_file)
            history.init(self.config.data.price)
            thumbnail.init(self.config.data.thumb)
            self.driver = my_lib.selenium_util.create_driver(PROFILE_NAME, self.config.data.selenium)
        except Exception:
            logging.exception("Failed to initialize")
            return False

        while not self.should_terminate.is_set():
            start_time = time.time()

            self._do_work(self._load_item_list())

            if self.should_terminate.is_set():
                break

            self._sleep_until(start_time + self.config.check.interval_sec)
            self.loop += 1

        # シグナル受信をログ出力（シグナルハンドラ外で安全に出力）
        if self._received_signal is not None:
            logging.warning("Received signal %d", self._received_signal)

        logging.warning("Terminate crawl")
        self.cleanup()

        return True


def run(config_file: str, target_file: str, port: int, *, debug_mode: bool = False) -> None:
    """価格監視を実行.

    Args:
        config_file: 設定ファイルパス
        target_file: ターゲット設定ファイルパス
        port: WebUI ポート番号
        debug_mode: デバッグモード
    """
    runner = AppRunner(config_file, target_file, port, debug_mode=debug_mode)
    runner.setup_signal_handlers()
    runner.start_webui_server()

    try:
        if runner.execute():
            sys.exit(0)
        else:
            sys.exit(1)
    except KeyboardInterrupt:
        logging.info("Received KeyboardInterrupt, shutting down...")
        runner.cleanup()
        sys.exit(0)


def main() -> None:
    """Console script entry point."""
    import docopt

    assert __doc__ is not None  # noqa: S101
    args = docopt.docopt(__doc__)

    config_file = args["-c"]
    target_file = args["-t"]
    port = int(args["-p"])
    debug_mode = args["-D"]

    log_level = logging.DEBUG if debug_mode else logging.INFO
    my_lib.logger.init("bot.price_watch", level=log_level)

    logging.info("Start.")
    logging.info("Using config: %s", config_file)
    logging.info("Using target: %s", target_file)

    run(config_file, target_file, port, debug_mode=debug_mode)


if __name__ == "__main__":
    main()
