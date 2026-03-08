#!/usr/bin/env python3
"""価格チャート画像生成モジュール.

トップページ用のグラフ画像を Selenium + Chart.js で生成する。
PriceChart.tsx のスタイルを忠実に再現する。

Usage:
  chart_image.py [-c CONFIG] [-t TARGET] -k ITEM_KEY -o PNG_FILE [-D]
  chart_image.py [-c CONFIG] [-t TARGET] --list [-D]

Options:
  -c CONFIG       : CONFIG を設定ファイルとして読み込みます。[default: config.yaml]
  -t TARGET       : TARGET をターゲット設定ファイルとして読み込みます。[default: target.yaml]
  -k ITEM_KEY     : 画像を生成するアイテムのキーを指定します。
  -o PNG_FILE     : 生成した画像を指定されたパスに保存します。
  --list          : アイテム一覧を表示します。
  -D              : デバッグモードで動作します。
"""

from __future__ import annotations

import json
import logging
import pathlib
import re
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import jinja2
import my_lib.selenium_util
from PIL import Image

if TYPE_CHECKING:
    from selenium.webdriver.remote.webdriver import WebDriver

    import price_watch.config

# チャート画像サイズ（トップページカード用）
# これは最終出力サイズ（物理ピクセル）
# CSS ピクセルは devicePixelRatio で割った値になる
CHART_WIDTH = 702
CHART_HEIGHT = 320

# デバイスピクセル比（Retina 相当）
DEVICE_PIXEL_RATIO = 2.0

# キャッシュ有効期間（秒）- デフォルト3時間
CACHE_TTL_SEC = 3 * 60 * 60

# デフォルトの色（PriceChart.tsx と同じ）
DEFAULT_COLORS = [
    "#3b82f6",  # Blue
    "#ef4444",  # Red
    "#22c55e",  # Green
    "#a855f7",  # Purple
    "#f97316",  # Orange
    "#ec4899",  # Pink
]

# テンプレートディレクトリ
_TEMPLATE_DIR = pathlib.Path(__file__).parent / "templates"

# Chart.js 共通ロジックファイル（PriceChart.tsx と共有）
_CHART_COMMON_JS = pathlib.Path(__file__).parent.parent.parent / "frontend" / "public" / "chart-common.js"


@dataclass(frozen=True)
class FontPaths:
    """チャート画像生成用フォントパス（互換性のため残す）."""

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
class PricePoint:
    """価格データポイント."""

    time: str  # ISO 8601 形式
    price: int | None
    effective_price: int | None
    stock: int | None


@dataclass(frozen=True)
class StoreChartData:
    """ストアごとのチャートデータ."""

    store_name: str
    color: str  # Hex カラーコード
    currency_rate: float  # 円への換算レート
    history: list[PricePoint] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """辞書に変換（JSON シリアライズ用）."""
        return {
            "store": self.store_name,
            "color": self.color,
            "currency_rate": self.currency_rate,
            "history": [
                {
                    "time": h.time,
                    "price": h.price,
                    "effective_price": h.effective_price,
                    "stock": h.stock,
                }
                for h in self.history
            ],
        }


@dataclass(frozen=True)
class StoreDefinition:
    """ストア定義（色情報用）."""

    name: str
    color: str | None

    def to_dict(self) -> dict[str, Any]:
        """辞書に変換."""
        return {
            "name": self.name,
            "color": self.color,
        }


@dataclass(frozen=True)
class ChartData:
    """チャート画像生成用データ."""

    item_name: str
    item_key: str
    stores: list[StoreChartData]
    store_definitions: list[StoreDefinition] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """辞書に変換."""
        return {
            "item_name": self.item_name,
            "item_key": self.item_key,
            "stores": [s.to_dict() for s in self.stores],
        }


