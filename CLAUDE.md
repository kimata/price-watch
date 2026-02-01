# CLAUDE.md

このファイルは Claude Code がこのリポジトリで作業する際のガイダンスを提供します。

## 概要

商品価格を監視して通知するスクリプトです。オンラインショップの価格をスクレイピングまたは Amazon PA-API で取得し、価格変動や在庫復活を検出して Slack に通知します。Selenium と undetected-chromedriver を使用してブラウザを操作します。

対応ショップ:

- Amazon.co.jp（PA-API / スクレイピング）
- メルカリ（キーワード検索）
- ラクマ（キーワード検索）
- PayPayフリマ（キーワード検索）
- Yahoo!ショッピング（API 検索）
- 楽天市場（API 検索）
- ヨドバシ.com
- Switch Science
- Ubiquiti Store USA
- Lenovo

## 重要な注意事項

### 共通運用ルール

- 変更前に意図と影響範囲を説明し、ユーザー確認を取る
- `pyproject.toml` 等の共通設定は `../py-project` で管理し、各リポジトリで直接編集しない
- `my_lib` の変更は `../my-py-lib` で実施し、各リポジトリのハッシュ更新後に `uv lock && uv sync` を実行
- 依存関係管理は `uv` を標準とし、他の手段はフォールバック扱い
- 構造化データは `@dataclass` を優先し、辞書からの生成は `parse()` 命名で統一
- Union 型が 3 箇所以上で出現する場合は `TypeAlias` を定義
- `except Exception` は避け、具体的な例外型を指定する
- ミラー運用がある場合は primary リポジトリにのみ push する

### コード変更時のドキュメント更新

コードを更新した際は、以下のドキュメントも更新が必要か**必ず検討してください**:

| ドキュメント | 更新が必要なケース                                                 |
| ------------ | ------------------------------------------------------------------ |
| README.md    | 機能追加・変更、使用方法の変更、依存関係の変更                     |
| CLAUDE.md    | アーキテクチャ変更、新規モジュール追加、設定項目変更、開発手順変更 |
| CHANGELOG.md | タグを打つ（リリースする）際                                       |

### my-lib（共通ライブラリ）の修正について

`my_lib` のソースコードは **`../my-py-lib`** に存在します。

リファクタリング等で `my_lib` の修正が必要な場合:

1. **必ず事前に何を変更したいか説明し、確認を取ること**
2. `../my-py-lib` で修正を行い、commit & push
3. このリポジトリの `pyproject.toml` の my-lib のコミットハッシュを更新
4. `uv lock && uv sync` で依存関係を更新

```bash
# my-lib 更新の流れ
cd ../my-py-lib
# ... 修正 ...
git add . && git commit -m "変更内容" && git push
cd ../price-watch
# pyproject.toml の my-lib ハッシュを更新
uv lock && uv sync
```

### プロジェクト管理ファイルについて

以下のファイルは **`../py-project`** で一元管理しています:

- `pyproject.toml`
- `.pre-commit-config.yaml`
- `.gitignore`
- `.gitlab-ci.yml`
- その他プロジェクト共通設定

**これらのファイルを直接編集しないでください。**

修正が必要な場合:

1. **必ず事前に何を変更したいか説明し、確認を取ること**
2. `../py-project` のテンプレートを更新
3. このリポジトリに変更を反映

## 開発環境

### パッケージ管理

- **パッケージマネージャー**: uv
- **依存関係のインストール**: `uv sync`
- **依存関係の更新**: `uv lock --upgrade-package <package-name>`

### テスト実行

テストは3層構造で管理されています:

```bash
# ユニットテスト（外部アクセスなし、高速）
uv run pytest tests/unit/

# E2E テスト（外部サーバー必要）
uv run pytest tests/e2e/ --host <host> --port <port>

# 型チェック
uv run pyright

# 全テスト（E2E を除く）
uv run pytest
```

### アプリケーション実行

```bash
# 通常実行
uv run price-watch

# デバッグモード
uv run price-watch -D

# 設定ファイル指定
uv run price-watch -c config.yaml -t target.yaml

# WebUI サーバーポート指定
uv run price-watch -p 5000

# メトリクス Web UI のみ
uv run price-watch-webui
```

### ヘルスチェック

```bash
uv run price-watch-healthz
```

## アーキテクチャ

### ディレクトリ構成

