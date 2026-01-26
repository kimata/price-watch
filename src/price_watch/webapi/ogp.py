#!/usr/bin/env python3
"""OGP 画像生成モジュール."""

from __future__ import annotations

import io
import logging
import pathlib
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import matplotlib
import my_lib.pil_util
from PIL import Image, ImageDraw, ImageFont

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MaxNLocator

if TYPE_CHECKING:
    import price_watch.config

# OGP 画像サイズ
OGP_WIDTH = 1200
OGP_HEIGHT = 630

# グラフ領域サイズ（OGP全面に表示）
GRAPH_WIDTH = 1200
GRAPH_HEIGHT = 630

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

# 日本語フォントの候補（フォールバック用）
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
class FontPaths:
    """OGP 画像生成用フォントパス."""

    jp_regular: pathlib.Path | None = None
    jp_medium: pathlib.Path | None = None
    jp_bold: pathlib.Path | None = None
    en_medium: pathlib.Path | None = None
    en_bold: pathlib.Path | None = None

    @classmethod
    def from_config(cls, font_config: price_watch.config.FontConfig | None) -> FontPaths:
        """FontConfig からフォントパスを取得."""
        if font_config is None:
            return cls()
        return cls(
            jp_regular=font_config.get_font_path("jp_regular"),
            jp_medium=font_config.get_font_path("jp_medium"),
            jp_bold=font_config.get_font_path("jp_bold"),
            en_medium=font_config.get_font_path("en_medium"),
            en_bold=font_config.get_font_path("en_bold"),
        )


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


def _find_fallback_font() -> str | None:
    """フォールバック用の日本語フォントを探す."""
    for path in JAPANESE_FONT_PATHS:
        if pathlib.Path(path).exists():
            return path
    return None


