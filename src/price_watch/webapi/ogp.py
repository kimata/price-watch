#!/usr/bin/env python3
"""OGP 画像生成モジュール."""

from __future__ import annotations

import io
import logging
import pathlib
import re
from dataclasses import dataclass
from typing import Any

import matplotlib
from PIL import Image, ImageDraw, ImageFont

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MaxNLocator

# OGP 画像サイズ
OGP_WIDTH = 1200
OGP_HEIGHT = 630

# グラフ領域サイズ
GRAPH_WIDTH = 850
GRAPH_HEIGHT = 450

# キャッシュ有効期間（秒）
CACHE_TTL_SEC = 3600

# デフォルトの色（Chart.js と同じ）
DEFAULT_COLORS = [
    "#3b82f6",  # Blue
    "#ef4444",  # Red
    "#22c55e",  # Green
    "#a855f7",  # Purple
    "#f97316",  # Orange
    "#ec4899",  # Pink
]

# 日本語フォントの候補
JAPANESE_FONT_PATHS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/OTF/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "C:\\Windows\\Fonts\\msgothic.ttc",
    "C:\\Windows\\Fonts\\meiryo.ttc",
]


@dataclass(frozen=True)
class StoreHistory:
    """ストアごとの価格履歴."""

    store_name: str
    color: str
    history: list[dict[str, Any]]  # [{"time": str, "price": int | None, "effective_price": int | None}, ...]


@dataclass(frozen=True)
class OgpData:
    """OGP 画像生成用データ."""

    item_name: str
    best_price: int | None
    best_store: str
    lowest_price: int | None
    thumb_path: pathlib.Path | None
    store_histories: list[StoreHistory]


def _find_japanese_font() -> str | None:
    """日本語フォントを探す."""
    for path in JAPANESE_FONT_PATHS:
        if pathlib.Path(path).exists():
            return path
    return None