```
src/
└── price_watch/
    ├── __main__.py             # メインエントリーポイント
    ├── cli/                    # CLI エントリーポイント群
    │   ├── app.py              # アプリケーション実行ロジック（price-watch コマンド）
    │   ├── webui.py            # メトリクス Web サーバー（price-watch-webui）
    │   └── healthz.py          # Liveness チェック（price-watch-healthz）
    │
    ├── app_context.py          # アプリケーションコンテキスト（ファサード）
    ├── processor.py            # アイテム処理（共通処理抽出）
    ├── exceptions.py           # 例外階層
    ├── models.py               # 型安全なデータモデル（dataclass）
    │
    ├── managers/               # Manager パターンによる責務分離
    │   ├── __init__.py
    │   ├── config_manager.py   # 設定管理（ホットリロード対応）
    │   ├── browser_manager.py  # WebDriver ライフサイクル
    │   ├── history_manager.py  # 履歴 DB 管理
    │   └── metrics_manager.py  # メトリクス統計
    │
    ├── config.py               # 型付き設定クラス（dataclass）
    ├── const.py                # 定数
    │
    ├── target.py               # ターゲット設定クラス（dataclass + Protocol）
    ├── item.py                 # アイテムリスト管理
    │
    ├── store/                  # ストア別価格取得
    │   ├── scrape.py           # スクレイピングによる価格チェック
    │   ├── flea_market.py      # フリマ検索（メルカリ・ラクマ・PayPayフリマ）
    │   ├── yahoo.py            # Yahoo!ショッピング検索
    │   ├── rakuten.py          # 楽天市場検索
    │   └── amazon/             # Amazon 関連モジュール
    │       ├── paapi.py        # Amazon PA-API による価格取得
    │       └── paapi_rate_limiter.py # PA-API レート制限
    │
    ├── captcha.py              # CAPTCHA 処理（reCAPTCHA 音声認識）
    ├── event.py                # イベント検出・記録（価格変動、在庫復活等）
    ├── notify.py               # Slack 通知
    ├── history.py              # 価格履歴管理（SQLite）
    ├── thumbnail.py            # サムネイル画像管理
    │
    └── webapi/                 # Web API サーバー
        ├── server.py           # Flask サーバー
        └── page.py             # REST API エンドポイント

frontend/                       # React フロントエンド（価格履歴ダッシュボード）

tests/
├── conftest.py                 # 共通フィクスチャ
├── unit/                       # ユニットテスト
└── e2e/                        # E2E テスト（Playwright）
```

### コアコンポーネント

#### PriceWatchApp (`app_context.py`)

全ての Manager を統合し、アプリケーションのライフサイクルを管理するファサードクラス。

```python
# 設定ファイルから PriceWatchApp を生成
app = PriceWatchApp.create(
    config_file=config_file,
    target_file=target_file,
    port=port,
    debug_mode=debug_mode,
)

# 初期化・実行
app.initialize()
app.setup_signal_handlers()
app.start_webui_server()
# ... 処理 ...
app.shutdown()
```

#### AppRunner (`cli/app.py`)

PriceWatchApp と ItemProcessor を組み合わせてメインループを制御するオーケストレーター。

```python
runner = AppRunner(app=app)
success = runner.execute()
```

#### ItemProcessor (`processor.py`)

各チェック方法（スクレイピング、PA-API、メルカリ、Yahoo、楽天）の共通処理を提供。

```python
processor = ItemProcessor(app=app, loop=0)
processor.process_all(item_list)
```

#### Manager クラス

| Manager        | 責務                                                       |
| -------------- | ---------------------------------------------------------- |
| ConfigManager  | 設定・ターゲットファイルの読み込み、ホットリロード         |
| BrowserManager | WebDriver のライフサイクル管理（遅延初期化、再作成、終了） |
| HistoryManager | 価格履歴 DB の操作（DI 対応ラッパー）                      |
| MetricsManager | 巡回セッションのメトリクス記録                             |

#### 実行フロー

