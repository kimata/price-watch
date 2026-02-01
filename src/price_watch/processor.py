#!/usr/bin/env python3
"""アイテム処理.

スクレイピング、PA-API、フリマ検索、Yahoo検索の共通処理を抽出したプロセッサ。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import selenium.common.exceptions

import price_watch.const
import price_watch.event
import price_watch.log_format
import price_watch.managers.metrics_manager
import price_watch.models
import price_watch.notify
import price_watch.store.amazon.paapi
import price_watch.store.flea_market
import price_watch.store.rakuten
import price_watch.store.scrape
import price_watch.store.yahoo
import price_watch.store.yodobashi
import price_watch.target

if TYPE_CHECKING:
    from price_watch.app_context import PriceWatchApp
    from price_watch.config import AppConfig
    from price_watch.target import ResolvedItem


@dataclass
class ItemProcessor:
    """アイテム処理クラス.

    各チェック方法（スクレイピング、PA-API、フリマ検索、Yahoo検索）の共通処理を提供します。
    """

    app: PriceWatchApp
    loop: int = 0
    error_count: dict[str, int] = field(default_factory=dict)
    debug_check_results: dict[str, bool] = field(default_factory=dict)

    @property
    def config(self) -> AppConfig:
        """設定を取得."""
        return self.app.config

    def process_all(self, item_list: list[ResolvedItem]) -> None:
        """全アイテムを処理.

        Args:
            item_list: アイテムリスト
        """
        # 1. スクレイピング対象
        self.process_scrape_items(item_list)

        # 2. Amazon PA-API 対象
        self.process_amazon_items(item_list)

        # 3. フリマ検索対象（メルカリ・ラクマ・PayPayフリマ）
        self.process_flea_market_items(item_list)

        # 4. Yahoo検索対象
        self.process_yahoo_items(item_list)

        # 5. 楽天検索対象
        self.process_rakuten_items(item_list)

        # 6. ヨドバシ対象
        self.process_yodobashi_items(item_list)

    def process_scrape_items(self, item_list: list[ResolvedItem]) -> None:
        """スクレイピング対象アイテムを処理.

        Args:
            item_list: 全アイテムリスト（フィルタリング前）
        """
        driver = self.app.browser_manager.driver
        if driver is None:
            return

        scrape_items = [
            item for item in item_list if item.check_method == price_watch.target.CheckMethod.SCRAPE
        ]

        # デバッグモードでは各ストアにつき1アイテムのみ
        if self.app.debug_mode:
            scrape_items = self._select_one_item_per_store(scrape_items)
            if scrape_items:
                logging.info(
                    "[デバッグモード] スクレイピング: %d件のアイテムをチェック",
                    len(scrape_items),
                )

        # ストアごとにグループ化
        items_by_store = self._group_by_store(scrape_items)

        for store_name, store_items in items_by_store.items():
            if self.app.should_terminate:
                return

            with price_watch.managers.metrics_manager.StoreContext(
                self.app.metrics_manager, store_name
            ) as store_ctx:
                for item in store_items:
                    if self.app.should_terminate:
                        return

                    success = self._process_scrape_item(item, store_name)
                    if success:
                        store_ctx.record_success()
                    else:
                        store_ctx.record_failure()

                    # アイテム間の待機
                    if self.app.wait_for_terminate(timeout=price_watch.const.SCRAPE_INTERVAL_SEC):
                        return

    def _process_scrape_item(self, item: ResolvedItem, store_name: str) -> bool:
        """スクレイピングでアイテムを処理.

        Args:
            item: 監視対象アイテム
            store_name: ストア名

        Returns:
            成功時 True
        """
        driver = self.app.browser_manager.driver
        if driver is None:
            return False

        logging.info(price_watch.log_format.format_crawl_start(item))
        crawl_success = False

        try:
            checked = price_watch.store.scrape.check(self.config, driver, item, self.loop)
            crawl_success = checked.is_success()

            self._process_data(checked)

            if crawl_success:
                self.app.update_liveness()
                self.error_count[item.url] = 0
                if self.app.debug_mode:
                    self.debug_check_results[store_name] = True
                    logging.info("[デバッグモード] %s: 成功", store_name)
            else:
                self._handle_crawl_failure(checked, store_name)

        except selenium.common.exceptions.InvalidSessionIdException:
            logging.warning("セッションが無効になりました。ドライバーを再作成します")
            if not self.app.browser_manager.recreate_driver():
                logging.error("ドライバーの再作成に失敗しました")
                return False
            # 失敗として記録
            checked = price_watch.models.CheckedItem.from_resolved_item(item)
            checked.crawl_status = price_watch.models.CrawlStatus.FAILURE
            self._process_data(checked)
            self._mark_debug_failure(store_name, "セッションエラー")

        except Exception:
            self._handle_exception(item, store_name)

        return crawl_success

    def process_amazon_items(self, item_list: list[ResolvedItem]) -> None:
        """Amazon PA-API 対象アイテムを処理.

        Args:
            item_list: 全アイテムリスト
        """
        amazon_items = [
            item for item in item_list if item.check_method == price_watch.target.CheckMethod.AMAZON_PAAPI
        ]

        if not amazon_items:
            return

        # デバッグモードでは1アイテムのみ
        if self.app.debug_mode:
            amazon_items = amazon_items[:1]
            logging.info("[デバッグモード] Amazon PA-API: 1件のアイテムをチェック")
        else:
            logging.info("[Amazon PA-API] %d件のアイテムをチェック中...", len(amazon_items))

        store_name = amazon_items[0].store
        with price_watch.managers.metrics_manager.StoreContext(
            self.app.metrics_manager, store_name
        ) as store_ctx:
            success_count = 0
            try:
                for checked in price_watch.store.amazon.paapi.check_item_list(self.config, amazon_items):
                    self._process_data(checked)
                    success_count += 1
                    store_ctx.record_success()
                self.app.update_liveness()
            except Exception:
                logging.exception("Failed to check Amazon PA-API items")
                # 残りのアイテムは失敗扱い
                failed_count = len(amazon_items) - success_count
                for _ in range(failed_count):
                    store_ctx.record_failure()

        # デバッグモード: 結果を記録
        if self.app.debug_mode:
            success = success_count > 0
            self.debug_check_results[store_name] = success
            if success:
                logging.info("[デバッグモード] %s: 成功", store_name)
            else:
                logging.warning("[デバッグモード] %s: 失敗", store_name)

    def process_flea_market_items(self, item_list: list[ResolvedItem]) -> None:
        """フリマ検索対象アイテムを処理（メルカリ・ラクマ・PayPayフリマ）.

        Args:
            item_list: 全アイテムリスト
        """
        driver = self.app.browser_manager.driver
        if driver is None:
            return

        flea_market_items = [
            item for item in item_list if item.check_method in price_watch.target.FLEA_MARKET_CHECK_METHODS
        ]

        if not flea_market_items:
            return

        # デバッグモードでは各ストアにつき1アイテムのみ
        if self.app.debug_mode:
            flea_market_items = self._select_one_item_per_store(flea_market_items)
            if flea_market_items:
                logging.info(
                    "[デバッグモード] フリマ検索: %d件のアイテムをチェック",
                    len(flea_market_items),
                )
        else:
            logging.info("[フリマ検索] %d件のアイテムをチェック中...", len(flea_market_items))

        # ストアごとにグループ化してメトリクスを記録
        items_by_store = self._group_by_store(flea_market_items)

        for store_name, store_items in items_by_store.items():
            if self.app.should_terminate:
                return

            with price_watch.managers.metrics_manager.StoreContext(
                self.app.metrics_manager, store_name
            ) as store_ctx:
                for item in store_items:
                    if self.app.should_terminate:
                        return

                    success = self._process_flea_market_item(item, store_name)
                    if success:
                        store_ctx.record_success()
                    else:
                        store_ctx.record_failure()

                    if self.app.wait_for_terminate(timeout=price_watch.const.SCRAPE_INTERVAL_SEC):
                        return

    def _process_flea_market_item(self, item: ResolvedItem, store_name: str) -> bool:
        """フリマアイテムを処理.

        Args:
            item: 監視対象アイテム
            store_name: ストア名

        Returns:
            成功時 True
        """
        driver = self.app.browser_manager.driver
        if driver is None:
            return False

        crawl_success = False

        try:
            checked = price_watch.store.flea_market.check(self.config, driver, item)
            crawl_success = checked.is_success()
            item_key = price_watch.store.flea_market.generate_item_key(checked)

            self._process_data(checked, item_key=item_key)

            if crawl_success:
                self.app.update_liveness()
                self.error_count[item_key] = 0
                if self.app.debug_mode:
                    self.debug_check_results[store_name] = True
                    logging.info("[デバッグモード] %s: 成功", store_name)
            else:
                self._handle_crawl_failure(checked, store_name, item_key=item_key)

        except selenium.common.exceptions.InvalidSessionIdException:
            logging.warning("セッションが無効になりました。ドライバーを再作成します")
            if not self.app.browser_manager.recreate_driver():
                logging.error("ドライバーの再作成に失敗しました")
                return False
            # 失敗として記録
            checked = price_watch.models.CheckedItem.from_resolved_item(item)
            checked.crawl_status = price_watch.models.CrawlStatus.FAILURE
            item_key = price_watch.store.flea_market.generate_item_key(checked)
            self._process_data(checked, item_key=item_key)
            self._mark_debug_failure(store_name, "セッションエラー")

        except Exception:
            # 例外時は CheckedItem を生成
            checked = price_watch.models.CheckedItem.from_resolved_item(item)
            checked.crawl_status = price_watch.models.CrawlStatus.FAILURE
            item_key = price_watch.store.flea_market.generate_item_key(checked)

            self.error_count[item_key] = self.error_count.get(item_key, 0) + 1
            logging.exception("Failed to check flea market item: %s", item.name)
            self._process_data(checked, item_key=item_key)
            if self.error_count[item_key] >= price_watch.const.ERROR_NOTIFY_COUNT:
                self.error_count[item_key] = 0
            self._mark_debug_failure(store_name, "例外発生")

        return crawl_success

    def process_yahoo_items(self, item_list: list[ResolvedItem]) -> None:
        """Yahoo検索対象アイテムを処理.

        Args:
            item_list: 全アイテムリスト
        """
        yahoo_items = [
            item for item in item_list if item.check_method == price_watch.target.CheckMethod.YAHOO_SEARCH
        ]

        if not yahoo_items:
            return

        store_name = yahoo_items[0].store

        # デバッグモードでは1アイテムのみ
        if self.app.debug_mode:
            yahoo_items = yahoo_items[:1]
            logging.info("[デバッグモード] Yahoo検索: 1件のアイテムをチェック")
        else:
            logging.info("[Yahoo検索] %d件のアイテムをチェック中...", len(yahoo_items))

        with price_watch.managers.metrics_manager.StoreContext(
            self.app.metrics_manager, store_name
        ) as store_ctx:
            for item in yahoo_items:
                if self.app.should_terminate:
                    return

                success = self._process_yahoo_item(item, store_name)
                if success:
                    store_ctx.record_success()
                else:
                    store_ctx.record_failure()

                if self.app.wait_for_terminate(timeout=price_watch.const.SCRAPE_INTERVAL_SEC):
                    return

    def _process_yahoo_item(self, item: ResolvedItem, store_name: str) -> bool:
        """Yahooアイテムを処理.

        Args:
            item: 監視対象アイテム
            store_name: ストア名

        Returns:
            成功時 True
        """
        crawl_success = False

        try:
            checked = price_watch.store.yahoo.check(self.config, item)
            crawl_success = checked.is_success()
            item_key = price_watch.store.yahoo.generate_item_key(checked)

            self._process_data(checked, item_key=item_key)

            if crawl_success:
                self.app.update_liveness()
                self.error_count[item_key] = 0
                if self.app.debug_mode:
                    self.debug_check_results[store_name] = True
                    logging.info("[デバッグモード] %s: 成功", store_name)
            else:
                self._handle_crawl_failure(checked, store_name, item_key=item_key)

        except Exception:
            # 例外時は CheckedItem を生成
            checked = price_watch.models.CheckedItem.from_resolved_item(item)
            checked.crawl_status = price_watch.models.CrawlStatus.FAILURE
            item_key = price_watch.store.yahoo.generate_item_key(checked)

            self.error_count[item_key] = self.error_count.get(item_key, 0) + 1
            logging.exception("Failed to check yahoo item: %s", item.name)
            self._process_data(checked, item_key=item_key)
            if self.error_count[item_key] >= price_watch.const.ERROR_NOTIFY_COUNT:
                self.error_count[item_key] = 0
            self._mark_debug_failure(store_name, "例外発生")

        return crawl_success

    def process_rakuten_items(self, item_list: list[ResolvedItem]) -> None:
        """楽天検索対象アイテムを処理.

        Args:
            item_list: 全アイテムリスト
        """
        rakuten_items = [
            item for item in item_list if item.check_method == price_watch.target.CheckMethod.RAKUTEN_SEARCH
        ]

        if not rakuten_items:
            return

        store_name = rakuten_items[0].store

        # デバッグモードでは1アイテムのみ
        if self.app.debug_mode:
            rakuten_items = rakuten_items[:1]
            logging.info("[デバッグモード] 楽天検索: 1件のアイテムをチェック")
        else:
            logging.info("[楽天検索] %d件のアイテムをチェック中...", len(rakuten_items))

        with price_watch.managers.metrics_manager.StoreContext(
            self.app.metrics_manager, store_name
        ) as store_ctx:
            for item in rakuten_items:
                if self.app.should_terminate:
                    return

                success = self._process_rakuten_item(item, store_name)
                if success:
                    store_ctx.record_success()
                else:
                    store_ctx.record_failure()

                if self.app.wait_for_terminate(timeout=price_watch.const.SCRAPE_INTERVAL_SEC):
                    return

    def _process_rakuten_item(self, item: ResolvedItem, store_name: str) -> bool:
        """楽天アイテムを処理.

        Args:
            item: 監視対象アイテム
            store_name: ストア名

        Returns:
            成功時 True
        """
        crawl_success = False

        try:
            checked = price_watch.store.rakuten.check(self.config, item)
            crawl_success = checked.is_success()
            item_key = price_watch.store.rakuten.generate_item_key(checked)

            self._process_data(checked, item_key=item_key)

            if crawl_success:
                self.app.update_liveness()
                self.error_count[item_key] = 0
                if self.app.debug_mode:
                    self.debug_check_results[store_name] = True
                    logging.info("[デバッグモード] %s: 成功", store_name)
            else:
                self._handle_crawl_failure(checked, store_name, item_key=item_key)

        except Exception:
            # 例外時は CheckedItem を生成
            checked = price_watch.models.CheckedItem.from_resolved_item(item)
            checked.crawl_status = price_watch.models.CrawlStatus.FAILURE
            item_key = price_watch.store.rakuten.generate_item_key(checked)

            self.error_count[item_key] = self.error_count.get(item_key, 0) + 1
            logging.exception("Failed to check rakuten item: %s", item.name)
            self._process_data(checked, item_key=item_key)
            if self.error_count[item_key] >= price_watch.const.ERROR_NOTIFY_COUNT:
                self.error_count[item_key] = 0
            self._mark_debug_failure(store_name, "例外発生")

        return crawl_success

    def process_yodobashi_items(self, item_list: list[ResolvedItem]) -> None:
        """ヨドバシ対象アイテムを処理.

        Args:
            item_list: 全アイテムリスト
        """
        driver = self.app.browser_manager.driver
        if driver is None:
            return

        yodobashi_items = [
            item for item in item_list if item.check_method == price_watch.target.CheckMethod.YODOBASHI_SCRAPE
        ]

        if not yodobashi_items:
            return

        # デバッグモードでは各ストアにつき1アイテムのみ
        if self.app.debug_mode:
            yodobashi_items = self._select_one_item_per_store(yodobashi_items)
            if yodobashi_items:
                logging.info(
                    "[デバッグモード] ヨドバシ: %d件のアイテムをチェック",
                    len(yodobashi_items),
                )
        else:
            logging.info("[ヨドバシ] %d件のアイテムをチェック中...", len(yodobashi_items))

        # ストアごとにグループ化
        items_by_store = self._group_by_store(yodobashi_items)

        for store_name, store_items in items_by_store.items():
            if self.app.should_terminate:
                return

            with price_watch.managers.metrics_manager.StoreContext(
                self.app.metrics_manager, store_name
            ) as store_ctx:
                for item in store_items:
                    if self.app.should_terminate:
                        return

                    success = self._process_yodobashi_item(item, store_name)
                    if success:
                        store_ctx.record_success()
                    else:
                        store_ctx.record_failure()

                    # アイテム間の待機
                    if self.app.wait_for_terminate(timeout=price_watch.const.SCRAPE_INTERVAL_SEC):
                        return

    def _process_yodobashi_item(self, item: ResolvedItem, store_name: str) -> bool:
        """ヨドバシアイテムを処理.

        Args:
            item: 監視対象アイテム
            store_name: ストア名

        Returns:
            成功時 True
        """
        driver = self.app.browser_manager.driver
        if driver is None:
            return False

        logging.info(price_watch.log_format.format_crawl_start(item))
        crawl_success = False

        try:
            checked = price_watch.store.yodobashi.check(self.config, driver, item)
            crawl_success = checked.is_success()

            self._process_data(checked)

            if crawl_success:
                self.app.update_liveness()
                self.error_count[item.url] = 0
                if self.app.debug_mode:
                    self.debug_check_results[store_name] = True
                    logging.info("[デバッグモード] %s: 成功", store_name)
            else:
                self._handle_crawl_failure(checked, store_name)

        except selenium.common.exceptions.InvalidSessionIdException:
            logging.warning("セッションが無効になりました。ドライバーを再作成します")
            if not self.app.browser_manager.recreate_driver():
                logging.error("ドライバーの再作成に失敗しました")
                return False
            # 失敗として記録
            checked = price_watch.models.CheckedItem.from_resolved_item(item)
            checked.crawl_status = price_watch.models.CrawlStatus.FAILURE
            self._process_data(checked)
            self._mark_debug_failure(store_name, "セッションエラー")

        except Exception:
            self._handle_exception(item, store_name)

        return crawl_success

    def _process_data(
        self,
        item: price_watch.models.CheckedItem,
        *,
        item_key: str | None = None,
    ) -> bool:
        """データを処理.

        Args:
            item: チェック済みアイテム
            item_key: アイテムキー（メルカリ・Yahoo用）

        Returns:
            成功時 True
        """
        history = self.app.history_manager

        # アイテム情報のみを upsert（価格履歴はまだ挿入しない）
        item_id = history.upsert_item(item)

        # 最新の履歴を取得（イベント判定のため、価格履歴挿入前に取得）
        last = history.get_last(item_key=item_key) if item_key else history.get_last(item.url)

        # 新規監視開始
        if last is None:
            # 価格履歴を挿入
            history.insert_price_history(item_id, item)
            self._log_watch_start(item)
            return True

        # 既存アイテムの更新
        if last.price is not None:
            item.old_price = last.price

        # イベント判定（価格履歴挿入前に判定することで、今回の価格を含めずに最安値を計算）
        crawl_status = 1 if item.crawl_status == price_watch.models.CrawlStatus.SUCCESS else 0
        self._check_and_notify_events(item, last, item_id, crawl_status)

        # 価格履歴を挿入
        history.insert_price_history(item_id, item)

        self._log_item_status(item)

        return True

    def _resolve_currency_rate(self, price_unit: str) -> float:
        """アイテムの price_unit に一致する通貨レートを返す.

        Args:
            price_unit: アイテムの通貨単位

        Returns:
            通貨レート（一致するものがなければ 1.0）
        """
        for cr in self.config.check.currency:
            if cr.label == price_unit:
                return cr.rate
        return 1.0

    def _build_all_currency_rates(self) -> dict[str, float]:
        """全通貨の換算レート辞書を構築.

        Returns:
            通貨ラベルをキー、レートを値とする辞書
        """
        rates: dict[str, float] = {}
        for cr in self.config.check.currency:
            rates[cr.label] = cr.rate
        return rates

    def _check_and_notify_events(
        self,
        item: price_watch.models.CheckedItem,
        last: price_watch.models.PriceHistoryRecord,
        item_id: int,
        crawl_status: int,
    ) -> None:
        """イベントを判定して通知."""
        history = self.app.history_manager
        drop_config = self.config.check.drop
        lowest_config = self.config.check.lowest
        ignore_hours = drop_config.ignore.hour if drop_config else 24
        windows = drop_config.windows if drop_config else []

        current_price = item.price
        current_stock = item.stock_as_int()
        last_stock = last.stock

        currency_rate = self._resolve_currency_rate(item.price_unit)
        all_currency_rates = self._build_all_currency_rates()

        if crawl_status == 1:
            # 在庫復活判定
            result = price_watch.event.check_back_in_stock(
                history, item_id, current_stock, last_stock, ignore_hours
            )
            if result is not None and result.should_notify:
                result.price = current_price
                self._notify_and_record_event(result, item, item_id)

            # 価格関連イベント
            if current_price is not None and current_stock == 1:
                result = price_watch.event.check_lowest_price(
                    history,
                    item_id,
                    current_price,
                    ignore_hours,
                    lowest_config=lowest_config,
                    currency_rate=currency_rate,
                    item_name=item.name,
                    all_currency_rates=all_currency_rates,
                )
                if result is not None and result.should_notify:
                    self._notify_and_record_event(result, item, item_id)

                if windows:
                    result = price_watch.event.check_price_drop(
                        history,
                        item_id,
                        current_price,
                        windows,
                        currency_rate=currency_rate,
                        item_name=item.name,
                        all_currency_rates=all_currency_rates,
                    )
                    if result is not None and result.should_notify:
                        self._notify_and_record_event(result, item, item_id)
        else:
            # クロール失敗時
            result = price_watch.event.check_crawl_failure(history, item_id)
            if result is not None and result.should_notify:
                self._notify_and_record_event(result, item, item_id)

            result = price_watch.event.check_data_retrieval_failure(history, item_id)
            if result is not None and result.should_notify:
                self._notify_and_record_event(result, item, item_id)

    def _notify_and_record_event(
        self,
        result: price_watch.event.EventResult,
        item: price_watch.models.CheckedItem,
        item_id: int,
    ) -> None:
        """イベントを通知して記録."""
        logging.warning(
            "Event detected: %s for %s",
            result.event_type.value,
            item.name,
        )

        # イベント発生時点の URL をスナップショットとして保存
        result.url = item.url

        notified = (
            price_watch.notify.event(self.config.slack, result, item, self.config.webapp.external_url)
            is not None
        )
        price_watch.event.record_event(self.app.history_manager, result, item_id, notified=notified)

    def _handle_crawl_failure(
        self,
        item: price_watch.models.CheckedItem,
        store_name: str,
        *,
        item_key: str | None = None,
    ) -> None:
        """クロール失敗を処理."""
        key = item_key or item.url or ""
        self.error_count[key] = self.error_count.get(key, 0) + 1
        logging.warning(price_watch.log_format.format_error(item, self.error_count[key]))
        if self.error_count[key] >= price_watch.const.ERROR_NOTIFY_COUNT:
            self.error_count[key] = 0
        self._mark_debug_failure(store_name, "価格要素なし")

    def _handle_exception(self, item: ResolvedItem, store_name: str) -> None:
        """例外を処理."""
        self.error_count[item.url] = self.error_count.get(item.url, 0) + 1
        logging.warning(price_watch.log_format.format_error(item, self.error_count[item.url]))

        # 失敗として記録
        checked = price_watch.models.CheckedItem.from_resolved_item(item)
        checked.crawl_status = price_watch.models.CrawlStatus.FAILURE
        self._process_data(checked)

        if self.error_count[item.url] >= price_watch.const.ERROR_NOTIFY_COUNT:
            self.error_count[item.url] = 0
        self._mark_debug_failure(store_name, "例外発生")

    def _mark_debug_failure(self, store_name: str, reason: str) -> None:
        """デバッグモードで失敗を記録."""
        if self.app.debug_mode:
            self.debug_check_results[store_name] = False
            logging.warning("[デバッグモード] %s: 失敗（%s）", store_name, reason)

    def _log_watch_start(self, item: price_watch.models.CheckedItem) -> None:
        """監視開始をログ出力."""
        logging.info(price_watch.log_format.format_watch_start(item))

    def _log_item_status(self, item: price_watch.models.CheckedItem) -> None:
        """アイテム状態をログ出力."""
        logging.info(price_watch.log_format.format_item_status(item))

    def _group_by_store(self, items: list[ResolvedItem]) -> dict[str, list[ResolvedItem]]:
        """ストアごとにグループ化."""
        result: dict[str, list[ResolvedItem]] = {}
        for item in items:
            store_name = item.store
            if store_name not in result:
                result[store_name] = []
            result[store_name].append(item)
        return result

    def _select_one_item_per_store(self, items: list[ResolvedItem]) -> list[ResolvedItem]:
        """各ストアから1アイテムずつ選択."""
        seen_stores: set[str] = set()
        result: list[ResolvedItem] = []
        for item in items:
            store = item.store
            if store not in seen_stores:
                seen_stores.add(store)
                result.append(item)
        return result

    def check_debug_results(self) -> bool:
        """デバッグモードの結果を確認.

        Returns:
            全ストアが成功した場合 True
        """
        if not self.debug_check_results:
            logging.warning("[デバッグモード] チェック対象のストアがありませんでした")
            return False

        all_success = all(self.debug_check_results.values())

        logging.info("[デバッグモード] === チェック結果 ===")
        for store, success in self.debug_check_results.items():
            status = "OK" if success else "NG"
            logging.info("[デバッグモード]   %s: %s", store, status)

        if all_success:
            logging.info("[デバッグモード] 全ストア成功")
        else:
            failed_stores = [s for s, ok in self.debug_check_results.items() if not ok]
            logging.warning("[デバッグモード] 失敗したストア: %s", ", ".join(failed_stores))

        return all_success
