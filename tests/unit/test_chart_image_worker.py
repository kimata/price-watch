#!/usr/bin/env python3
# ruff: noqa: S101
"""chart_image_worker モジュールのユニットテスト."""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

import price_watch.chart_image
import price_watch.chart_image_worker


@pytest.fixture
def chart_data() -> price_watch.chart_image.ChartData:
    """サンプルのチャートデータを生成."""
    return price_watch.chart_image.ChartData(item_name="Item", item_key="key1", stores=[])


@pytest.fixture
def worker(tmp_path: pathlib.Path) -> price_watch.chart_image_worker.ChartImageWorker:
    """ワーカーを生成（スレッドは開始しない）."""
    return price_watch.chart_image_worker.ChartImageWorker(cache_dir=tmp_path, data_path=tmp_path)


def _create_valid_cache(tmp_path: pathlib.Path) -> pathlib.Path:
    cache_path = price_watch.chart_image.get_cache_path("key1", tmp_path)
    cache_path.write_bytes(b"dummy")
    return cache_path


class TestSubmitBatch:
    """submit_batch のテスト."""

    def test_skips_valid_cache(
        self,
        worker: price_watch.chart_image_worker.ChartImageWorker,
        chart_data: price_watch.chart_image.ChartData,
        tmp_path: pathlib.Path,
    ) -> None:
        """有効なキャッシュがあればスキップする."""
        _create_valid_cache(tmp_path)

        assert worker.submit_batch([chart_data]) == 0
        assert worker._request_queue.empty()

    def test_force_enqueues_valid_cache(
        self,
        worker: price_watch.chart_image_worker.ChartImageWorker,
        chart_data: price_watch.chart_image.ChartData,
        tmp_path: pathlib.Path,
    ) -> None:
        """force=True なら有効なキャッシュがあってもキューに追加する."""
        _create_valid_cache(tmp_path)

        assert worker.submit_batch([chart_data], force=True) == 1
        _, _, request = worker._request_queue.get_nowait()
        assert request.force is True


class TestProcessRequest:
    """_process_request のテスト."""

    def _process(
        self,
        worker: price_watch.chart_image_worker.ChartImageWorker,
        chart_data: price_watch.chart_image.ChartData,
        force: bool,
    ) -> MagicMock:
        request = price_watch.chart_image_worker.ChartRequest(
            item_key=chart_data.item_key,
            chart_data=chart_data,
            priority=price_watch.chart_image_worker.RequestPriority.LOW,
            force=force,
        )
        with (
            patch.object(worker, "_ensure_browser", return_value=MagicMock()),
            patch(
                "price_watch.chart_image.generate_chart_image",
                return_value=Image.new("RGB", (4, 4)),
            ) as mock_generate,
        ):
            worker._process_request(request)

        assert request.result_event.is_set()
        assert request.error is None
        return mock_generate

    def test_skips_generation_for_valid_cache(
        self,
        worker: price_watch.chart_image_worker.ChartImageWorker,
        chart_data: price_watch.chart_image.ChartData,
        tmp_path: pathlib.Path,
    ) -> None:
        """有効なキャッシュがあれば生成しない."""
        cache_path = _create_valid_cache(tmp_path)

        mock_generate = self._process(worker, chart_data, force=False)

        mock_generate.assert_not_called()
        assert cache_path.read_bytes() == b"dummy"

    def test_force_regenerates_valid_cache(
        self,
        worker: price_watch.chart_image_worker.ChartImageWorker,
        chart_data: price_watch.chart_image.ChartData,
        tmp_path: pathlib.Path,
    ) -> None:
        """force=True なら有効なキャッシュがあっても再生成する."""
        cache_path = _create_valid_cache(tmp_path)

        mock_generate = self._process(worker, chart_data, force=True)

        mock_generate.assert_called_once()
        assert cache_path.read_bytes() != b"dummy"