def _get_pillow_font(
    size: int,
    font_path: pathlib.Path | None = None,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Pillow 用フォントを取得.

    Args:
        size: フォントサイズ
        font_path: フォントファイルのパス（None の場合はフォールバック）
    """
    # 指定されたフォントを試す
    if font_path and font_path.exists():
        try:
            return ImageFont.truetype(str(font_path), size)
        except Exception:
            logging.warning("Failed to load font: %s", font_path)

    # フォールバック
    fallback_path = _find_fallback_font()
    if fallback_path:
        try:
            return ImageFont.truetype(fallback_path, size)
        except Exception:
            logging.warning("Failed to load fallback font: %s", fallback_path)

    return ImageFont.load_default()


def _setup_matplotlib_font(font_path: pathlib.Path | None = None) -> None:
    """matplotlib 用のフォントを設定.

    Args:
        font_path: フォントファイルのパス（None の場合はフォールバック）
    """
    import matplotlib.font_manager as fm

    # 指定されたフォントを試す
    if font_path and font_path.exists():
        try:
            fm.fontManager.addfont(str(font_path))
            prop = fm.FontProperties(fname=str(font_path))
            plt.rcParams["font.family"] = prop.get_name()
            return
        except Exception:
            logging.warning("Failed to setup matplotlib font: %s", font_path)

    # フォールバック
    fallback_path = _find_fallback_font()
    if fallback_path:
        try:
            fm.fontManager.addfont(fallback_path)
            prop = fm.FontProperties(fname=fallback_path)
            plt.rcParams["font.family"] = prop.get_name()
        except Exception:
            logging.warning("Failed to setup matplotlib fallback font: %s", fallback_path)


def _format_price(price: int | None) -> str:
    """価格をフォーマット."""
    if price is None:
        return "---"
    return f"¥{price:,}"


def _get_text_size(
    img: Image.Image, text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont
) -> tuple[int, int]:
    """テキストの描画サイズを取得.

    my_lib.pil_util.text_size のラッパー（ImageFont 互換のため）.
    """
    if isinstance(font, ImageFont.FreeTypeFont):
        return my_lib.pil_util.text_size(img, font, text)
    # フォールバック（デフォルトフォントの場合）
    if hasattr(font, "getbbox"):
        bbox = font.getbbox(text)
        return (int(bbox[2] - bbox[0]), int(bbox[3] - bbox[1])) if bbox else (len(text) * 20, 20)
    return (len(text) * 20, 20)


def _truncate_text(
    img: Image.Image, text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont, max_width: int
) -> str:
    """テキストを最大幅に収まるように切り詰める."""
    width, _ = _get_text_size(img, text, font)

    if width <= max_width:
        return text

    ellipsis = "..."
    while text and width > max_width:
        text = text[:-1]
        test_text = text + ellipsis
        width, _ = _get_text_size(img, test_text, font)

    return text + ellipsis


def _generate_price_graph(
    store_histories: list[StoreHistory],
    font_paths: FontPaths | None = None,
) -> Image.Image:
    """価格推移グラフを生成.

    Args:
        store_histories: ストアごとの価格履歴
        font_paths: フォントパス設定
    """
    # matplotlib 用フォントを設定（日本語 medium を使用）
    jp_font = font_paths.jp_medium if font_paths else None
    _setup_matplotlib_font(jp_font)

    fig, ax = plt.subplots(figsize=(GRAPH_WIDTH / 100, GRAPH_HEIGHT / 100), dpi=100)

    # 背景を完全透明に設定（後でサムネイルの上に重ねるため）
    fig.patch.set_facecolor("none")
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

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

    # 凡例は省略（小さく表示された際に読めないため）

    # NOTE: サムネイルはグラフ生成後に PIL で合成する（アスペクト比を正確に維持するため）

    # スタイル調整
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="both", labelsize=24)

    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.1, transparent=True)
    buf.seek(0)
    plt.close(fig)

    return Image.open(buf)


def _draw_rounded_rect_overlay(
    img: Image.Image, rect: tuple[int, int, int, int], radius: int = 10, alpha: int = 230
) -> Image.Image:
    """半透明の角丸背景を描画.

    Args:
        img: 対象画像
        rect: (x1, y1, x2, y2)
        radius: 角丸半径
        alpha: 透明度 (0-255)

    Returns:
        合成後の画像
    """
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rounded_rectangle(
        [(rect[0], rect[1]), (rect[2], rect[3])],
        radius=radius,
        fill=(255, 255, 255, alpha),
    )
    img = img.convert("RGBA")
    img = Image.alpha_composite(img, overlay)
    return img.convert("RGB")


def generate_ogp_image(data: OgpData, font_paths: FontPaths | None = None) -> Image.Image:
    """OGP 画像を生成.

    白背景 → サムネイル → グラフ → テキストの順で合成。
    サムネイルはグラフの後ろに配置される。

    Args:
        data: OGP 画像生成用データ
        font_paths: フォントパス設定
    """
    # --- 1. 白背景を作成 ---
    img = Image.new("RGBA", (OGP_WIDTH, OGP_HEIGHT), color=(255, 255, 255, 255))

    # --- 2. サムネイルを左下に配置（アスペクト比を維持） ---
    if data.thumb_path and data.thumb_path.exists():
        try:
            thumb = Image.open(data.thumb_path)
            thumb_w, thumb_h = thumb.size

            # 最大サイズ（プロットエリアの36% x 78%程度）※1.2倍に拡大
            max_thumb_width = int(OGP_WIDTH * 0.36)
            max_thumb_height = int(OGP_HEIGHT * 0.78)

            # アスペクト比を維持してリサイズ
            thumb_aspect = thumb_w / thumb_h if thumb_h > 0 else 1.0
            max_aspect = max_thumb_width / max_thumb_height

            if thumb_aspect > max_aspect:
                # 幅で制限
                new_width = max_thumb_width
                new_height = int(max_thumb_width / thumb_aspect)
            else:
                # 高さで制限
                new_height = max_thumb_height
                new_width = int(max_thumb_height * thumb_aspect)

            thumb_resized: Image.Image = thumb.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # 半透明化（alpha=0.35相当、グラフの下なので少し薄め）
            thumb_rgba: Image.Image = (
                thumb_resized.convert("RGBA") if thumb_resized.mode != "RGBA" else thumb_resized
            )
            alpha_data = thumb_rgba.split()[3]
            alpha_data = alpha_data.point(lambda x: int(x * 0.35))
            thumb_rgba.putalpha(alpha_data)

            # 左下に配置（軸ラベル分のマージンを考慮）
            paste_x = 100  # Y軸ラベル分
            paste_y = OGP_HEIGHT - new_height - 60  # X軸ラベル分

            # 合成
            img.paste(thumb_rgba, (paste_x, paste_y), thumb_rgba)
        except Exception:
            logging.warning("Failed to load thumbnail: %s", data.thumb_path)

    # --- 3. グラフを上に重ねる（透明背景） ---
    if data.store_histories:
        graph_img = _generate_price_graph(data.store_histories, font_paths=font_paths)
        # グラフのサイズを OGP サイズに調整
        if graph_img.size != (OGP_WIDTH, OGP_HEIGHT):
            graph_img = graph_img.resize((OGP_WIDTH, OGP_HEIGHT), Image.Resampling.LANCZOS)
        # RGBA に変換
        if graph_img.mode != "RGBA":
            graph_img = graph_img.convert("RGBA")
        # グラフを合成（透明部分はサムネイルが見える）
        img = Image.alpha_composite(img, graph_img)

    # RGB に変換
    img = img.convert("RGB")

    # フォントを取得（小さく表示された際も読めるように大きめ）
    # 商品名: 日本語 Bold、価格: 英語 Bold、ストア名: 日本語 Medium
    font_title = _get_pillow_font(58, font_paths.jp_bold if font_paths else None)
    font_price = _get_pillow_font(100, font_paths.en_bold if font_paths else None)
    font_label = _get_pillow_font(36, font_paths.jp_medium if font_paths else None)

    # プロットエリアのマージン（軸ラベル等を考慮）
    plot_right_margin = 80  # 右端の余白
    plot_top_margin = 20  # 上端の余白

    # --- 商品名を上部に表示（プロットエリア全幅を使用） ---
    box_padding = 5  # 上下左右の最小パディング
    title_max_width = OGP_WIDTH - plot_right_margin * 2 - box_padding * 2
    title_text = _truncate_text(img, data.item_name, font_title, title_max_width)
    title_width, title_height = _get_text_size(img, title_text, font_title)

    # 商品名の背景ボックス（右寄せ、サイズ最小化）
    title_box_width = title_width + box_padding * 2
    title_box_height = title_height + box_padding * 2
    title_box_x = OGP_WIDTH - plot_right_margin - title_box_width
    title_box_y = plot_top_margin

    img = _draw_rounded_rect_overlay(
        img,
        (title_box_x, title_box_y, title_box_x + title_box_width, title_box_y + title_box_height),
    )

    # 商品名を描画（ボックス内左寄せ = 視覚的には右寄せボックス）
    title_x = title_box_x + box_padding
    title_y = title_box_y + box_padding
    draw = ImageDraw.Draw(img)
    draw.text((title_x, title_y), title_text, font=font_title, fill=(50, 50, 50))

    # --- 価格・ストア名を右側に表示 ---
    price_text = _format_price(data.best_price)
    store_text = _truncate_text(img, data.best_store, font_label, 400)

    price_width, price_height = _get_text_size(img, price_text, font_price)
    store_width, store_height = _get_text_size(img, store_text, font_label)

    # ボックスサイズを最小化（テキストサイズ + 最小パディング）
    box_padding = 5  # 上下左右の最小パディング
    text_gap = 8  # 価格とストア名の間隔
    max_text_width = max(price_width, store_width)
    info_width = max_text_width + box_padding * 2
    info_height = box_padding + price_height + text_gap + store_height + box_padding

    # プロットエリア右端に配置
    info_x = OGP_WIDTH - plot_right_margin - info_width
    info_y = title_box_y + title_box_height + 10  # 商品名ボックスの下

    img = _draw_rounded_rect_overlay(
        img,
        (info_x, info_y, info_x + info_width, info_y + info_height),
    )

    # テキストを右寄せで描画（my_lib.pil_util.draw_text を活用）
    text_right_edge = info_x + info_width - box_padding
    price_y = info_y + box_padding
    store_y = price_y + price_height + text_gap

    # FreeTypeFont のみ my_lib.pil_util.draw_text を使用可能
    if isinstance(font_price, ImageFont.FreeTypeFont) and isinstance(font_label, ImageFont.FreeTypeFont):
        # 現在価格（右寄せ）
        my_lib.pil_util.draw_text(
            img, price_text, (text_right_edge, price_y), font_price, align="right", color="#dc3232"
        )
        # 最安ストア名（右寄せ）
        my_lib.pil_util.draw_text(
            img, store_text, (text_right_edge, store_y), font_label, align="right", color="#646464"
        )
    else:
        # フォールバック: 手動で右寄せ位置を計算
        draw = ImageDraw.Draw(img)
        price_x = text_right_edge - price_width
        draw.text((price_x, price_y), price_text, font=font_price, fill=(220, 50, 50))
        store_x = text_right_edge - store_width
        draw.text((store_x, store_y), store_text, font=font_label, fill=(100, 100, 100))

    # Price Watch ロゴ（右下）
    font_logo = _get_pillow_font(16, font_paths.en_medium if font_paths else None)
    logo_text = "Price Watch"
    draw = ImageDraw.Draw(img)
    draw.text((OGP_WIDTH - 130, OGP_HEIGHT - 35), logo_text, font=font_logo, fill=(150, 150, 150))

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
    font_paths: FontPaths | None = None,
) -> pathlib.Path:
    """OGP 画像を取得（キャッシュがなければ生成）.

    Args:
        item_key: アイテムキー（キャッシュファイル名に使用）
        data: OGP 画像生成用データ
        cache_dir: キャッシュディレクトリ
        ttl_sec: キャッシュ有効期間（秒）
        font_paths: フォントパス設定
    """
    cache_path = get_cache_path(item_key, cache_dir)

    if is_cache_valid(cache_path, ttl_sec):
        return cache_path

    # 画像を生成して保存
    img = generate_ogp_image(data, font_paths)
    save_ogp_image(img, cache_path)

    return cache_path
