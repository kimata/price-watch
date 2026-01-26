#!/usr/bin/env python3
# ruff: noqa: S101
"""
cli/healthz.py のユニットテスト

Liveness チェックを検証します。
"""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock, patch

import pytest

import price_watch.cli.healthz


class TestMain:
    """main 関数のテスト"""

    def test_success_with_healthy_state(self, tmp_path: pathlib.Path) -> None:
        """正常状態では成功"""
        mock_args = {
            "-c": str(tmp_path / "config.yaml"),
            "-D": False,
        }

        mock_config = MagicMock()
        mock_config.liveness.file.crawler = tmp_path / "healthz"
        mock_config.liveness.interval_sec = 300
        mock_config.data.metrics = tmp_path

        mock_status = MagicMock()
        mock_status.is_running = True
        mock_status.session_id = 1
        mock_status.uptime_sec = 3600
        mock_status.total_items = 10
        mock_status.success_items = 8
        mock_status.failed_items = 2

        mock_db = MagicMock()
        mock_db.is_crawler_healthy.return_value = True
        mock_db.get_current_session_status.return_value = mock_status

        with (
            patch("docopt.docopt", return_value=mock_args),
            patch("my_lib.logger.init"),
            patch("price_watch.config.load", return_value=mock_config),
            patch("my_lib.healthz.check_liveness_all", return_value=[]),
            patch("price_watch.metrics.MetricsDB", return_value=mock_db),
            patch.object(pathlib.Path, "exists", return_value=True),
            pytest.raises(SystemExit) as exc_info,
        ):
            price_watch.cli.healthz.main()

        assert exc_info.value.code == 0

    def test_fails_on_liveness_check_failure(self, tmp_path: pathlib.Path) -> None:
        """liveness チェック失敗時は失敗"""
        mock_args = {
            "-c": str(tmp_path / "config.yaml"),
            "-D": False,
        }

        mock_config = MagicMock()
        mock_config.liveness.file.crawler = tmp_path / "healthz"
        mock_config.liveness.interval_sec = 300
        mock_config.data.metrics = tmp_path

        with (
            patch("docopt.docopt", return_value=mock_args),
            patch("my_lib.logger.init"),
            patch("price_watch.config.load", return_value=mock_config),
            patch("my_lib.healthz.check_liveness_all", return_value=["price-watch"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            price_watch.cli.healthz.main()

        assert exc_info.value.code == 1

    def test_fails_on_unhealthy_crawler(self, tmp_path: pathlib.Path) -> None:
        """クローラーが不健全な場合は失敗"""
        mock_args = {
            "-c": str(tmp_path / "config.yaml"),
            "-D": False,
        }

        mock_config = MagicMock()
        mock_config.liveness.file.crawler = tmp_path / "healthz"
        mock_config.liveness.interval_sec = 300
        mock_config.data.metrics = tmp_path

        mock_db = MagicMock()
        mock_db.is_crawler_healthy.return_value = False

        with (
            patch("docopt.docopt", return_value=mock_args),
            patch("my_lib.logger.init"),
            patch("price_watch.config.load", return_value=mock_config),
            patch("my_lib.healthz.check_liveness_all", return_value=[]),
            patch("price_watch.metrics.MetricsDB", return_value=mock_db),
            patch.object(pathlib.Path, "exists", return_value=True),
            pytest.raises(SystemExit) as exc_info,
        ):
            price_watch.cli.healthz.main()

        assert exc_info.value.code == 1

    def test_skips_metrics_check_if_db_not_exists(self, tmp_path: pathlib.Path) -> None:
        """メトリクス DB がない場合はスキップ"""
        mock_args = {
            "-c": str(tmp_path / "config.yaml"),
            "-D": False,
        }

        mock_config = MagicMock()
        mock_config.liveness.file.crawler = tmp_path / "healthz"
        mock_config.liveness.interval_sec = 300
        metrics_path = tmp_path / "metrics"
        mock_config.data.metrics = metrics_path

        with (
            patch("docopt.docopt", return_value=mock_args),
            patch("my_lib.logger.init"),
            patch("price_watch.config.load", return_value=mock_config),
            patch("my_lib.healthz.check_liveness_all", return_value=[]),
            pytest.raises(SystemExit) as exc_info,
        ):
            price_watch.cli.healthz.main()

        # メトリクス DB がなくても成功
        assert exc_info.value.code == 0
