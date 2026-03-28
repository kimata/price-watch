#!/usr/bin/env python3
"""チャート画像生成ワーカー.

単一スレッドでチャート画像生成を行い、Chrome プロファイルの競合を防ぐ。
Flask リクエストとバックグラウンド生成の両方がこのワーカー経由で画像を取得する。
"""

from __future__ import annotations

import logging
import pathlib
import queue
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

import price_watch.chart_image

if TYPE_CHECKING:
    from collections.abc import Callable

    from selenium.webdriver.remote.webdriver import WebDriver


class RequestPriority(Enum):
    """リクエストの優先度."""

    HIGH = auto()  # Flask リクエスト（ユーザー待機中）
    LOW = auto()  # バックグラウンド生成


@dataclass
class ChartRequest:
    """チャート画像生成リクエスト."""

    item_key: str
    chart_data: price_watch.chart_image.ChartData
    priority: RequestPriority
    result_event: threading.Event = field(default_factory=threading.Event)
    result_path: pathlib.Path | None = field(default=None)
    error: Exception | None = field(default=None)

    def __lt__(self, other: ChartRequest) -> bool:
        """優先度比較（PriorityQueue 用）."""
        # HIGH (1) < LOW (2) なので、HIGH が先に処理される
        return self.priority.value < other.priority.value


