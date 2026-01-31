"""特定アイテムの動作確認ジョブ管理.

アイテムの価格チェックを非同期で実行し、SSE でリアルタイムに進捗を返す。
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
import uuid
from collections.abc import Generator
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from flask import Blueprint, Response, current_app, jsonify, request

if TYPE_CHECKING:
    from price_watch.app_context import PriceWatchApp

check_job_bp = Blueprint("check_job", __name__, url_prefix="/api/target")


class JobStatus(str, Enum):
    """ジョブステータス."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class JobMessage:
    """SSE メッセージ."""

    type: str  # "log", "progress", "result", "error", "done"
    data: dict


@dataclass
class CheckJob:
    """価格チェックジョブ."""

    job_id: str
    item_name: str
    store_name: str
    status: JobStatus = JobStatus.PENDING
    message_queue: queue.Queue[JobMessage] = field(default_factory=queue.Queue)
    result: dict | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)


# ジョブストア（メモリ内）
_jobs: dict[str, CheckJob] = {}
_jobs_lock = threading.Lock()

# 同時実行制限
_running_job: str | None = None
_running_lock = threading.Lock()

# ジョブの保持時間（秒）
JOB_RETENTION_SECONDS = 3600


def _cleanup_old_jobs() -> None:
    """古いジョブを削除."""
    now = time.time()
    with _jobs_lock:
        expired = [job_id for job_id, job in _jobs.items() if now - job.created_at > JOB_RETENTION_SECONDS]
        for job_id in expired:
            del _jobs[job_id]


def _run_check_job(
    app: PriceWatchApp,
    job: CheckJob,
    item_config: dict,
    store_config: dict,
) -> None:
    """価格チェックを実行するワーカー."""
    import price_watch.store.amazon.paapi as paapi
    import price_watch.store.flea_market as flea_market
    import price_watch.store.scrape as scrape
    import price_watch.store.yahoo as yahoo
    from price_watch.models import CrawlStatus, StockStatus
    from price_watch.target import CheckMethod, ResolvedItem, StoreDefinition

    global _running_job

    logger = logging.getLogger(__name__)

    try:
        job.status = JobStatus.RUNNING
        job.message_queue.put(
            JobMessage(type="log", data={"message": f"チェック開始: {job.item_name} @ {job.store_name}"})
        )

        # ストア定義を構築
        store_def = StoreDefinition.parse(store_config)
        job.message_queue.put(
            JobMessage(type="log", data={"message": f"ストア設定: check_method={store_def.check_method}"})
        )

        # アイテム URL を取得
        store_entry = next(
            (s for s in item_config.get("store", []) if s.get("name") == job.store_name),
            None,
        )
        if not store_entry:
            raise ValueError(f"ストアエントリが見つかりません: {job.store_name}")

        url = store_entry.get("url", "")
        asin = store_entry.get("asin")
        search_keyword = store_entry.get("search_keyword") or item_config.get("name", "")
        exclude_keyword = store_entry.get("exclude_keyword")
        jan_code = store_entry.get("jan_code")
        cond = store_entry.get("cond") or item_config.get("cond")
        price_range = store_entry.get("price") or item_config.get("price")

        # preload 設定の取得
        preload = None
        preload_data = store_entry.get("preload")
        if preload_data:
            from price_watch.target import PreloadConfig

            preload = PreloadConfig.parse(preload_data)

        job.message_queue.put(
            JobMessage(type="log", data={"message": f"URL: {url or '(なし)'}, ASIN: {asin or '(なし)'}"})
        )

        # ResolvedItem を構築
        resolved_item = ResolvedItem(
            name=item_config.get("name", ""),
            store=store_def.name,
            url=url or "",
            asin=asin,
            check_method=store_def.check_method,
            price_xpath=store_entry.get("price_xpath") or store_def.price_xpath,
            thumb_img_xpath=store_entry.get("thumb_img_xpath") or store_def.thumb_img_xpath,
            unavailable_xpath=store_entry.get("unavailable_xpath") or store_def.unavailable_xpath,
            price_unit=store_def.price_unit,
            point_rate=store_def.point_rate,
            color=store_def.color,
            actions=store_def.actions,
            preload=preload,
            search_keyword=search_keyword,
            exclude_keyword=exclude_keyword,
            price_range=price_range,
            cond=cond,
            jan_code=jan_code,
            category=item_config.get("category"),
        )

        job.message_queue.put(
            JobMessage(type="progress", data={"step": "checking", "message": "価格チェック実行中..."})
        )

        # チェック方法に応じた処理
        config = app.config_manager.config
        driver = app.browser_manager.driver

        if resolved_item.check_method == CheckMethod.SCRAPE:
            if driver is None:
                raise RuntimeError("WebDriver が初期化されていません")
            result = scrape.check(
                config,
                driver,
                resolved_item,
                loop=0,
            )

            job.message_queue.put(
                JobMessage(type="log", data={"message": f"チェック結果: crawl_status={result.crawl_status}"})
            )

            job.result = {
                "price": result.price,
                "stock": result.stock.value if result.stock else StockStatus.UNKNOWN.value,
                "thumb_url": result.thumb_url,
                "crawl_status": result.crawl_status.value,
            }
            job.message_queue.put(JobMessage(type="result", data=job.result))

        elif resolved_item.check_method == CheckMethod.AMAZON_PAAPI:
            results = paapi.check_item_list(config, [resolved_item])

            if results:
                result = results[0]
                job.result = {
                    "price": result.price,
                    "stock": result.stock.value if result.stock else StockStatus.UNKNOWN.value,
                    "thumb_url": result.thumb_url,
                    "crawl_status": result.crawl_status.value,
                }
            else:
                job.result = {
                    "price": None,
                    "stock": StockStatus.UNKNOWN.value,
                    "thumb_url": None,
                    "crawl_status": CrawlStatus.FAILURE.value,
                }
            job.message_queue.put(JobMessage(type="result", data=job.result))

        elif resolved_item.check_method in (
            CheckMethod.MERCARI_SEARCH,
            CheckMethod.RAKUMA_SEARCH,
            CheckMethod.PAYPAY_SEARCH,
        ):
            if driver is None:
                raise RuntimeError("WebDriver が初期化されていません")
            result = flea_market.check(config, driver, resolved_item)

            job.result = {
                "price": result.price,
                "stock": result.stock.value if result.stock else StockStatus.UNKNOWN.value,
                "thumb_url": result.thumb_url,
                "crawl_status": result.crawl_status.value,
            }
            job.message_queue.put(JobMessage(type="result", data=job.result))

        elif resolved_item.check_method == CheckMethod.YAHOO_SEARCH:
            result = yahoo.check(config, resolved_item)

            job.result = {
                "price": result.price,
                "stock": result.stock.value if result.stock else StockStatus.UNKNOWN.value,
                "thumb_url": result.thumb_url,
                "crawl_status": result.crawl_status.value,
            }
            job.message_queue.put(JobMessage(type="result", data=job.result))

        else:
            raise ValueError(f"未対応のチェック方法: {resolved_item.check_method}")

        job.status = JobStatus.COMPLETED
        job.message_queue.put(JobMessage(type="done", data={"status": "completed"}))

    except Exception as e:
        logger.exception("チェックジョブでエラー発生")
        job.status = JobStatus.FAILED
        job.error = str(e)
        job.message_queue.put(JobMessage(type="error", data={"message": str(e)}))
        job.message_queue.put(JobMessage(type="done", data={"status": "failed"}))

    finally:
        with _running_lock:
            global _running_job
            _running_job = None


