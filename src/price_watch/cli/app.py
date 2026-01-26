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
import selenium.common.exceptions

import price_watch.amazon.paapi
import price_watch.config
import price_watch.const
import price_watch.event
import price_watch.history
import price_watch.log_format
import price_watch.metrics
import price_watch.notify
import price_watch.store.mercari
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

        # デバッグモード用: 各チェック方法の成功/失敗を追跡
        self._debug_check_results: dict[str, bool] = {}

        # ドライバー作成の連続失敗回数
        self._driver_create_failures: int = 0

        # メトリクス
        self._metrics_db: price_watch.metrics.MetricsDB | None = None
        self._current_session_id: int | None = None
        self._session_total_items: int = 0
        self._session_success_items: int = 0
        self._session_failed_items: int = 0

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

    def _create_driver_with_retry(self, max_retries: int = 2) -> WebDriver | None:
        """プロファイル削除を伴うリトライ付きでドライバーを作成.

        Args:
            max_retries: プロファイル削除後のリトライ回数

        Returns:
            成功時は WebDriver、全て失敗時は None
        """
        assert self.config is not None  # noqa: S101

        for attempt in range(max_retries + 1):
            try:
                driver = my_lib.selenium_util.create_driver(PROFILE_NAME, self.config.data.selenium)
                self._driver_create_failures = 0
                return driver
            except Exception as e:
                self._driver_create_failures += 1
                logging.warning(
                    "ドライバー作成失敗（%d/%d）: %s",
                    attempt + 1,
                    max_retries + 1,
                    e,
                )

                if attempt < max_retries:
                    # プロファイルを削除してリトライ
                    logging.warning("プロファイルを削除してリトライします")
                    my_lib.chrome_util.delete_profile(PROFILE_NAME, self.config.data.selenium)

        logging.error("ドライバー作成に %d 回失敗しました", max_retries + 1)
        return None

    def _recreate_driver(self) -> bool:
        """ドライバーを再作成.

        セッションエラー発生時にプロファイルを削除して再作成します。

        Returns:
            成功時 True
        """
        if self.config is None:
            return False

        logging.warning("ドライバーを再作成します")

        # 既存ドライバーを終了
        my_lib.selenium_util.quit_driver_gracefully(self.driver)
        self.driver = None

        # プロファイルを削除
        my_lib.chrome_util.delete_profile(PROFILE_NAME, self.config.data.selenium)

        # 新しいドライバーを作成
        self.driver = self._create_driver_with_retry()
        return self.driver is not None

    def _update_liveness(self) -> None:
        """liveness を更新."""
        if self.config is not None:
            my_lib.footprint.update(self.config.liveness.file.crawler)
        # メトリクスのハートビートも更新
        if self._metrics_db is not None and self._current_session_id is not None:
            self._metrics_db.update_heartbeat(self._current_session_id)

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

            # メルカリ検索の場合は item_key を事前に生成
            if item_dict["check_method"] == price_watch.target.CheckMethod.MERCARI_SEARCH.value:
                # search_keyword がなければ name を使用
                search_keyword = item_dict.get("search_keyword") or item_dict["name"]
                item_dict["search_keyword"] = search_keyword
                # item_key を生成（エラーカウント用）
                item_key = price_watch.history.generate_item_key(
                    search_keyword=search_keyword,
                    search_cond=item_dict.get("search_cond", ""),
                )
                if item_key not in self.error_count:
                    self.error_count[item_key] = 0
            else:
                if item_dict["url"] not in self.error_count:
                    self.error_count[item_dict["url"]] = 0

            result.append(item_dict)

        return result

    def _do_work(self, item_list: list[dict[str, Any]]) -> None:
        """監視処理を実行."""
        if self.config is None or self.driver is None:
            return

        # 1. スクレイピング対象
        self._do_work_scrape(item_list)

        # 2. Amazon PA-API 対象
        self._do_work_amazon(item_list)

        # 3. メルカリ検索対象
        self._do_work_mercari(item_list)

    def _do_work_scrape(self, item_list: list[dict[str, Any]]) -> None:
        """スクレイピング対象アイテムを処理."""
        if self.config is None or self.driver is None:
            return

        check_method = "scrape"
        scrape_items = list(filter(lambda item: item["check_method"] == check_method, item_list))

        # デバッグモードでは各ストアにつき1アイテムのみ
        if self.debug_mode:
            scrape_items = self._select_one_item_per_store(scrape_items)
            if scrape_items:
                logging.info("[デバッグモード] スクレイピング: %d件のアイテムをチェック", len(scrape_items))

        # ストアごとにグループ化して処理
        items_by_store: dict[str, list[dict[str, Any]]] = {}
        for item in scrape_items:
            store_name = item.get("store", check_method)
            if store_name not in items_by_store:
                items_by_store[store_name] = []
            items_by_store[store_name].append(item)

        for store_name, store_items in items_by_store.items():
            if self.should_terminate.is_set():
                return

            # ストア巡回開始
            store_stats_id = self._start_store_crawl(store_name)
            store_success = 0
            store_failed = 0

            for item in store_items:
                if self.should_terminate.is_set():
                    self._end_store_crawl(store_stats_id, len(store_items), store_success, store_failed)
                    return

                logging.info(price_watch.log_format.format_crawl_start(item))
                crawl_success = False

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
                        store_success += 1
                        # デバッグモード: このストアは成功
                        if self.debug_mode:
                            self._debug_check_results[store_name] = True
                            logging.info("[デバッグモード] %s: 成功", store_name)
                    else:
                        # 価格要素が見つからなかった場合（例外は発生していない）
                        self.error_count[item["url"]] += 1
                        store_failed += 1
                        logging.warning(
                            price_watch.log_format.format_error(item, self.error_count[item["url"]])
                        )
                        if self.error_count[item["url"]] >= price_watch.const.ERROR_NOTIFY_COUNT:
                            self.error_count[item["url"]] = 0
                        # デバッグモード: このストアは失敗
                        if self.debug_mode:
                            self._debug_check_results[store_name] = False
                            logging.warning("[デバッグモード] %s: 失敗（価格要素なし）", store_name)
                except selenium.common.exceptions.InvalidSessionIdException:
                    # セッションが無効になった場合はドライバーを再作成
                    logging.warning("セッションが無効になりました。ドライバーを再作成します")
                    store_failed += 1
                    if not self._recreate_driver():
                        logging.error("ドライバーの再作成に失敗しました")
                        self._end_store_crawl(store_stats_id, len(store_items), store_success, store_failed)
                        return

                    # 履歴を記録（crawl_status=0）
                    self._process_data(
                        self.config.slack,
                        item,
                        price_watch.history.last(item["url"]),
                        crawl_status=0,
                    )

                    # デバッグモード: このストアは失敗
                    if self.debug_mode:
                        self._debug_check_results[store_name] = False
                        logging.warning("[デバッグモード] %s: 失敗（セッションエラー）", store_name)
                except Exception:
                    self.error_count[item["url"]] += 1
                    store_failed += 1
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

                    # デバッグモード: このストアは失敗
                    if self.debug_mode:
                        self._debug_check_results[store_name] = False
                        logging.warning("[デバッグモード] %s: 失敗（例外発生）", store_name)

                # アイテム結果を記録
                self._record_item_result(success=crawl_success)

                # wait() を使用してシグナル受信時に即座に終了できるようにする
                if self.should_terminate.wait(timeout=price_watch.const.SCRAPE_INTERVAL_SEC):
                    self._end_store_crawl(store_stats_id, len(store_items), store_success, store_failed)
                    return

            # ストア巡回終了
            self._end_store_crawl(store_stats_id, len(store_items), store_success, store_failed)

    def _do_work_amazon(self, item_list: list[dict[str, Any]]) -> None:
        """Amazon PA-API 対象アイテムを処理."""
        if self.config is None:
            return

        check_method = price_watch.target.CheckMethod.AMAZON_PAAPI.value
        amazon_items = list(filter(lambda item: item["check_method"] == check_method, item_list))

        if not amazon_items:
            return

        # デバッグモードでは1アイテムのみ
        if self.debug_mode:
            amazon_items = amazon_items[:1]
            logging.info("[デバッグモード] Amazon PA-API: 1件のアイテムをチェック")
        else:
            logging.info("[Amazon PA-API] %d件のアイテムをチェック中...", len(amazon_items))

        store_name = "amazon.co.jp"
        store_stats_id = self._start_store_crawl(store_name)
        success_count = 0
        failed_count = 0

        try:
            for item in price_watch.amazon.paapi.check_item_list(self.config, amazon_items):
                self._process_data(
                    self.config.slack,
                    item,
                    price_watch.history.last(item["url"]),
                    crawl_status=1,
                )
                success_count += 1
                self._record_item_result(success=True)
            self._update_liveness()
        except Exception:
            logging.exception("Failed to check Amazon PA-API items")
            # 残りのアイテムは失敗扱い
            failed_count = len(amazon_items) - success_count
            for _ in range(failed_count):
                self._record_item_result(success=False)

        self._end_store_crawl(store_stats_id, len(amazon_items), success_count, failed_count)

        # デバッグモード: 結果を記録
        if self.debug_mode:
            success = success_count > 0
            self._debug_check_results[store_name] = success
            if success:
                logging.info("[デバッグモード] %s: 成功", store_name)
            else:
                logging.warning("[デバッグモード] %s: 失敗", store_name)

    def _do_work_mercari(self, item_list: list[dict[str, Any]]) -> None:
        """メルカリ検索対象アイテムを処理."""
        if self.config is None or self.driver is None:
            return

        check_method = price_watch.target.CheckMethod.MERCARI_SEARCH.value
        mercari_items = list(filter(lambda item: item["check_method"] == check_method, item_list))

        if not mercari_items:
            return

        store_name = "mercari.com"

        # デバッグモードでは1アイテムのみ
        if self.debug_mode:
            mercari_items = mercari_items[:1]
            logging.info("[デバッグモード] メルカリ検索: 1件のアイテムをチェック")
        else:
            logging.info("[メルカリ検索] %d件のアイテムをチェック中...", len(mercari_items))

        store_stats_id = self._start_store_crawl(store_name)
        store_success = 0
        store_failed = 0

        for item in mercari_items:
            if self.should_terminate.is_set():
                self._end_store_crawl(store_stats_id, len(mercari_items), store_success, store_failed)
                return

            crawl_success = False
            try:
                price_watch.store.mercari.check(self.config, self.driver, item)

                crawl_success = item.get("crawl_success", False)
                crawl_status = 1 if crawl_success else 0

                # メルカリは item_key ベースで履歴を管理
                item_key = price_watch.store.mercari.generate_item_key(item)
                self._process_data(
                    self.config.slack,
                    item,
                    price_watch.history.last(item_key=item_key),
                    crawl_status=crawl_status,
                )

                if crawl_success:
                    self._update_liveness()
                    self.error_count[item_key] = 0
                    store_success += 1
                    # デバッグモード: 成功
                    if self.debug_mode:
                        self._debug_check_results[store_name] = True
                        logging.info("[デバッグモード] %s: 成功", store_name)
                else:
                    self.error_count[item_key] += 1
                    store_failed += 1
                    logging.warning(price_watch.log_format.format_error(item, self.error_count[item_key]))
                    if self.error_count[item_key] >= price_watch.const.ERROR_NOTIFY_COUNT:
                        self.error_count[item_key] = 0
                    # デバッグモード: 失敗
                    if self.debug_mode:
                        self._debug_check_results[store_name] = False
                        logging.warning("[デバッグモード] %s: 失敗（検索結果なし）", store_name)
            except selenium.common.exceptions.InvalidSessionIdException:
                # セッションが無効になった場合はドライバーを再作成
                logging.warning("セッションが無効になりました。ドライバーを再作成します")
                store_failed += 1
                if not self._recreate_driver():
                    logging.error("ドライバーの再作成に失敗しました")
                    self._end_store_crawl(store_stats_id, len(mercari_items), store_success, store_failed)
                    return

                # 履歴を記録（crawl_status=0）
                item_key = price_watch.store.mercari.generate_item_key(item)
                self._process_data(
                    self.config.slack,
                    item,
                    price_watch.history.last(item_key=item_key),
                    crawl_status=0,
                )

                # デバッグモード: 失敗
                if self.debug_mode:
                    self._debug_check_results[store_name] = False
                    logging.warning("[デバッグモード] %s: 失敗（セッションエラー）", store_name)
            except Exception:
                item_key = price_watch.store.mercari.generate_item_key(item)
                self.error_count[item_key] += 1
                store_failed += 1
                logging.exception("Failed to check mercari item: %s", item["name"])

                self._process_data(
                    self.config.slack,
                    item,
                    price_watch.history.last(item_key=item_key),
                    crawl_status=0,
                )

                if self.error_count[item_key] >= price_watch.const.ERROR_NOTIFY_COUNT:
                    self.error_count[item_key] = 0

                # デバッグモード: 失敗
                if self.debug_mode:
                    self._debug_check_results[store_name] = False
                    logging.warning("[デバッグモード] %s: 失敗（例外発生）", store_name)

            # アイテム結果を記録
            self._record_item_result(success=crawl_success)

            if self.should_terminate.wait(timeout=price_watch.const.SCRAPE_INTERVAL_SEC):
                self._end_store_crawl(store_stats_id, len(mercari_items), store_success, store_failed)
                return

        # ストア巡回終了
        self._end_store_crawl(store_stats_id, len(mercari_items), store_success, store_failed)

    def _select_one_item_per_store(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """各ストアから1アイテムずつ選択.

        Args:
            items: アイテムリスト

        Returns:
            各ストアから1アイテムずつ選択されたリスト
        """
        seen_stores: set[str] = set()
        result: list[dict[str, Any]] = []

        for item in items:
            store = item.get("store", "unknown")
            if store not in seen_stores:
                seen_stores.add(store)
                result.append(item)

        return result

    def execute(self) -> bool:
        """メイン実行ループ.

        Returns:
            正常終了の場合 True（デバッグモードでは全ストア成功時のみ True）
        """
        try:
            # config は run() で先に読み込まれている
            if self.config is None:
                self.config = price_watch.config.load(self.config_file)
            price_watch.history.init(self.config.data.price)
            price_watch.thumbnail.init(self.config.data.thumb)
            # メトリクス DB を初期化
            metrics_db_path = self.config.data.metrics / "metrics.db"
            self._metrics_db = price_watch.metrics.MetricsDB(metrics_db_path)
            self.driver = self._create_driver_with_retry()
            if self.driver is None:
                logging.error("ドライバーの作成に失敗しました")
                return False
        except Exception:
            logging.exception("Failed to initialize")
            return False

        # デバッグモード: 1回だけ実行して終了
        if self.debug_mode:
            logging.info("[デバッグモード] 各ストア1アイテムのみチェックして終了します")
            self._start_session()
            self._do_work(self._load_item_list())
            self._end_session("normal")
            self.cleanup()
            return self._check_debug_results()

        while not self.should_terminate.is_set():
            start_time = time.time()

            self._start_session()
            self._do_work(self._load_item_list())
            self._end_session("normal")

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

    def _start_session(self) -> None:
        """巡回セッションを開始."""
        if self._metrics_db is None:
            return
        self._current_session_id = self._metrics_db.start_session()
        self._session_total_items = 0
        self._session_success_items = 0
        self._session_failed_items = 0

    def _end_session(self, exit_reason: str) -> None:
        """巡回セッションを終了."""
        if self._metrics_db is None or self._current_session_id is None:
            return
        self._metrics_db.end_session(
            self._current_session_id,
            self._session_total_items,
            self._session_success_items,
            self._session_failed_items,
            exit_reason,
        )
        self._current_session_id = None

    def _record_item_result(self, *, success: bool) -> None:
        """アイテムの巡回結果を記録."""
        self._session_total_items += 1
        if success:
            self._session_success_items += 1
        else:
            self._session_failed_items += 1

    def _start_store_crawl(self, store_name: str) -> int | None:
        """ストア巡回を開始."""
        if self._metrics_db is None or self._current_session_id is None:
            return None
        return self._metrics_db.start_store_crawl(self._current_session_id, store_name)

    def _end_store_crawl(
        self,
        stats_id: int | None,
        item_count: int,
        success_count: int,
        failed_count: int,
    ) -> None:
        """ストア巡回を終了."""
        if self._metrics_db is None or stats_id is None:
            return
        self._metrics_db.end_store_crawl(stats_id, item_count, success_count, failed_count)

    def _check_debug_results(self) -> bool:
        """デバッグモードの結果を確認.

        Returns:
            全ストアが成功した場合 True
        """
        if not self._debug_check_results:
            logging.warning("[デバッグモード] チェック対象のストアがありませんでした")
            return False

        all_success = all(self._debug_check_results.values())

        logging.info("[デバッグモード] === チェック結果 ===")
        for store, success in self._debug_check_results.items():
            status = "OK" if success else "NG"
            logging.info("[デバッグモード]   %s: %s", store, status)

        if all_success:
            logging.info("[デバッグモード] 全ストア成功")
        else:
            failed_stores = [s for s, ok in self._debug_check_results.items() if not ok]
            logging.warning("[デバッグモード] 失敗したストア: %s", ", ".join(failed_stores))

        return all_success


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

    # デバッグモードでは WebUI サーバーを起動しない
    if not debug_mode:
        runner.start_webui_server()

    try:
        success = runner.execute()
        if success:
            sys.exit(0)
        else:
            # デバッグモードで失敗した場合は終了コード 1
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