```
price-watch (cli/app.py)
├── PriceWatchApp.create() → アプリケーションコンテキスト作成
│   ├── ConfigManager → 設定読み込み
│   ├── HistoryManager → 履歴 DB 管理
│   ├── BrowserManager → WebDriver 管理
│   └── MetricsManager → メトリクス管理
├── app.initialize() → 各 Manager を初期化
├── app.setup_signal_handlers() → シグナルハンドラ設定
├── app.start_webui_server() → Flask サーバー起動
├── AppRunner.execute() → メイン監視ループ
│   └── ItemProcessor.process_all() → 全アイテム処理
│       ├── process_scrape_items() → スクレイピング
│       ├── process_amazon_items() → PA-API
│       ├── process_flea_market_items() → フリマ検索（メルカリ・ラクマ・PayPayフリマ）
│       ├── process_yahoo_items() → Yahoo検索
│       └── process_rakuten_items() → 楽天検索
└── app.shutdown() → 終了処理
```

### データモデル

#### exceptions.py

```python
# 例外階層
PriceWatchError     # 基底例外
├── ConfigError     # 設定エラー
├── ScrapeError     # スクレイピングエラー
│   ├── CrawlError  # クロール処理エラー
│   └── SessionError # Selenium セッションエラー
├── PaapiError      # Amazon PA-API エラー
├── NotificationError # 通知送信エラー
├── HistoryError    # 履歴 DB エラー
└── BrowserError    # ブラウザエラー
```

#### models.py

```python
# Enum
CrawlStatus: SUCCESS, FAILURE
StockStatus: IN_STOCK, OUT_OF_STOCK, UNKNOWN

# dataclass
PriceResult      # 価格チェック結果（price, stock, crawl_status, thumb_url）
CheckedItem      # チェック済みアイテム（name, store, url, price, stock 等）
PriceRecord      # 価格履歴レコード
ItemRecord       # アイテムレコード
ItemStats        # アイテム統計情報
EventRecord      # イベントレコード
ProcessResult    # 処理結果集計
SessionStats     # セッション統計
StoreStats       # ストア別統計
```

#### target.py

```python
# Enum
CheckMethod: SCRAPE, AMAZON_PAAPI, MERCARI_SEARCH, RAKUMA_SEARCH, PAYPAY_SEARCH, YAHOO_SEARCH
ActionType: CLICK, INPUT, SIXDIGIT, RECAPTCHA

# Protocol
HasName, HasUrl, HasStore, HasXPathConfig, HasCheckMethod
WatchItem  # 監視対象アイテムの Protocol

# dataclass
ActionStep       # アクションステップ（type, xpath, value）
PreloadConfig    # プリロード設定（url, every）
StoreDefinition  # ストア定義（name, check_method, price_xpath 等）
ItemDefinition   # アイテム定義（name, store, url, asin, category 等）
ResolvedItem     # ストア定義とマージ済みのアイテム
TargetConfig     # ターゲット設定（stores, items, categories）
```

### 設定ファイル

#### config.yaml

```yaml
check:
    interval_sec: 1800 # 監視周期（秒）
    drop: # 価格下落イベント判定
        ignore:
            hour: 6 # 直近 N 時間以内の重複イベントを無視
        windows: # 判定ウィンドウ（days 昇順にソートされる）
            - days: 7
              price:
                  rate: 10 # N% 以上の下落で発火
                  value: 1000 # N 円以上の下落で発火（通貨換算後）
            - days: 30
              price:
                  rate: 5
    lowest: # 最安値更新イベント判定（省略時は即発火）
        rate: 1 # 直近の最安値イベントから N% 以上の下落で発火
        value: 100 # N 円以上の下落で発火（通貨換算後）
    currency: # 通貨換算レート（value 判定に使用）
        - label: ドル # ストアの price_unit に対応
          rate: 150 # 1単位あたりの円換算レート

slack:
    bot_token: "xoxb-..."
    from: "price-watch"
    info:
        channel:
            name: "#price"
    error:
        channel:
            name: "#error"
            id: "C0123456789"
        interval_min: 60

store:
    amazon:
        associate: "XXXXXX-22"
        access_key: "..."
        secret_key: "..."
        host: "webservices.amazon.co.jp"
        region: "us-west-2"

    yahoo:
        client_id: "..."
        secret: "..."

data:
    selenium: ./data # Selenium プロファイル
    dump: ./data/debug # デバッグダンプ
    price: ./data/price # 価格履歴 DB
    thumb: ./data/thumb # サムネイル画像
    metrics: ./data/metrics # メトリクス

liveness:
    file:
        crawler: /dev/shm/healthz
    interval_sec: 300
```

#### target.yaml