def _get_pillow_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Pillow 用フォントを取得."""
    font_path = _find_japanese_font()
    if font_path:
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:
            logging.warning("Failed to load font: %s", font_path)
    return ImageFont.load_default()


def _setup_matplotlib_font() -> None:
    """matplotlib 用の日本語フォントを設定."""
    font_path = _find_japanese_font()
    if font_path:
        import matplotlib.font_manager as fm

        try:
            fm.fontManager.addfont(font_path)
            prop = fm.FontProperties(fname=font_path)
            plt.rcParams["font.family"] = prop.get_name()
        except Exception:
            logging.warning("Failed to setup matplotlib font: %s", font_path)


def _format_price(price: int | None) -> str:
    """価格をフォーマット."""
    if price is None:
        return "---"
    return f"¥{price:,}"


def _truncate_text(text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont, max_width: int) -> str:
    """テキストを最大幅に収まるように切り詰める."""
    if hasattr(font, "getbbox"):
        bbox = font.getbbox(text)
        width = bbox[2] - bbox[0] if bbox else 0
    else:
        width = len(text) * 20

    if width <= max_width:
        return text

    ellipsis = "..."
    while text and width > max_width:
        text = text[:-1]
        test_text = text + ellipsis
        if hasattr(font, "getbbox"):
            bbox = font.getbbox(test_text)
            width = bbox[2] - bbox[0] if bbox else 0
        else:
            width = len(test_text) * 20

    return text + ellipsis


def _generate_price_graph(store_histories: list[StoreHistory]) -> Image.Image:
    """価格推移グラフを生成."""
    _setup_matplotlib_font()

    fig, ax = plt.subplots(figsize=(GRAPH_WIDTH / 100, GRAPH_HEIGHT / 100), dpi=100)

    # 背景色を設定
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    all_prices: list[int] = []
    all_times_set: set[str] = set()

    for sh in store_histories:
        for h in sh.history:
            if h.get("effective_price") is not None:
                all_prices.append(h["effective_price"])
            all_times_set.add(h["time"])

    all_times: list[str] = sorted(all_times_set)

    if not all_prices or not all_times:
        # データがない場合は空のグラフを返す
        ax.text(
            0.5,
            0.5,
            "価格情報なし",
            ha="center",
            va="center",
            fontsize=14,
            color="gray",
            transform=ax.transAxes,
        )
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")

        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.1)
        buf.seek(0)
        plt.close(fig)
        return Image.open(buf)

    # Y軸の範囲を設定（Chart.js と同様に padding 10%）
    min_price = min(all_prices)
    max_price = max(all_prices)
    padding = (max_price - min_price) * 0.1 or max_price * 0.1
    y_min = max(0, min_price - padding)
    y_max = max_price + padding

    # 時間を datetime に変換
    from datetime import datetime

    time_to_dt: dict[str, datetime] = {}
    for t in all_times:
        try:
            # "YYYY-MM-DD HH:MM:SS" 形式を想定
            dt = datetime.fromisoformat(t.replace(" ", "T"))
            time_to_dt[t] = dt
        except ValueError:
            logging.debug("Invalid datetime format: %s", t)

    sorted_times = sorted(time_to_dt.keys(), key=lambda x: time_to_dt[x])
    if not sorted_times:
        ax.text(
            0.5,
            0.5,
            "価格情報なし",
            ha="center",
            va="center",
            fontsize=14,
            color="gray",
            transform=ax.transAxes,
        )
        ax.axis("off")
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.1)
        buf.seek(0)
        plt.close(fig)
        return Image.open(buf)

    # 各ストアのデータをプロット
    for sh in store_histories:
        # 時間ごとの価格をマップ
        price_map: dict[str, int | None] = {}
        for h in sh.history:
            time_key = h["time"]
            # 同じ時間帯に複数のエントリがある場合は、時間の hour でグルーピング
            if time_key in time_to_dt:
                hour_key = time_to_dt[time_key].strftime("%Y-%m-%d %H:00")
                if hour_key not in price_map or (
                    price_map[hour_key] is None and h.get("effective_price") is not None
                ):
                    price_map[hour_key] = h.get("effective_price")

        # ソートされた時間に沿ってデータを配列化
        times: list[datetime] = []
        prices: list[int | None] = []
        for time_str in sorted_times:
            dt_or_none = time_to_dt.get(time_str)
            if dt_or_none is not None:
                hour_key = dt_or_none.strftime("%Y-%m-%d %H:00")
                if hour_key in price_map:
                    times.append(dt_or_none)
                    prices.append(price_map[hour_key])

        if times and any(p is not None for p in prices):
            # None を除外してプロット（Chart.js の spanGaps: true 相当）
            valid_times: list[datetime] = []
            valid_prices: list[int] = []
            for time_dt, price in zip(times, prices, strict=False):
                if price is not None:
                    valid_times.append(time_dt)
                    valid_prices.append(price)

            if valid_times:
                color = sh.color
                # matplotlib の型スタブは datetime を受け付けないが、実行時は動作する
                ax.plot(
                    valid_times,  # type: ignore[arg-type]
                    valid_prices,
                    label=sh.store_name,
                    color=color,
                    linewidth=6,
                    marker="o" if len(valid_times) <= 20 else None,
                    markersize=10,
                )

    # Y軸の設定
    ax.set_ylim(y_min, y_max)

    # Y軸のフォーマット（カンマ区切り）と目盛り数を制限
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{int(x):,}"))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=5, integer=True))

    # X軸の設定（目盛り数を制限）
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%-m月%-d日"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=4))

    # X軸のグリッドを非表示（Chart.js と同様）
    ax.xaxis.grid(False)
    ax.yaxis.grid(True, linestyle="-", alpha=0.3)

    # 凡例を上部に表示（Chart.js と同様）
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.15), ncol=min(len(store_histories), 4), fontsize=12)

    # スタイル調整
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="both", labelsize=14)

    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.1, facecolor="white")
    buf.seek(0)
    plt.close(fig)

    return Image.open(buf)


def generate_ogp_image(data: OgpData) -> Image.Image:
    """OGP 画像を生成."""
    # 1200x630 の白い画像を作成
    img = Image.new("RGB", (OGP_WIDTH, OGP_HEIGHT), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # フォントを取得
    font_title = _get_pillow_font(36)
    font_price = _get_pillow_font(48)
    font_label = _get_pillow_font(20)
    font_store = _get_pillow_font(24)

    # 左側エリアの幅
    left_width = OGP_WIDTH - GRAPH_WIDTH - 60  # 60 は margin

    # --- 左側: サムネイル + 商品情報 ---
    y_offset = 40

    # 商品名（最大幅で切り詰め）
    title_text = _truncate_text(data.item_name, font_title, left_width - 40)
    draw.text((30, y_offset), title_text, font=font_title, fill=(30, 30, 30))
    y_offset += 60

    # サムネイル画像
    thumb_size = 180
    if data.thumb_path and data.thumb_path.exists():
        try:
            thumb = Image.open(data.thumb_path)
            thumb.thumbnail((thumb_size, thumb_size), Image.Resampling.LANCZOS)
            # サムネイルを中央に配置
            thumb_x = 30 + (thumb_size - thumb.width) // 2
            thumb_y = y_offset + (thumb_size - thumb.height) // 2
            img.paste(thumb, (thumb_x, thumb_y))
        except Exception:
            logging.warning("Failed to load thumbnail: %s", data.thumb_path)

    y_offset += thumb_size + 30

    # 現在価格
    draw.text((30, y_offset), "現在価格", font=font_label, fill=(100, 100, 100))
    y_offset += 28
    price_text = _format_price(data.best_price)
    draw.text((30, y_offset), price_text, font=font_price, fill=(30, 30, 30))
    y_offset += 60

    # 最安ストア
    draw.text((30, y_offset), "最安ストア", font=font_label, fill=(100, 100, 100))
    y_offset += 28
    store_text = _truncate_text(data.best_store, font_store, left_width - 40)
    draw.text((30, y_offset), store_text, font=font_store, fill=(30, 30, 30))
    y_offset += 40

    # 最安値
    if data.lowest_price is not None:
        draw.text((30, y_offset), "最安値", font=font_label, fill=(100, 100, 100))
        y_offset += 28
        lowest_text = _format_price(data.lowest_price)
        draw.text((30, y_offset), lowest_text, font=font_store, fill=(100, 100, 100))

    # --- 右側: 価格推移グラフ ---
    if data.store_histories:
        graph_img = _generate_price_graph(data.store_histories)
        # グラフを右側に配置
        graph_x = left_width + 30
        graph_y = 80
        # グラフのサイズを調整
        graph_img = graph_img.resize(
            (GRAPH_WIDTH, GRAPH_HEIGHT),
            Image.Resampling.LANCZOS,
        )
        img.paste(graph_img, (graph_x, graph_y))

    # Price Watch ロゴ（右下）
    font_logo = _get_pillow_font(18)
    logo_text = "Price Watch"
    draw.text((OGP_WIDTH - 150, OGP_HEIGHT - 40), logo_text, font=font_logo, fill=(150, 150, 150))

    return img


def get_cache_path(item_key: str, cache_dir: pathlib.Path) -> pathlib.Path:
    """キャッシュファイルのパスを取得."""
    # サブディレクトリを作成
    ogp_cache_dir = cache_dir / "ogp"
    ogp_cache_dir.mkdir(parents=True, exist_ok=True)
    # ファイル名にはアイテムキーのみ使用（時間は含めない）
    # キャッシュの有効期限はファイルの更新時刻で判定
    return ogp_cache_dir / f"{_sanitize_filename(item_key)}.png"


def _sanitize_filename(name: str) -> str:
    """ファイル名として安全な文字列に変換."""
    return re.sub(r"[^\w\-_]", "_", name)[:100]


def is_cache_valid(cache_path: pathlib.Path, ttl_sec: int = CACHE_TTL_SEC) -> bool:
    """キャッシュが有効かどうかを判定."""
    if not cache_path.exists():
        return False

    import time

    mtime = cache_path.stat().st_mtime
    age = time.time() - mtime
    return age < ttl_sec


def save_ogp_image(img: Image.Image, output_path: pathlib.Path) -> None:
    """OGP 画像をファイルに保存."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, format="PNG")


def get_or_generate_ogp_image(
    item_key: str,
    data: OgpData,
    cache_dir: pathlib.Path,
    ttl_sec: int = CACHE_TTL_SEC,
) -> pathlib.Path:
    """OGP 画像を取得（キャッシュがなければ生成）."""
    cache_path = get_cache_path(item_key, cache_dir)

    if is_cache_valid(cache_path, ttl_sec):
        return cache_path

    # 画像を生成して保存
    img = generate_ogp_image(data)
    save_ogp_image(img, cache_path)

    return cache_path