class ChartImageWorker:
    """チャート画像生成ワーカー.

    単一スレッドで画像生成を行い、Chrome インスタンスを1つだけ保持する。

    Usage:
        worker = ChartImageWorker(cache_dir, data_path)
        worker.start()

        # Flask リクエストから
        path = worker.request_chart(chart_data, timeout=10.0)

        # バックグラウンド生成から
        worker.submit_batch(chart_data_list)

        worker.stop()
    """

    def __init__(
        self,
        cache_dir: pathlib.Path,
        data_path: pathlib.Path,
        font_family: str | None = None,
        ttl_sec: int = price_watch.chart_image.CACHE_TTL_SEC,
    ) -> None:
        """初期化.

        Args:
            cache_dir: キャッシュディレクトリ
            data_path: Chrome データディレクトリ
            font_family: CSS font-family 名
            ttl_sec: キャッシュ有効期間（秒）
        """
        self._cache_dir = cache_dir
        self._data_path = data_path
        self._font_family = font_family
        self._ttl_sec = ttl_sec

        self._request_queue: queue.PriorityQueue[tuple[int, float, ChartRequest]] = queue.PriorityQueue()
        self._worker_thread: threading.Thread | None = None
        self._driver: WebDriver | None = None
        self._should_stop = threading.Event()
        self._is_running = False
        self._lock = threading.Lock()

        # 処理中のリクエストを追跡（重複リクエスト対応）
        self._pending_requests: dict[str, ChartRequest] = {}
        self._pending_lock = threading.Lock()

    def start(self) -> None:
        """ワーカースレッドを開始."""
        with self._lock:
            if self._is_running:
                return

            self._should_stop.clear()
            self._worker_thread = threading.Thread(
                target=self._worker_loop,
                name="ChartImageWorker",
                daemon=True,
            )
            self._worker_thread.start()
            self._is_running = True
            logging.info("ChartImageWorker started")

    def stop(self, timeout: float = 10.0) -> None:
        """ワーカースレッドを停止.

        Args:
            timeout: 停止待機タイムアウト（秒）
        """
        with self._lock:
            if not self._is_running:
                return

            logging.info("Stopping ChartImageWorker...")
            self._should_stop.set()

            if self._worker_thread is not None:
                self._worker_thread.join(timeout=timeout)
                if self._worker_thread.is_alive():
                    logging.warning("ChartImageWorker did not stop within timeout")

            self._is_running = False
            logging.info("ChartImageWorker stopped")

    def request_chart(
        self,
        chart_data: price_watch.chart_image.ChartData,
        timeout: float = 30.0,
    ) -> pathlib.Path | None:
        """チャート画像を要求（同期、Flask リクエスト用）.

        キャッシュがあれば即座に返し、なければ生成を待つ。

        Args:
            chart_data: チャートデータ
            timeout: タイムアウト（秒）

        Returns:
            画像ファイルのパス（タイムアウト時は None）
        """
        item_key = chart_data.item_key

        # キャッシュチェック
        cache_path = price_watch.chart_image.get_cache_path(item_key, self._cache_dir)
        if price_watch.chart_image.is_cache_valid(cache_path, self._ttl_sec):
            return cache_path

        # 既に同じリクエストが処理中か確認し、なければ新規作成（1回のロックで完結）
        request: ChartRequest | None = None
        existing_request: ChartRequest | None = None
        with self._pending_lock:
            if item_key in self._pending_requests:
                existing_request = self._pending_requests[item_key]
            else:
                request = ChartRequest(
                    item_key=item_key,
                    chart_data=chart_data,
                    priority=RequestPriority.HIGH,
                )
                self._pending_requests[item_key] = request

        # 既存リクエストがある場合はロックの外で完了を待つ
        # NOTE: ロック保持中に wait すると Worker の finally ブロックが
        # _pending_lock を取得できずデッドロックになる
        if existing_request is not None:
            if existing_request.result_event.wait(timeout=timeout):
                if existing_request.error is not None:
                    logging.warning("Chart generation failed for %s: %s", item_key, existing_request.error)
                    return None
                return existing_request.result_path
            logging.warning("Chart generation timed out for %s", item_key)
            return None

        assert request is not None  # noqa: S101

        # キューに追加
        self._enqueue(request)

        # 結果を待つ
        if request.result_event.wait(timeout=timeout):
            if request.error is not None:
                logging.warning("Chart generation failed for %s: %s", item_key, request.error)
                return None
            return request.result_path

        logging.warning("Chart generation timed out for %s", item_key)
        return None

    def submit_batch(
        self,
        chart_data_list: list[price_watch.chart_image.ChartData],
        should_terminate: Callable[[], bool] | None = None,
    ) -> int:
        """バッチでチャート画像生成をキューに追加（バックグラウンド用）.

        キャッシュが有効なものはスキップし、無効なもののみキューに追加。

        Args:
            chart_data_list: チャートデータのリスト
            should_terminate: 終了判定コールバック

        Returns:
            キューに追加したリクエスト数
        """
        added = 0
        for chart_data in chart_data_list:
            if should_terminate is not None and should_terminate():
                break

            item_key = chart_data.item_key
            cache_path = price_watch.chart_image.get_cache_path(item_key, self._cache_dir)

            # キャッシュが有効ならスキップ
            if price_watch.chart_image.is_cache_valid(cache_path, self._ttl_sec):
                continue

            # 既に処理中ならスキップ
            with self._pending_lock:
                if item_key in self._pending_requests:
                    continue

                request = ChartRequest(
                    item_key=item_key,
                    chart_data=chart_data,
                    priority=RequestPriority.LOW,
                )
                self._pending_requests[item_key] = request

            self._enqueue(request)
            added += 1

        logging.info("Submitted %d chart generation requests to queue", added)
        return added

    def _enqueue(self, request: ChartRequest) -> None:
        """リクエストをキューに追加."""
        # (priority, timestamp, request) のタプルでキューに追加
        # timestamp を入れることで同じ優先度内での FIFO を保証
        self._request_queue.put((request.priority.value, time.time(), request))

    def _worker_loop(self) -> None:
        """ワーカースレッドのメインループ."""
        logging.info("ChartImageWorker loop started")

        try:
            while not self._should_stop.is_set():
                try:
                    # タイムアウト付きでキューから取得（停止シグナルをチェックするため）
                    _, _, request = self._request_queue.get(timeout=1.0)
                except queue.Empty:
                    continue

                self._process_request(request)

        finally:
            # ドライバーを終了
            self._quit_driver()
            logging.info("ChartImageWorker loop ended")

    def _process_request(self, request: ChartRequest) -> None:
        """リクエストを処理."""
        item_key = request.item_key

        try:
            # キャッシュを再チェック（キュー待機中に生成された可能性）
            cache_path = price_watch.chart_image.get_cache_path(item_key, self._cache_dir)
            if price_watch.chart_image.is_cache_valid(cache_path, self._ttl_sec):
                request.result_path = cache_path
                return

            # ドライバーを確保
            driver = self._ensure_driver()
            if driver is None:
                request.error = RuntimeError("Failed to create WebDriver")
                return

            # 画像を生成
            img = price_watch.chart_image.generate_chart_image(
                request.chart_data,
                driver=driver,
                data_path=self._data_path,
                font_family=self._font_family,
            )

            # 保存
            price_watch.chart_image.save_chart_image(img, cache_path)
            request.result_path = cache_path
            logging.debug("Generated chart image for %s", item_key)

        except Exception as e:
            logging.exception("Failed to generate chart image for %s", item_key)
            request.error = e

            # エラー時はドライバーを再作成（セッション無効の可能性）
            self._quit_driver()

        finally:
            # pending から削除
            with self._pending_lock:
                self._pending_requests.pop(item_key, None)

            # 完了を通知
            request.result_event.set()

    def _ensure_driver(self) -> WebDriver | None:
        """WebDriver を確保（必要に応じて作成）."""
        if self._driver is not None:
            # セッションが有効か確認
            try:
                self._driver.current_url  # noqa: B018
                return self._driver
            except Exception:
                logging.warning("Chart driver session invalid, recreating...")
                self._quit_driver()

        try:
            css_width = int(price_watch.chart_image.CHART_WIDTH / price_watch.chart_image.DEVICE_PIXEL_RATIO)
            css_height = int(
                price_watch.chart_image.CHART_HEIGHT / price_watch.chart_image.DEVICE_PIXEL_RATIO
            )
            self._driver = price_watch.chart_image._create_headless_driver(
                self._data_path,
                css_width,
                css_height,
                price_watch.chart_image.DEVICE_PIXEL_RATIO,
            )
            logging.info("Created chart image WebDriver")
            return self._driver
        except Exception:
            logging.exception("Failed to create chart image WebDriver")
            return None

    def _quit_driver(self) -> None:
        """WebDriver を終了."""
        if self._driver is not None:
            try:
                self._driver.quit()
            except Exception:
                logging.exception("Error quitting chart driver")
            self._driver = None


# グローバルワーカーインスタンス
_worker: ChartImageWorker | None = None
_worker_lock = threading.Lock()


def get_worker() -> ChartImageWorker | None:
    """グローバルワーカーインスタンスを取得."""
    return _worker


def init_worker(
    cache_dir: pathlib.Path,
    data_path: pathlib.Path,
    font_family: str | None = None,
    ttl_sec: int = price_watch.chart_image.CACHE_TTL_SEC,
) -> ChartImageWorker:
    """グローバルワーカーを初期化して開始.

    Args:
        cache_dir: キャッシュディレクトリ
        data_path: Chrome データディレクトリ
        font_family: CSS font-family 名
        ttl_sec: キャッシュ有効期間（秒）

    Returns:
        初期化されたワーカー
    """
    global _worker

    with _worker_lock:
        if _worker is not None:
            return _worker

        worker = ChartImageWorker(
            cache_dir=cache_dir,
            data_path=data_path,
            font_family=font_family,
            ttl_sec=ttl_sec,
        )
        worker.start()
        _worker = worker
        return worker


def stop_worker() -> None:
    """グローバルワーカーを停止."""
    global _worker

    with _worker_lock:
        if _worker is not None:
            _worker.stop()
            _worker = None
