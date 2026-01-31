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

import price_watch.webapi.cache

if TYPE_CHECKING:
    from price_watch.app_context import PriceWatchApp
    from price_watch.target import ItemDefinition, StoreDefinition

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


def _find_item_in_target(
    item_name: str,
    store_name: str,
) -> tuple[ItemDefinition, StoreDefinition] | None:
    """target.yaml から保存済みアイテムとストア定義を検索.

    Args:
        item_name: アイテム名
        store_name: ストア名

    Returns:
        (ItemDefinition, StoreDefinition) のタプル。見つからない場合は None。
    """
    target_config = price_watch.webapi.cache.get_target_config()
    if target_config is None:
        return None

    # ストア定義を検索
    store_def = target_config.get_store(store_name)
    if store_def is None:
        return None

    # アイテムを検索（名前とストアの組み合わせで一致）
    for item in target_config.items:
        if item.name == item_name and item.store == store_name:
            return item, store_def

    return None


def _run_check_job(
    app: PriceWatchApp,
    job: CheckJob,
    item_def: ItemDefinition,
    store_def: StoreDefinition,
) -> None:
    """価格チェックを実行するワーカー.

    Args:
        app: アプリケーションコンテキスト
        job: チェックジョブ
        item_def: target.yaml から取得したアイテム定義
        store_def: target.yaml から取得したストア定義
    """
    import price_watch.store.amazon.paapi as paapi
    import price_watch.store.flea_market as flea_market
    import price_watch.store.scrape as scrape
    import price_watch.store.yahoo as yahoo
    from price_watch.models import CrawlStatus, StockStatus
    from price_watch.target import CheckMethod, ResolvedItem

    global _running_job

    logger = logging.getLogger(__name__)

    try:
        job.status = JobStatus.RUNNING
        job.message_queue.put(
            JobMessage(type="log", data={"message": f"チェック開始: {job.item_name} @ {job.store_name}"})
        )

        job.message_queue.put(
            JobMessage(type="log", data={"message": f"ストア設定: check_method={store_def.check_method}"})
        )

        job.message_queue.put(
            JobMessage(
                type="log",
                data={"message": f"URL: {item_def.url or '(なし)'}, ASIN: {item_def.asin or '(なし)'}"},
            )
        )

        # ResolvedItem を構築（アイテム定義とストア定義をマージ）
        resolved_item = ResolvedItem(
            name=item_def.name,
            store=store_def.name,
            url=item_def.url or "",
            asin=item_def.asin,
            check_method=store_def.check_method,
            price_xpath=item_def.price_xpath or store_def.price_xpath,
            thumb_img_xpath=item_def.thumb_img_xpath or store_def.thumb_img_xpath,
            unavailable_xpath=item_def.unavailable_xpath or store_def.unavailable_xpath,
            price_unit=store_def.price_unit,
            point_rate=store_def.point_rate,
            color=store_def.color,
            actions=store_def.actions,
            preload=item_def.preload,
            search_keyword=item_def.search_keyword or item_def.name,
            exclude_keyword=item_def.exclude_keyword,
            price_range=item_def.price_range,
            cond=item_def.cond,
            jan_code=item_def.jan_code,
            category=item_def.category,
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
    """特定アイテムの価格チェックを開始.

    セキュリティ対策として、target.yaml に保存されているアイテムのみ
    チェックを実行できます。任意の URL を指定した SSRF 攻撃を防止します。
    """
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

    item_name = data.get("item_name")
    store_name = data.get("store_name")

    if not item_name or not store_name:
        return jsonify({"error": "item_name と store_name が必要です"}), 400

    # target.yaml から保存済みアイテムを検索（SSRF 対策）
    result = _find_item_in_target(item_name, store_name)
    if result is None:
        return (
            jsonify(
                {
                    "error": "指定されたアイテムは target.yaml に保存されていません。"
                    "動作確認を行うには、先に設定を保存してください。",
                }
            ),
            404,
        )

    item_def, store_def = result

    # ジョブ作成
    job_id = str(uuid.uuid4())
    job = CheckJob(
        job_id=job_id,
        item_name=item_name,
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
        args=(price_watch_app, job, item_def, store_def),
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
