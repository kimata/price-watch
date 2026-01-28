#!/usr/bin/env python3
"""メトリクス管理.

巡回セッションのメトリクスを管理します。
"""

from __future__ import annotations

import logging
import pathlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

import my_lib.time

import price_watch.metrics

if TYPE_CHECKING:
    pass


@dataclass
class MetricsManager:
    """メトリクス管理クラス.

    巡回セッションの開始・終了、ストア別統計を管理します。
    コンテキストマネージャーとして使用でき、セッションを自動的に管理します。
    """

    metrics_dir: pathlib.Path
    _db: price_watch.metrics.MetricsDB | None = field(default=None, init=False, repr=False)
    _current_session_id: int | None = field(default=None, init=False)
    _session_total_items: int = field(default=0, init=False)
    _session_success_items: int = field(default=0, init=False)
    _session_failed_items: int = field(default=0, init=False)
    _work_ended_at: float | None = field(default=None, init=False)

    def initialize(self) -> None:
        """メトリクス DB を初期化."""
        if self._db is not None:
            return

        db_path = self.metrics_dir / "metrics.db"
        logging.info("Initializing metrics database at %s", db_path)
        self._db = price_watch.metrics.MetricsDB(db_path)

    @property
    def db(self) -> price_watch.metrics.MetricsDB | None:
        """メトリクス DB を取得."""
        return self._db

    @property
    def current_session_id(self) -> int | None:
        """現在のセッション ID を取得."""
        return self._current_session_id

    def start_session(self) -> int | None:
        """巡回セッションを開始.

        Returns:
            セッション ID、または None（DB未初期化時）
        """
        if self._db is None:
            return None

        self._current_session_id = self._db.start_session()
        self._session_total_items = 0
        self._session_success_items = 0
        self._session_failed_items = 0
        self._work_ended_at = None

        logging.debug("Started session: %s", self._current_session_id)
        return self._current_session_id

    def end_session(self, exit_reason: str, *, work_ended_at: float | None = None) -> None:
        """巡回セッションを終了.

        Args:
            exit_reason: 終了理由（"normal", "terminated" など）
            work_ended_at: 作業終了時刻（Unix timestamp）。スリープ時間を除外するため。
        """
        if self._db is None or self._current_session_id is None:
            return

        # 作業終了時刻を datetime に変換
        ended_at_dt: datetime | None = None
        if work_ended_at is not None:
            ended_at_dt = datetime.fromtimestamp(work_ended_at, tz=my_lib.time.now().tzinfo)
        elif self._work_ended_at is not None:
            ended_at_dt = datetime.fromtimestamp(self._work_ended_at, tz=my_lib.time.now().tzinfo)

        self._db.end_session(
            self._current_session_id,
            self._session_total_items,
            self._session_success_items,
            self._session_failed_items,
            exit_reason,
            work_ended_at=ended_at_dt,
        )

        logging.debug(
            "Ended session %s: total=%d, success=%d, failed=%d",
            self._current_session_id,
            self._session_total_items,
            self._session_success_items,
            self._session_failed_items,
        )

        self._current_session_id = None
        self._work_ended_at = None

    def record_work_ended(self, timestamp: float) -> None:
        """作業終了時刻を記録し、DB に即時反映.

        Args:
            timestamp: Unix timestamp
        """
        self._work_ended_at = timestamp
        if self._db is not None and self._current_session_id is not None:
            self._db.update_work_ended_at(self._current_session_id)

    def record_work_started(self) -> None:
        """作業開始を記録し、DB の work_ended_at をクリア."""
        self._work_ended_at = None
        if self._db is not None and self._current_session_id is not None:
            self._db.clear_work_ended_at(self._current_session_id)

    def record_item_result(self, *, success: bool) -> None:
        """アイテムの巡回結果を記録.

        Args:
            success: 成功時 True
        """
        self._session_total_items += 1
        if success:
            self._session_success_items += 1
        else:
            self._session_failed_items += 1

    def update_heartbeat(self) -> None:
        """ハートビートを更新（現在のアイテムカウントも含む）."""
        if self._db is not None and self._current_session_id is not None:
            self._db.update_heartbeat(
                self._current_session_id,
                total_items=self._session_total_items,
                success_items=self._session_success_items,
                failed_items=self._session_failed_items,
            )

    def start_store_crawl(self, store_name: str) -> int | None:
        """ストア巡回を開始.

        Args:
            store_name: ストア名

        Returns:
            統計 ID、または None
        """
        if self._db is None or self._current_session_id is None:
            return None
        return self._db.start_store_crawl(self._current_session_id, store_name)

    def end_store_crawl(
        self,
        stats_id: int | None,
        item_count: int,
        success_count: int,
        failed_count: int,
    ) -> None:
        """ストア巡回を終了.

        Args:
            stats_id: 統計 ID
            item_count: アイテム数
            success_count: 成功数
            failed_count: 失敗数
        """
        if self._db is None or stats_id is None:
            return
        self._db.end_store_crawl(stats_id, item_count, success_count, failed_count)


@dataclass
class StoreContext:
    """ストア巡回コンテキスト.

    ストア巡回を自動的に開始・終了するコンテキストマネージャー。
    """

    metrics: MetricsManager
    store_name: str
    _stats_id: int | None = field(default=None, init=False)
    _item_count: int = field(default=0, init=False)
    _success_count: int = field(default=0, init=False)
    _failed_count: int = field(default=0, init=False)

    def __enter__(self) -> StoreContext:
        """コンテキストに入る."""
        self._stats_id = self.metrics.start_store_crawl(self.store_name)
        return self

    def __exit__(
        self,
        _exc_type: type | None,
        _exc_val: Exception | None,
        _exc_tb: object,
    ) -> None:
        """コンテキストを終了."""
        self.metrics.end_store_crawl(
            self._stats_id,
            self._item_count,
            self._success_count,
            self._failed_count,
        )

    def record_success(self) -> None:
        """成功を記録."""
        self._item_count += 1
        self._success_count += 1
        self.metrics.record_item_result(success=True)

    def record_failure(self) -> None:
        """失敗を記録."""
        self._item_count += 1
        self._failed_count += 1
        self.metrics.record_item_result(success=False)
