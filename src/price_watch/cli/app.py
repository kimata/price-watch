#!/usr/bin/env python3
"""
商品価格を監視し、価格変動を通知します。

Usage:
  price-watch [-c CONFIG] [-t TARGET] [-p PORT] [-D] [--item ITEM] [--store STORE]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。[default: config.yaml]
  -t TARGET         : TARGET を価格監視対象の設定ファイルとして読み込んで実行します。[default: target.yaml]
  -p PORT           : WebUI サーバーを動かすポート番号。[default: 5000]
  -D                : デバッグモードで動作します。
  --item ITEM       : 特定の商品名を指定してチェックします（部分一致）。-D と併用。
  --store STORE     : 特定のストア名を指定してチェックします（部分一致）。-D と併用。
"""

from __future__ import annotations

import logging
import pathlib
import sys
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import my_lib.logger
import my_lib.webapp.event

import price_watch.app_context
import price_watch.chart_image
import price_watch.chart_image_worker
import price_watch.const
import price_watch.managers.history
import price_watch.notify
import price_watch.processor
import price_watch.target

if TYPE_CHECKING:
    from price_watch.models import TargetDiff
    from price_watch.target import ResolvedItem

if TYPE_CHECKING:
    from price_watch.app_context import PriceWatchApp


@dataclass
class AppRunner:
    """価格監視ボットの実行を管理するクラス.

    PriceWatchApp をオーケストレーションし、メインループを制御します。
    """

    app: PriceWatchApp
    _processor: price_watch.processor.ItemProcessor | None = field(default=None, init=False)
    _loop: int = field(default=0, init=False)
    _last_chart_generation_time: float = field(default=0.0, init=False)

    @property
    def processor(self) -> price_watch.processor.ItemProcessor:
        """ItemProcessor を取得（遅延初期化）."""
        if self._processor is None:
            self._processor = price_watch.processor.ItemProcessor(
                app=self.app,
                loop=self._loop,
            )
        return self._processor

    def execute(self) -> bool:
        """メイン実行ループ.

        Returns:
            正常終了の場合 True（デバッグモードでは全ストア成功時のみ True）
        """
        try:
            # 初期化
            self.app.initialize()

            # ブラウザを起動
            self.app.browser_manager.ensure_driver()

        except Exception:
            logging.exception("Failed to initialize")
            return False

        # デバッグモード: 1回だけ実行して終了
        if self.app.debug_mode:
            return self._execute_debug_mode()

        return self._execute_main_loop()

    def _execute_debug_mode(self) -> bool:
        """デバッグモードで実行.

        Returns:
            全ストア成功時 True
        """
        logging.info("[デバッグモード] 各ストア1アイテムのみチェックして終了します")

        self.app.metrics_manager.start_session()
        self._do_work()
        self.app.metrics_manager.end_session("normal")
        self.app.shutdown()

        return self.processor.check_debug_results()

    def _execute_main_loop(self) -> bool:
        """メインループを実行.

        Returns:
            正常終了時 True
        """
        self.app.metrics_manager.start_session()

        while not self.app.should_terminate:
            start_time = time.time()

            self._do_work()

            # 巡回完了後、チャート画像生成が必要なら実行
            if self._should_generate_charts():
                self._generate_chart_images()

            # 作業終了時刻を記録（スリープ前）
            self.app.metrics_manager.record_work_ended(time.time())

            # コンテンツ更新をクライアントに通知
            my_lib.webapp.event.notify_event(my_lib.webapp.event.EVENT_TYPE.CONTENT)

            if self.app.should_terminate:
                break

            self._sleep_until(start_time + self.app.config.check.interval_sec)
            self._loop += 1

            # 次のサイクル開始前にセッションを更新
            if not self.app.should_terminate:
                self.app.metrics_manager.end_session("normal")
                self.app.metrics_manager.start_session()
                # 巡回再開を記録（work_ended_at をクリア）
                self.app.metrics_manager.record_work_started()

        # 最終セッションを終了
        self.app.metrics_manager.end_session("terminated")

        logging.warning("Terminate crawl")
        self.app.shutdown()

        return True

    def _should_generate_charts(self) -> bool:
        """チャート画像生成が必要かどうかを判定.

        3時間経過していれば True を返す。
        """
        now = time.time()
        elapsed = now - self._last_chart_generation_time
        return elapsed >= price_watch.const.CHART_GENERATION_INTERVAL_SEC

    def _generate_chart_images(self) -> None:
        """全アイテムのチャート画像を ChartImageWorker 経由で生成."""
        logging.info("Starting background chart image generation...")

        worker = price_watch.chart_image_worker.get_worker()
        if worker is None:
            logging.warning("ChartImageWorker not initialized, skipping chart generation")
            return

        # 通貨換算レートを構築
        currency_rates: dict[str, float] = {}
        if self.app.config.check.currency:
            for cr in self.app.config.check.currency:
                currency_rates[cr.label] = cr.rate

        try:
            # 全アイテムのチャートデータを収集
            chart_data_list = self._collect_chart_data(currency_rates)

            # ワーカーにバッチ投入
            added = worker.submit_batch(
                chart_data_list,
                should_terminate=lambda: self.app.should_terminate,
            )
            logging.info("Submitted %d chart generation requests to worker", added)
        except Exception:
            logging.exception("Failed to submit chart generation requests")

        # 生成時刻を更新
        self._last_chart_generation_time = time.time()

    def _collect_chart_data(
        self, currency_rates: dict[str, float]
    ) -> list[price_watch.chart_image.ChartData]:
        """全アイテムのチャートデータを収集."""
        db_path = self.app.config.data.price
        target_config = self.app.config_manager.target

        # ストア定義を取得（色情報用）
        store_definitions = [
            price_watch.chart_image.StoreDefinition(name=s.name, color=s.color) for s in target_config.stores
        ]

        # 全アイテムを取得
        manager = price_watch.managers.history.HistoryManager.create(db_path)
        manager.initialize()
        all_items = manager.get_all_items()

        if not all_items:
            return []

        # 商品名でグループ化して重複を除去
        unique_names: set[str] = set()
        chart_data_list: list[price_watch.chart_image.ChartData] = []

        for item in all_items:
            if item.name in unique_names:
                continue
            unique_names.add(item.name)

            # アイテムデータを取得
            result = price_watch.chart_image._get_item_data_from_db(
                item.item_key, db_path, target_config, currency_rates
            )
            if result[0] is None:
                continue

            item_name: str = result[0]
            stores_data: list[price_watch.chart_image.StoreChartData] = result[1]

            if not stores_data:
                continue

            chart_data = price_watch.chart_image.ChartData(
                item_name=item_name,
                item_key=item.item_key,
                stores=stores_data,
                store_definitions=store_definitions,
            )
            chart_data_list.append(chart_data)

        return chart_data_list

    def _do_work(self) -> None:
        """監視処理を実行."""
        item_list = self._load_item_list()
        self.processor.loop = self._loop
        self.processor.process_all(item_list)

    def _load_item_list(self) -> list[ResolvedItem]:
        """監視対象アイテムリストを読み込む."""
        items, diff = self.app.get_resolved_items()

        # target.yaml の変更を通知
        self._notify_target_changes(diff)

        # エラーカウントを初期化
        for item in items:
            if item.check_method in price_watch.target.FLEA_MARKET_CHECK_METHODS:
                # フリマ検索の場合は item_key を使用
                search_keyword = item.search_keyword or item.name
                item_key = price_watch.managers.history.generate_item_key(
                    search_keyword=search_keyword,
                    search_cond="",
                    store_name=item.store,
                )
                if item_key not in self.processor.error_count:
                    self.processor.error_count[item_key] = 0
            else:
                if item.url not in self.processor.error_count:
                    self.processor.error_count[item.url] = 0

        return items

    def _notify_target_changes(self, diff: TargetDiff | None) -> None:
        """target.yaml の変更を通知.

        Args:
            diff: 差分情報（初回読み込み時は None）
        """
        if diff is None or not diff.has_changes():
            return

        # 変更内容をログ出力
        logging.info(
            "target.yaml changed: added=%d, removed=%d, changed=%d",
            len(diff.added),
            len(diff.removed),
            len(diff.changed),
        )

        # Slack 通知（target_changed 内で SlackEmptyConfig チェックを行う）
        price_watch.notify.target_changed(self.app.config.slack, diff)

    def _sleep_until(self, end_time: float) -> None:
        """指定時刻までスリープ.

        threading.Event.wait() を使用することで、シグナル受信時に即座に終了できる。
        """
        sleep_remain = end_time - time.time()
        logging.info("sleep %d sec...", int(sleep_remain))

        while True:
            self.app.update_liveness()

            if self.app.should_terminate:
                return

            sleep_remain = end_time - time.time()
            if sleep_remain < 0:
                return
            elif sleep_remain < price_watch.const.SLEEP_UNIT:
                if self.app.wait_for_terminate(timeout=sleep_remain):
                    return
            else:
                if self.app.wait_for_terminate(timeout=price_watch.const.SLEEP_UNIT):
                    return