```yaml
# カテゴリー表示順（省略可）
# フロントエンドのトップページでアイテムをカテゴリー別にグルーピング表示する。
# 「その他」をリストに含めるとその位置に表示。含めない場合は末尾に表示。
# リストにないカテゴリーは、リスト記載カテゴリーの後にアルファベット順で表示。
category_list:
    - PC パーツ
    - IoT デバイス
    - フリマ
    - その他

store_list:
    - name: ヨドバシ
      price_xpath: '//span[@id="js_scl_salesPrice"]/span[1]'
      thumb_img_xpath: '//img[@id="mainImg"]/@src'
      unavailable_xpath: '//p[contains(@class, "orderInfo")]/span[text()="販売休止中"]'

    - name: Amazon
      check_method: my_lib.store.amazon.api
      affiliate_id: "my-tag-22" # アフィリエイトタグ（URLに ?tag=... を付与）

    - name: メルカリ
      check_method: my_lib.store.mercari.search
      affiliate_id: "my_mercari_affiliate" # アフィリエイトID（URLに ?afid=... を付与）

    - name: ラクマ
      check_method: my_lib.store.rakuma.search
      affiliate_id: "my_rakuma_affiliate" # アフィリエイトID（URLに ?afid=... を付与）

    - name: PayPayフリマ
      check_method: my_lib.store.paypay.search
      affiliate_id: "my_paypay_affiliate" # アフィリエイトID（URLに ?afid=... を付与）

    - name: Yahoo
      check_method: my_lib.store.yahoo.api

    - name: 楽天
      check_method: my_lib.store.rakuten.api

item_list:
    # 1アイテム=複数ストアの例（category でカテゴリーを指定）
    - name: 商品名
      category: PC パーツ # カテゴリー名（省略時は「その他」）
      store:
          - name: ヨドバシ
            url: https://www.yodobashi.com/product/...
          - name: Amazon
            asin: B0XXXXXXXX

    # フリマ検索（メルカリ・ラクマ・PayPayフリマ）
    - name: フリマ商品
      category: フリマ
      cond: NEW|LIKE_NEW # アイテムレベルで商品状態を指定（省略時デフォルト: NEW|LIKE_NEW）
      price:
          - 10000 # price_min
          - 50000 # price_max
      store:
          - name: メルカリ
            search_keyword: 検索キーワード # 省略時は name で検索
            exclude_keyword: ジャンク # 除外キーワード（省略可）
          - name: ラクマ
          - name: PayPayフリマ

    # Yahoo検索（キーワード検索）
    - name: Yahoo商品
      store:
          - name: Yahoo
            search_keyword: 検索キーワード # 省略時は name で検索
            price:
                - 10000 # price_min
                - 50000 # price_max
            cond: new # new（デフォルト）or used

    # Yahoo検索（JANコード検索）
    - name: Yahoo商品（JAN）
      store:
          - name: Yahoo
            jan_code: "4901234567890"

    # 楽天検索（キーワード検索、除外キーワード対応）
    - name: 楽天商品
      store:
          - name: 楽天
            search_keyword: 検索キーワード # 省略時は name で検索
            exclude_keyword: 中古 ジャンク # 除外キーワード（スペース区切りで複数指定可）
            price:
                - 10000 # price_min
                - 50000 # price_max
```

## デプロイ

### Kubernetes

- `Deployment` で1レプリカ運用
- `/dev/shm` を EmptyDir (Memory) でマウント（Chrome 用、1GB 以上確保）
- Liveness Probe で `price-watch-healthz` を実行
- CPU: 2コア、メモリ: 4GB

### Docker

```bash
docker compose up
```

## 依存ライブラリ

### 主要な外部依存

| ライブラリ                | 用途                              |
| ------------------------- | --------------------------------- |
| undetected-chromedriver   | bot 検出回避付き Chrome WebDriver |
| selenium                  | ブラウザ自動操作                  |
| amazon-paapi5             | Amazon Product Advertising API    |
| pydub / speechrecognition | CAPTCHA 音声認識                  |
| flask / flask-cors        | Web API サーバー                  |
| pillow                    | 画像処理（サムネイル）            |

### my-lib（自作共通ライブラリ）