def _render_chart_html(
    data: ChartData,
    css_width: int,
    css_height: int,
    font_family: str | None = None,
    large_labels: bool | None = None,
) -> str:
    """チャート HTML をレンダリング.

    Args:
        data: チャート画像生成用データ
        css_width: CSS ピクセル幅（コンテナサイズ）
        css_height: CSS ピクセル高さ（コンテナサイズ）
        font_family: CSS font-family 名（None の場合はシステムフォント）
        large_labels: 大きめのラベルを使用するか（None の場合は画像サイズで自動判定）

    Returns:
        レンダリングされた HTML 文字列
    """
    # Jinja2 テンプレートを読み込み
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
    )
    template = env.get_template("chart.html")

    # データを JSON 形式に変換
    chart_data_json = json.dumps(data.to_dict(), ensure_ascii=False)
    store_definitions_json = json.dumps(
        [sd.to_dict() for sd in data.store_definitions],
        ensure_ascii=False,
    )

    # フォントファミリーを設定（None の場合は空文字）
    font_family_str = f"'{font_family}'" if font_family else ""

    # large_labels のデフォルトは False（トップページカードと同じスタイル）
    # PriceChart.tsx のデフォルト値と一致させる
    if large_labels is None:
        large_labels = False

    # 共通 JavaScript を読み込み
    chart_common_js = ""
    if _CHART_COMMON_JS.exists():
        chart_common_js = _CHART_COMMON_JS.read_text(encoding="utf-8")
    else:
        logging.warning("共通 JS ファイルが見つかりません: %s", _CHART_COMMON_JS)

    # テンプレートをレンダリング
    return template.render(
        width=css_width,
        height=css_height,
        chart_data_json=chart_data_json,
        store_definitions_json=store_definitions_json,
        font_family=font_family_str,
        chart_common_js=chart_common_js,
        large_labels=large_labels,
    )


def _create_headless_driver(
    data_path: pathlib.Path,
    css_width: int,
    css_height: int,
    device_scale_factor: float = DEVICE_PIXEL_RATIO,
) -> WebDriver:
    """軽量なヘッドレス Chrome ドライバーを作成.

    undetected_chromedriver 経由で作成し、chromedriver の管理を委譲する。

    Args:
        data_path: Chrome データディレクトリのパス
        css_width: CSS ピクセル幅
        css_height: CSS ピクセル高さ
        device_scale_factor: デバイスピクセル比（デフォルト 2.0 で Retina 相当）

    Returns:
        WebDriver インスタンス
    """
    try:
        import my_lib.selenium_util

        driver = my_lib.selenium_util.create_driver(
            profile_name="chart_generator",
            data_path=data_path,
            is_headless=True,
            stealth_mode=False,
        )
    except Exception:
        logging.warning("undetected_chromedriver での作成に失敗、標準ドライバーにフォールバック")

        import selenium.webdriver
        import selenium.webdriver.chrome.options

        options = selenium.webdriver.chrome.options.Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument(f"--force-device-scale-factor={device_scale_factor}")
        options.add_argument("--lang=ja-JP")

        profile_path = data_path / "chart_generator"
        profile_path.mkdir(parents=True, exist_ok=True)
        options.add_argument(f"--user-data-dir={profile_path}")

        driver = selenium.webdriver.Chrome(options=options)

    # デバイスメトリクスを CDP 経由で設定
    driver.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride",
        {
            "width": css_width + 100,
            "height": css_height + 200,
            "deviceScaleFactor": device_scale_factor,
            "mobile": False,
        },
    )

    # ウィンドウサイズを CSS ピクセルで設定
    driver.set_window_size(css_width + 100, css_height + 200)

    return driver