def run(
    config_file: pathlib.Path,
    target_file: pathlib.Path,
    port: int,
    *,
    debug_mode: bool = False,
    item_filter: str | None = None,
    store_filter: str | None = None,
) -> None:
    """価格監視を実行.

    Args:
        config_file: 設定ファイルパス
        target_file: ターゲット設定ファイルパス
        port: WebUI ポート番号
        debug_mode: デバッグモード
        item_filter: 商品名フィルター（部分一致）
        store_filter: ストア名フィルター（部分一致）
    """
    # アプリケーションコンテキストを作成
    app = price_watch.app_context.PriceWatchApp.create(
        config_file=config_file,
        target_file=target_file,
        port=port,
        debug_mode=debug_mode,
        item_filter=item_filter,
        store_filter=store_filter,
    )

    # シグナルハンドラを設定
    app.setup_signal_handlers()

    # デバッグモードでは WebUI サーバーを起動しない
    if not debug_mode:
        app.start_webui_server()

    # 実行
    runner = AppRunner(app=app)
    try:
        success = runner.execute()
        if success:
            sys.exit(0)
        else:
            sys.exit(1)
    except KeyboardInterrupt:
        logging.info("Received KeyboardInterrupt, shutting down...")
        app.shutdown()
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
    item_filter: str | None = args["--item"]
    store_filter: str | None = args["--store"]

    # --item や --store を指定した場合は自動的にデバッグモードにする
    if item_filter or store_filter:
        debug_mode = True

    log_level = logging.DEBUG if debug_mode else logging.INFO
    my_lib.logger.init("bot.price_watch", level=log_level)

    logging.info("Start.")
    logging.info("Using config: %s", config_file)
    logging.info("Using target: %s", target_file)
    if item_filter:
        logging.info("Item filter: %s", item_filter)
    if store_filter:
        logging.info("Store filter: %s", store_filter)

    run(
        config_file,
        target_file,
        port,
        debug_mode=debug_mode,
        item_filter=item_filter,
        store_filter=store_filter,
    )


if __name__ == "__main__":
    main()