| モジュール               | 用途                                                             |
| ------------------------ | ---------------------------------------------------------------- |
| my_lib.selenium_util     | WebDriver 作成・操作ユーティリティ                               |
| my_lib.config            | YAML 設定ファイル読み込み（スキーマ検証付き）                    |
| my_lib.notify.slack      | Slack 通知（レート制限機能付き）                                 |
| my_lib.healthz           | Liveness チェック                                                |
| my_lib.footprint         | タイムスタンプファイル管理                                       |
| my_lib.store.flea_market | フリマ検索共通型（ItemCondition, SearchCondition, SearchResult） |
| my_lib.store.mercari.\*  | メルカリ検索                                                     |
| my_lib.store.rakuma.\*   | ラクマ検索                                                       |
| my_lib.store.paypay.\*   | PayPayフリマ検索                                                 |
| my_lib.store.amazon.\*   | Amazon API 関連                                                  |
| my_lib.store.yahoo.\*    | Yahoo!ショッピング API 関連                                      |
| my_lib.store.rakuten.\*  | 楽天市場 API 関連                                                |

## コーディング規約

- Python 3.11+
- 型ヒントを積極的に使用
- dataclass で不変オブジェクトを定義（`frozen=True`）
- ruff でフォーマット・lint
- pyright で型チェック

### インポートスタイル

`from xxx import yyy` は基本的に使わず、`import yyy` としてモジュールをインポートし、使用時は `yyy.xxx` の形式で参照する。

```python
# Good
import my_lib.selenium_util
my_lib.selenium_util.get_driver()

# Avoid
from my_lib.selenium_util import get_driver
get_driver()
```

**例外:**

- 標準ライブラリの一般的なパターン（例: `from pathlib import Path`）
- 型ヒント用のインポート（`from typing import TYPE_CHECKING`）
- dataclass などのデコレータ（`from dataclasses import dataclass`）

### 型チェック（pyright）

pyright のエラー対策として、各行に `# type: ignore` コメントを付けて回避するのは**最後の手段**とします。

基本方針:

1. **型推論が効くようにコードを書く** - 明示的な型注釈や適切な変数の初期化で対応
2. **型の絞り込み（Type Narrowing）を活用** - `assert`, `if`, `isinstance()` 等で型を絞り込む
3. **どうしても回避できない場合のみ `# type: ignore`** - その場合は理由をコメントに記載

```python
# Good: 型の絞り込み
value = get_optional_value()
assert value is not None
use_value(value)

# Avoid: type: ignore での回避
value = get_optional_value()
use_value(value)  # type: ignore
```

**例外:** テストコードでは、モックオブジェクトの使用など型チェックが困難な場合に `# type: ignore` を使用可能です。

### PEP 8 準拠

#### コレクションの空チェック

`len()` を使った比較ではなく、bool 評価を使用する:

```python
# Good
if not items:
    return
if elements:
    process(elements)

# Avoid
if len(items) == 0:
    return
if len(elements) != 0:
    process(elements)
```

### dataclass 優先

辞書（`dict[str, Any]`）よりも dataclass を優先する。特に:

- 複数の関数間で受け渡されるデータ構造
- 型安全性が重要なケース
- 属性アクセスが頻繁なケース

```python
# Good
@dataclass(frozen=True)
class TaskRequest:
    queue_name: str
    items: list[Item]
    timestamp: float = 0.0

def process(task: TaskRequest) -> None:
    print(task.queue_name)

# Avoid
def process(task: dict[str, Any]) -> None:
    print(task["queue_name"])
```

**ポイント:**

- 不変データには `frozen=True` を使用
- デフォルト値は `field(default=...)` または直接指定
- Union 型は `TypeA | TypeB` 形式で定義

### match 文の活用

`isinstance()` チェックよりも `match` 文を優先する（Python 3.10+）:

```python
# Good
match check_method:
    case CheckMethod.SCRAPE:
        scrape.check(...)
    case CheckMethod.AMAZON_PAAPI:
        amazon.paapi.check(...)
    case _:
        raise ValueError(f"Unknown check method: {check_method}")

# Avoid
if check_method == CheckMethod.SCRAPE:
    scrape.check(...)
elif check_method == CheckMethod.AMAZON_PAAPI:
    amazon_paapi.check(...)
```

### functools の活用

手動でキャッシュを実装するのではなく、標準ライブラリを活用:

```python
# Good
from functools import lru_cache

@lru_cache(maxsize=10000)
def get_cached_value(key: str) -> Value:
    return compute_value(key)

# Avoid: 手動 LRU 実装
_cache: dict[str, Value] = {}
def get_cached_value(key: str) -> Value:
    if key in _cache:
        return _cache[key]
    # ...
```