def generate_chart_image(
    data: ChartData,
    font_paths: FontPaths | None = None,  # 互換性のため残す（Chart.js では未使用）
    width: int = CHART_WIDTH,
    height: int = CHART_HEIGHT,
    driver: WebDriver | None = None,
    data_path: pathlib.Path | None = None,
    font_family: str | None = None,
    device_pixel_ratio: float = DEVICE_PIXEL_RATIO,
) -> Image.Image:
    """価格チャート画像を生成.

    Selenium + Chart.js でグラフをレンダリングし、スクリーンショットを撮影。
    ブラウザと同じ devicePixelRatio でレンダリングすることで、
    フォントサイズや線の太さが一致する。

    Args:
        data: チャート画像生成用データ
        font_paths: フォントパス設定（互換性のため、実際には使用しない）
        width: 最終出力画像の幅（物理ピクセル）
        height: 最終出力画像の高さ（物理ピクセル）
        driver: 既存の WebDriver（None の場合は新規作成）
        data_path: Chrome データディレクトリのパス
        font_family: CSS font-family 名（None の場合はシステムフォント）
        device_pixel_ratio: デバイスピクセル比（デフォルト 2.0）

    Returns:
        生成された画像
    """
    # CSS ピクセルサイズを計算
    # ブラウザと同じ条件でレンダリングするため、
    # 最終出力サイズを devicePixelRatio で割った値を CSS サイズとする
    css_width = int(width / device_pixel_ratio)
    css_height = int(height / device_pixel_ratio)

    # HTML をレンダリング（CSS ピクセルサイズで）
    html_content = _render_chart_html(data, css_width, css_height, font_family)

    # 一時ファイルに HTML を保存
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html_content)
        html_path = pathlib.Path(f.name)

    try:
        # WebDriver を作成または使用
        own_driver = False
        if driver is None:
            if data_path is None:
                data_path = pathlib.Path(tempfile.gettempdir()) / "price_watch_chart"
            data_path.mkdir(parents=True, exist_ok=True)
            driver = _create_headless_driver(data_path, css_width, css_height, device_pixel_ratio)
            own_driver = True

        try:
            # HTML ファイルを開く
            driver.get(f"file://{html_path}")

            # Chart.js のレンダリング完了を待機
            _wait_for_chart_render(driver)

            # スクリーンショットを撮影
            # devicePixelRatio 倍の物理ピクセルで撮影される
            screenshot = driver.get_screenshot_as_png()

            # PIL Image に変換
            import io

            raw_img = Image.open(io.BytesIO(screenshot))

            # チャート領域をクロップ（目標サイズで）
            # devicePixelRatio でレンダリングしているので、縮小は不要
            cropped_img = _crop_chart(raw_img, width, height)

            return cropped_img

        finally:
            if own_driver:
                driver.quit()

    finally:
        # 一時ファイルを削除
        html_path.unlink(missing_ok=True)


def _wait_for_chart_render(driver: WebDriver, timeout: int = 10) -> None:
    """Chart.js のレンダリング完了を待機.

    Args:
        driver: WebDriver インスタンス
        timeout: タイムアウト秒数
    """
    import selenium.webdriver.support.wait

    wait = selenium.webdriver.support.wait.WebDriverWait(driver, timeout)
    try:
        wait.until(lambda d: d.execute_script("return window.chartRendered === true"))
    except Exception:
        logging.warning("Chart render wait timed out, proceeding anyway")
        # タイムアウトしても続行（レンダリングが完了している可能性がある）
        time.sleep(1)


def _crop_chart(
    img: Image.Image,
    width: int,
    height: int,
) -> Image.Image:
    """チャート領域をクロップ.

    devicePixelRatio でレンダリングされた画像から、
    目標サイズでクロップする（リサイズは行わない）。

    Args:
        img: スクリーンショット画像
        width: 目標幅（物理ピクセル）
        height: 目標高さ（物理ピクセル）

    Returns:
        クロップされた画像
    """
    if img.size[0] >= width and img.size[1] >= height:
        # 左上から目標サイズで切り出し
        img = img.crop((0, 0, width, height))

    return img


def _sanitize_filename(name: str) -> str:
    """ファイル名として安全な文字列に変換."""
    return re.sub(r"[^\w\-_]", "_", name)[:100]


def get_cache_path(item_key: str, cache_dir: pathlib.Path) -> pathlib.Path:
    """キャッシュファイルのパスを取得.

    Args:
        item_key: アイテムキー
        cache_dir: キャッシュディレクトリ
    """
    # サブディレクトリを作成
    chart_cache_dir = cache_dir / "chart"
    chart_cache_dir.mkdir(parents=True, exist_ok=True)
    return chart_cache_dir / f"{_sanitize_filename(item_key)}.png"


