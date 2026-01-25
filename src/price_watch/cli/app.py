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
from typing import TYPE_CHECKING, Any

import my_lib.chrome_util
import my_lib.footprint
import my_lib.logger
import my_lib.notify.slack
import my_lib.selenium_util

import price_watch.amazon.paapi
import price_watch.config
import price_watch.const
import price_watch.event
import price_watch.history
import price_watch.log_format
import price_watch.notify
import price_watch.store.scrape
import price_watch.target
import price_watch.thumbnail
import price_watch.webapi.server

if TYPE_CHECKING:
    from selenium.webdriver.remote.webdriver import WebDriver

    from price_watch.webapi.server import ServerHandle

PROFILE_NAME = "Default"


class AppRunner:
    """価格監視ボットの実行を管理するクラス."""

    def __init__(
        self,
        config_file: pathlib.Path,
        target_file: pathlib.Path,
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

        self.config: price_watch.config.AppConfig | None = None
        self.driver: WebDriver | None = None
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
        assert self.config is not None  # noqa: S101

        static_dir_path = self.config.webapp.static_dir_path

        if not static_dir_path.exists():
            logging.warning("Static directory not found: %s", static_dir_path)
            logging.warning("Run 'cd frontend && npm run build' to build the frontend")

        self.server_handle = price_watch.webapi.server.start(self.port, static_dir_path=static_dir_path)
        logging.info("WebUI server started on port %d", self.port)

    def cleanup(self) -> None:
        """終了処理."""
        logging.info("Cleaning up...")

        # WebUI サーバーを停止
        if self.server_handle is not None:
            price_watch.webapi.server.term(self.server_handle)
            self.server_handle = None

        # ブラウザを確実に終了（プロセス終了待機・強制終了も含む）
        my_lib.selenium_util.quit_driver_gracefully(self.driver)
        self.driver = None

        # Chrome プロファイルのロックファイルをクリーンアップ
        if self.config is not None:
            my_lib.chrome_util.cleanup_profile_lock(PROFILE_NAME, self.config.data.selenium)

    def _update_liveness(self) -> None:
        """liveness を更新."""
        if self.config is not None:
            my_lib.footprint.update(self.config.liveness.file.crawler)

    def _sleep_until(self, end_time: float) -> None:
        """指定時刻までスリープ.

        threading.Event.wait() を使用することで、シグナル受信時に即座に終了できる。
        """
        sleep_remain = end_time - time.time()
        logging.info("sleep %d sec...", int(sleep_remain))

        while True:
            self._update_liveness()

            if self.should_terminate.is_set():
                return

            sleep_remain = end_time - time.time()
            if sleep_remain < 0:
                return
            elif sleep_remain < price_watch.const.SLEEP_UNIT:
                # wait() は should_terminate.set() で即座に解除される
                if self.should_terminate.wait(timeout=sleep_remain):
                    return
            else:
                if self.should_terminate.wait(timeout=price_watch.const.SLEEP_UNIT):
                    return

    def _log_watch_start(self, item: dict[str, Any]) -> None:
        """監視開始時のログを出力."""
        logging.info(price_watch.log_format.format_watch_start(item))

    def _log_item_status(self, item: dict[str, Any]) -> None:
        """アイテムの状態をログ出力."""
        logging.info(price_watch.log_format.format_item_status(item))

    def _process_data(
        self,
        slack_config: my_lib.notify.slack.SlackConfigTypes,
        item: dict[str, Any],
        last: dict[str, Any] | None,
        *,
        crawl_status: int = 1,
    ) -> bool:
        """データを処理.

        データモデル:
        - crawl_status=0: クロール失敗 → stock=NULL, price=NULL
        - crawl_status=1, stock=0: 在庫なし → price=NULL
        - crawl_status=1, stock=1: 在庫あり → price=有効な価格

        Args:
            slack_config: Slack 設定
            item: アイテム情報
            last: 前回の記録
            crawl_status: クロール状態（0: 失敗, 1: 成功）
        """
        # 履歴を記録（history.py 側で stock/price の処理を行う）
        item_id = price_watch.history.insert(item, crawl_status=crawl_status)

        # 新規監視開始
        if last is None:
            self._log_watch_start(item)
            return True

        # 既存アイテムの更新（old_price は last から取得）
        if last.get("price") is not None:
            item["old_price"] = last["price"]

        # イベント判定
        self._check_and_notify_events(slack_config, item, last, item_id, crawl_status)

        self._log_item_status(item)

        return True

    def _check_and_notify_events(
        self,
        slack_config: my_lib.notify.slack.SlackConfigTypes,
        item: dict[str, Any],
        last: dict[str, Any],
        item_id: int,
        crawl_status: int,
    ) -> None:
        """イベントを判定して通知.

        Args:
            slack_config: Slack 設定
            item: アイテム情報
            last: 前回の記録
            item_id: アイテム ID
            crawl_status: クロール状態
        """
        if self.config is None:
            return

        # 判定設定を取得
        judge_config = self.config.check.judge
        ignore_hours = judge_config.ignore.hour if judge_config else 24
        windows = judge_config.windows if judge_config else []

        current_price = item.get("price")
        # stock は None（クロール失敗時）の場合がある
        current_stock: int | None = item.get("stock")
        last_stock: int | None = last.get("stock")

        # クロール成功時のイベント判定
        if crawl_status == 1:
            # 1. 在庫復活判定
            result = price_watch.event.check_back_in_stock(item_id, current_stock, last_stock, ignore_hours)
            if result is not None and result.should_notify:
                result.price = current_price
                self._notify_and_record_event(slack_config, result, item, item_id)

            # 価格がある場合のみ価格関連イベントを判定（stock=1 かつ price があるとき）
            if current_price is not None and current_stock == 1:
                # 2. 過去最安値判定
                result = price_watch.event.check_lowest_price(item_id, current_price, ignore_hours)
                if result is not None and result.should_notify:
                    self._notify_and_record_event(slack_config, result, item, item_id)

                # 3. 価格下落判定（windows 設定がある場合のみ）
                if windows:
                    result = price_watch.event.check_price_drop(item_id, current_price, windows)
                    if result is not None and result.should_notify:
                        self._notify_and_record_event(slack_config, result, item, item_id)
        else:
            # クロール失敗時のイベント判定
            result = price_watch.event.check_crawl_failure(item_id)
            if result is not None and result.should_notify:
                self._notify_and_record_event(slack_config, result, item, item_id)

    def _notify_and_record_event(
        self,
        slack_config: my_lib.notify.slack.SlackConfigTypes,
        result: price_watch.event.EventResult,
        item: dict[str, Any],
        item_id: int,
    ) -> None:
        """イベントを通知して記録.

        Args:
            slack_config: Slack 設定
            result: イベント判定結果
            item: アイテム情報
            item_id: アイテム ID
        """
        logging.warning(
            "Event detected: %s for %s",
            result.event_type.value,
            item["name"],
        )

        # 通知送信
        notified = price_watch.notify.event(slack_config, result, item) is not None

        # イベント記録
        price_watch.event.record_event(result, item_id, notified=notified)

    def _load_item_list(self) -> list[dict[str, Any]]:
        """監視対象アイテムリストを読み込む."""
        target_config = price_watch.target.load(self.target_file)
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

            logging.info(price_watch.log_format.format_crawl_start(item))

            try:
                price_watch.store.scrape.check(self.config, self.driver, item, self.loop)

                # crawl_success フラグで成功/失敗を判定
                crawl_success = item.get("crawl_success", False)
                crawl_status = 1 if crawl_success else 0

                self._process_data(
                    self.config.slack,
                    item,
                    price_watch.history.last(item["url"]),
                    crawl_status=crawl_status,
                )

                if crawl_success:
                    self._update_liveness()
                    self.error_count[item["url"]] = 0
                else:
                    # 価格要素が見つからなかった場合（例外は発生していない）
                    self.error_count[item["url"]] += 1
                    logging.warning(price_watch.log_format.format_error(item, self.error_count[item["url"]]))
                    if self.error_count[item["url"]] >= price_watch.const.ERROR_NOTIFY_COUNT:
                        self.error_count[item["url"]] = 0
            except Exception:
                self.error_count[item["url"]] += 1
                logging.warning(price_watch.log_format.format_error(item, self.error_count[item["url"]]))
                # スクリーンショット付きのエラー通知は scrape.py の error_handler で送信済み

                # 例外発生時も履歴を記録（crawl_status=0）
                self._process_data(
                    self.config.slack,
                    item,
                    price_watch.history.last(item["url"]),
                    crawl_status=0,
                )

                if self.error_count[item["url"]] >= price_watch.const.ERROR_NOTIFY_COUNT:
                    self.error_count[item["url"]] = 0
            # wait() を使用してシグナル受信時に即座に終了できるようにする
            if self.should_terminate.wait(timeout=price_watch.const.SCRAPE_INTERVAL_SEC):
                return

        amazon_items = list(filter(lambda item: item["check_method"] == "amazon-paapi", item_list))
        if amazon_items:
            logging.info("[Amazon PA-API] %d件のアイテムをチェック中...", len(amazon_items))

        for item in price_watch.amazon.paapi.check_item_list(self.config, amazon_items):
            self._process_data(
                self.config.slack,
                item,
                price_watch.history.last(item["url"]),
                crawl_status=1,
            )
        self._update_liveness()

    def execute(self) -> bool:
        """メイン実行ループ.

        Returns:
            正常終了の場合 True
        """
        try:
            # config は run() で先に読み込まれている
            if self.config is None:
                self.config = price_watch.config.load(self.config_file)
            price_watch.history.init(self.config.data.price)
            price_watch.thumbnail.init(self.config.data.thumb)
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


def run(config_file: pathlib.Path, target_file: pathlib.Path, port: int, *, debug_mode: bool = False) -> None:
    """価格監視を実行.

    Args:
        config_file: 設定ファイルパス
        target_file: ターゲット設定ファイルパス
        port: WebUI ポート番号
        debug_mode: デバッグモード
    """
    # 設定を先に読み込む
    config = price_watch.config.load(config_file)

    runner = AppRunner(config_file, target_file, port, debug_mode=debug_mode)
    runner.config = config
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

    config_file = pathlib.Path(args["-c"])
    target_file = pathlib.Path(args["-t"])
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