### パス管理

スキーマファイルや設定ファイルへのパスは、相対パスではなく `pathlib.Path(__file__)` を基準とした絶対パスを使用する。

```python
# Good
_SCHEMA_DIR = pathlib.Path(__file__).parent.parent / "schema"
_SCHEMA_CONFIG = _SCHEMA_DIR / "config.schema"

# Avoid
_SCHEMA_CONFIG = "schema/config.schema"  # 実行ディレクトリに依存
```

#### パス型の統一

ファイルパスを関数やクラスの引数として受け取る場合は `pathlib.Path` 型で統一し、文字列での受け渡しは避ける。

```python
# Good
def __init__(self, db_path: pathlib.Path):
    self.db_path = db_path

# Avoid
def __init__(self, db_path: str = "data/cache.db"):
    self.db_path = pathlib.Path(db_path)
```

### 時刻処理

`datetime.now()` の代わりに `my_lib.time.now()` を使用し、時刻処理を統一する。

```python
# Good
import my_lib.time
now = my_lib.time.now()

# Avoid
from datetime import datetime
now = datetime.now()
```

### datetime import について

`from datetime import datetime, timedelta` は許容されるパターンです。
ただし、現在時刻の取得は必ず `my_lib.time.now()` を使用してください。

```python
# Good
import my_lib.time
from datetime import datetime, timedelta

now = my_lib.time.now()  # 現在時刻
parsed = datetime.fromisoformat(date_str)  # ISO文字列のパース
delta = timedelta(days=1)  # 時間差

# Avoid
from datetime import datetime
now = datetime.now()  # NG: タイムゾーンが考慮されない
```

### 返り値の型

関数の返り値に `dict[str, Any]` を使用せず、dataclass を定義して型安全性を確保する。

```python
# Good
@dataclass(frozen=True)
class PriceInfo:
    price: int
    stock: int

def get_price() -> PriceInfo | None:
    ...

# Avoid
def get_price() -> dict[str, Any] | None:
    ...
```

## 開発ワークフロー規約

### リポジトリ構成

- **プライマリリポジトリ**: GitLab (`gitlab.green-rabbit.net`)
- **ミラーリポジトリ**: GitHub (`github.com/kimata/price-watch`)

GitLab にプッシュすると、自動的に GitHub にミラーリングされます。GitHub への直接プッシュは不要です。

### コミット時の注意

- 今回のセッションで作成し、プロジェクトが機能するのに必要なファイル以外は git add しないこと
- 気になる点がある場合は追加して良いか質問すること

### バグ修正の原則

- 憶測に基づいて修正しないこと
- 必ず原因を論理的に確定させた上で修正すること
- 「念のため」の修正でコードを複雑化させないこと

### コード修正時の確認事項

- 関連するテストも修正すること
- 関連するドキュメントも更新すること
- mypy, pyright, ty がパスすることを確認すること

### リリース（タグ作成）時

リリースタグを作成する際は、以下の手順に従うこと：

1. **CHANGELOG.md を更新する**
    - 新しいバージョンのセクションを追加
    - 内容はコミット履歴の変更点から抽出することとするが、システムとしての変更点は見逃さないこと
    - 含まれる変更を以下のカテゴリで記載（絵文字付き）：
        - `### ✨ Added`: 新機能
        - `### 🔄 Changed`: 既存機能の変更
        - `### 🐛 Fixed`: バグ修正
        - `### 🗑️ Removed`: 削除された機能
        - `### 🔒 Security`: セキュリティ関連の修正
        - `### ⚡ Performance`: パフォーマンス改善
        - `### 📝 Documentation`: ドキュメント更新
        - `### 🧪 Tests`: テスト関連
        - `### 🔧 CI`: CI/CD 関連
        - `### 🏗️ Infrastructure`: インフラ関連
    - **重要**: システムとしての新機能（新しいストア対応、新しい監視方式など）は漏らさず記載すること
        - 細かい実装の改善よりも、ユーザー視点での機能追加を優先して記載
        - 例: 「メルカリ対応」「アイテム詳細ページの実装」など
    - [Keep a Changelog](https://keepachangelog.com/) 形式を参考にする

2. **タグを作成する**
    ```bash
    git tag -a v1.x.x -m "バージョン説明"
    git push origin v1.x.x
    ```