def is_cache_valid(cache_path: pathlib.Path, ttl_sec: int = CACHE_TTL_SEC) -> bool:
    """キャッシュが有効かどうかを判定."""
    if not cache_path.exists():
        return False

    mtime = cache_path.stat().st_mtime
    age = time.time() - mtime
    return age < ttl_sec


def save_chart_image(img: Image.Image, output_path: pathlib.Path) -> None:
    """チャート画像をファイルに保存."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, format="PNG")


def get_or_generate_chart_image(
    data: ChartData,
    cache_dir: pathlib.Path,
    ttl_sec: int = CACHE_TTL_SEC,
    font_paths: FontPaths | None = None,
    driver: WebDriver | None = None,
    data_path: pathlib.Path | None = None,
    font_family: str | None = None,
) -> pathlib.Path:
    """チャート画像を取得（キャッシュがなければ生成）.

    Args:
        data: チャート画像生成用データ
        cache_dir: キャッシュディレクトリ
        ttl_sec: キャッシュ有効期間（秒）
        font_paths: フォントパス設定（互換性のため）
        driver: 既存の WebDriver（None の場合は新規作成）
        data_path: Chrome データディレクトリのパス
        font_family: CSS font-family 名（None の場合はシステムフォント）

    Returns:
        生成された画像ファイルのパス
    """
    cache_path = get_cache_path(data.item_key, cache_dir)

    if is_cache_valid(cache_path, ttl_sec):
        return cache_path

    # 画像を生成して保存
    img = generate_chart_image(data, font_paths, driver=driver, data_path=data_path, font_family=font_family)
    save_chart_image(img, cache_path)

    return cache_path


def _calc_effective_price(price: int | None, point_rate: float) -> int | None:
    """実質価格を計算（ポイント還元考慮）."""
    if price is None:
        return None
    return int(price * (1 - point_rate / 100))


def _get_item_data_from_db(
    item_key: str,
    db_path: pathlib.Path,
    target_config: Any | None = None,
    currency_rates: dict[str, float] | None = None,
    days: int = 30,
) -> tuple[str | None, list[StoreChartData]]:
    """データベースからアイテムデータを取得.

    Args:
        item_key: アイテムキー
        db_path: データベースディレクトリパス
        target_config: ターゲット設定（色情報用）
        currency_rates: 通貨換算レート（price_unit -> rate のマッピング）
        days: 履歴取得日数

    Returns:
        (アイテム名, StoreChartData リスト) のタプル
    """
    import price_watch.managers.history

    manager = price_watch.managers.history.HistoryManager.create(db_path)
    manager.initialize()

    if currency_rates is None:
        currency_rates = {}

    # 全アイテムを取得して item_key から名前を特定
    all_items = manager.get_all_items()
    primary = next((item for item in all_items if item.item_key == item_key), None)
    if primary is None:
        return None, []

    item_name = primary.name

    # 同名の全ストアのデータを収集
    same_name_items = [item for item in all_items if item.name == item_name]

    store_chart_data_list: list[StoreChartData] = []
    for idx, item in enumerate(same_name_items):
        # 履歴を取得
        _, history_records = manager.get_history(item.item_key, days=days)

        # 色、price_unit、point_rate を取得
        color = None
        price_unit = "円"
        point_rate = 0.0
        if target_config is not None:
            store_def = target_config.get_store(item.store)
            if store_def:
                color = store_def.color
                price_unit = store_def.price_unit
                point_rate = store_def.point_rate

        if not color:
            color = DEFAULT_COLORS[idx % len(DEFAULT_COLORS)]

        # 通貨換算レートを price_unit から取得
        currency_rate = currency_rates.get(price_unit, 1.0)

        # 履歴をチャート用データに変換
        history = [
            PricePoint(
                time=h.time if isinstance(h.time, str) else h.time.isoformat(),
                price=h.price,
                effective_price=_calc_effective_price(h.price, point_rate),
                stock=h.stock,
            )
            for h in history_records
        ]

        store_chart_data_list.append(
            StoreChartData(
                store_name=item.store,
                color=color,
                currency_rate=currency_rate,
                history=history,
            )
        )

    return item_name, store_chart_data_list


def _list_items(db_path: pathlib.Path) -> list[tuple[str, str, str]]:
    """データベースから全アイテムを取得.

    Returns:
        (item_key, name, store) のタプルリスト
    """
    import price_watch.managers.history

    manager = price_watch.managers.history.HistoryManager.create(db_path)
    manager.initialize()
    all_items = manager.get_all_items()

    return [(item.item_key, item.name, item.store) for item in all_items]


def generate_all_chart_images(
    cache_dir: pathlib.Path,
    db_path: pathlib.Path,
    target_config: Any,
    currency_rates: dict[str, float],
    data_path: pathlib.Path,
    font_family: str | None = None,
    ttl_sec: int = CACHE_TTL_SEC,
    should_terminate: Callable[[], bool] | None = None,
) -> int:
    """全アイテムのチャート画像を一括生成.

    - 1つのWebDriverを共有して効率化
    - キャッシュが有効なアイテムはスキップ
    - should_terminate で中断可能

    Args:
        cache_dir: キャッシュディレクトリ
        db_path: データベースディレクトリパス
        target_config: ターゲット設定（色情報用）
        currency_rates: 通貨換算レート（price_unit -> rate のマッピング）
        data_path: Chrome データディレクトリのパス
        font_family: CSS font-family 名（None の場合はシステムフォント）
        ttl_sec: キャッシュ有効期間（秒）
        should_terminate: 終了判定コールバック

    Returns:
        生成した画像数
    """
    import price_watch.managers.history

    logging.info("Starting background chart image generation...")

    # HistoryManager を初期化
    manager = price_watch.managers.history.HistoryManager.create(db_path)
    manager.initialize()
    all_items = manager.get_all_items()

    if not all_items:
        logging.info("No items found in database, skipping chart generation")
        return 0

    # 商品名でグループ化して重複を除去
    unique_names: set[str] = set()
    items_to_process: list[tuple[str, str]] = []  # (item_key, item_name)

    for item in all_items:
        if item.name not in unique_names:
            unique_names.add(item.name)
            items_to_process.append((item.item_key, item.name))

    logging.info("Found %d unique items for chart generation", len(items_to_process))

    # キャッシュが無効なアイテムのみフィルタリング
    items_needing_generation: list[tuple[str, str]] = []
    for item_key, item_name in items_to_process:
        cache_path = get_cache_path(item_key, cache_dir)
        if not is_cache_valid(cache_path, ttl_sec):
            items_needing_generation.append((item_key, item_name))

    if not items_needing_generation:
        logging.info("All chart images are cached, skipping generation")
        return 0

    logging.info(
        "Generating %d chart images (skipped %d cached)",
        len(items_needing_generation),
        len(items_to_process) - len(items_needing_generation),
    )

    # CSS ピクセルサイズを計算
    css_width = int(CHART_WIDTH / DEVICE_PIXEL_RATIO)
    css_height = int(CHART_HEIGHT / DEVICE_PIXEL_RATIO)

    # WebDriver を作成
    driver = _create_headless_driver(data_path, css_width, css_height, DEVICE_PIXEL_RATIO)

    generated_count = 0
    try:
        # ストア定義を取得（色情報用）
        store_definitions = []
        if target_config is not None:
            store_definitions = [StoreDefinition(name=s.name, color=s.color) for s in target_config.stores]

        for item_key, _item_name in items_needing_generation:
            # 終了判定
            if should_terminate is not None and should_terminate():
                logging.info("Chart generation interrupted by termination signal")
                break

            try:
                # アイテムデータを取得
                result = _get_item_data_from_db(item_key, db_path, target_config, currency_rates)
                if result[0] is None:
                    logging.debug("Skipping item %s: not found in database", item_key)
                    continue

                name: str = result[0]
                stores_data: list[StoreChartData] = result[1]

                if not stores_data:
                    logging.debug("Skipping item %s: no store data", item_key)
                    continue

                # チャートデータを作成
                chart_data = ChartData(
                    item_name=name,
                    item_key=item_key,
                    stores=stores_data,
                    store_definitions=store_definitions,
                )

                # 画像を生成
                img = generate_chart_image(
                    chart_data,
                    driver=driver,
                    data_path=data_path,
                    font_family=font_family,
                )

                # 保存
                cache_path = get_cache_path(item_key, cache_dir)
                save_chart_image(img, cache_path)
                generated_count += 1

                logging.debug("Generated chart image for %s", name)

            except Exception:
                logging.exception("Failed to generate chart image for %s", item_key)
                continue

    finally:
        driver.quit()

    logging.info("Generated %d chart images", generated_count)
    return generated_count


if __name__ == "__main__":
    import docopt
    import my_lib.logger

    import price_watch.config
    import price_watch.target

    assert __doc__ is not None  # noqa: S101
    args = docopt.docopt(__doc__)

    config_file = args["-c"]
    target_file = args["-t"]
    item_key = args["-k"]
    out_file = args["-o"]
    list_mode = args["--list"]
    debug_mode = args["-D"]

    my_lib.logger.init("chart_image", level=logging.DEBUG if debug_mode else logging.INFO)

    # 設定ファイルを読み込み
    config = price_watch.config.load(pathlib.Path(config_file))
    target_config = price_watch.target.load(pathlib.Path(target_file))

    db_path = config.data.price

    # 通貨換算レートを構築
    currency_rates: dict[str, float] = {}
    if config.check.currency:
        for cr in config.check.currency:
            currency_rates[cr.label] = cr.rate

    if list_mode:
        # アイテム一覧を表示（商品名でグループ化）
        items = _list_items(db_path)
        logging.info("アイテム一覧 (%d 件):", len(items))

        # 商品名でグループ化
        from collections import defaultdict

        by_name: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for key, name, store in items:
            by_name[name].append((key, store))

        # 商品名ごとに表示
        for name, key_stores in sorted(by_name.items()):
            first_key = key_stores[0][0]
            stores_str = ", ".join(store for _, store in key_stores)
            logging.info("  %s: %s [%s]", first_key, name, stores_str)
    else:
        # 画像を生成
        if not item_key:
            logging.error("-k オプションでアイテムキーを指定してください。")
            logging.info("利用可能なアイテムは --list オプションで確認できます。")
            raise SystemExit(1)

        if not out_file:
            logging.error("-o オプションで出力ファイルを指定してください。")
            raise SystemExit(1)

        logging.info("アイテムキー: %s", item_key)

        # アイテムデータを取得
        result = _get_item_data_from_db(item_key, db_path, target_config, currency_rates)
        if result[0] is None:
            logging.error("アイテムが見つかりません: %s", item_key)
            raise SystemExit(1)

        item_name: str = result[0]
        stores_data: list[StoreChartData] = result[1]

        logging.info("アイテム名: %s", item_name)
        logging.info("ストア数: %d", len(stores_data))
        for store_item in stores_data:
            logging.info("  - %s (履歴: %d 件)", store_item.store_name, len(store_item.history))

        # ストア定義を取得（色情報用）
        store_definitions = [StoreDefinition(name=s.name, color=s.color) for s in target_config.stores]

        # チャートデータを作成
        chart_data = ChartData(
            item_name=item_name,
            item_key=item_key,
            stores=stores_data,
            store_definitions=store_definitions,
        )

        # フォント設定を取得
        font_family = None
        if config.font is not None and config.font.chart.family is not None:
            font_family = config.font.chart.family
            logging.info("フォントファミリー: %s", font_family)

        # 画像を生成
        logging.info("画像を生成中...")
        img = generate_chart_image(chart_data, data_path=config.data.selenium, font_family=font_family)

        # 保存
        output_path = pathlib.Path(out_file)
        save_chart_image(img, output_path)
        logging.info("保存しました: %s", output_path)

        logging.info("完了。")