@check_job_bp.route("/check-item", methods=["POST"])
def start_check_item():
    """特定アイテムの価格チェックを開始."""
    global _running_job

    _cleanup_old_jobs()

    # 同時実行チェック
    with _running_lock:
        if _running_job is not None:
            return (
                jsonify(
                    {
                        "error": "別のチェックが実行中です",
                        "running_job_id": _running_job,
                    }
                ),
                409,
            )

    data = request.get_json()
    if not data:
        return jsonify({"error": "リクエストボディが必要です"}), 400

    item_config = data.get("item")
    store_name = data.get("store_name")
    store_config = data.get("store_config")

    if not item_config or not store_name or not store_config:
        return jsonify({"error": "item, store_name, store_config が必要です"}), 400

    # ジョブ作成
    job_id = str(uuid.uuid4())
    job = CheckJob(
        job_id=job_id,
        item_name=item_config.get("name", ""),
        store_name=store_name,
    )

    with _jobs_lock:
        _jobs[job_id] = job

    with _running_lock:
        _running_job = job_id

    # アプリケーションコンテキストを取得
    price_watch_app = current_app.config.get("PRICE_WATCH_APP")
    if price_watch_app is None:
        with _running_lock:
            _running_job = None
        return jsonify({"error": "アプリケーションが初期化されていません"}), 500

    # ワーカースレッドで実行
    thread = threading.Thread(
        target=_run_check_job,
        args=(price_watch_app, job, item_config, store_config),
        daemon=True,
    )
    thread.start()

    return jsonify({"job_id": job_id})


@check_job_bp.route("/check-item/<job_id>/stream", methods=["GET"])
def stream_check_item_progress(job_id: str):
    """価格チェックの進捗を SSE でストリーミング."""
    with _jobs_lock:
        job = _jobs.get(job_id)

    if not job:
        return jsonify({"error": "ジョブが見つかりません"}), 404

    def generate() -> Generator[str, None, None]:
        """SSE イベントを生成."""
        while True:
            try:
                msg = job.message_queue.get(timeout=30)
                yield f"event: {msg.type}\ndata: {json.dumps(msg.data, ensure_ascii=False)}\n\n"

                if msg.type == "done":
                    break
            except queue.Empty:
                # Keep-alive
                yield ": keepalive\n\n"

                # ジョブが終了していたら終了
                if job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
                    break

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@check_job_bp.route("/check-item/<job_id>", methods=["GET"])
def get_check_item_status(job_id: str):
    """ジョブのステータスを取得."""
    with _jobs_lock:
        job = _jobs.get(job_id)

    if not job:
        return jsonify({"error": "ジョブが見つかりません"}), 404

    return jsonify(
        {
            "job_id": job.job_id,
            "item_name": job.item_name,
            "store_name": job.store_name,
            "status": job.status.value,
            "result": job.result,
            "error": job.error,
        }
    )
