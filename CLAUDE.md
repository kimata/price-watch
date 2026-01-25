# CLAUDE.md

このファイルは Claude Code がこのリポジトリで作業する際のガイダンスを提供します。

## 概要

商品価格を監視して通知するスクリプトです。オンラインショップの価格をスクレイピングまたは Amazon PA-API で取得し、価格変動や在庫復活を検出して Slack に通知します。Selenium と undetected-chromedriver を使用してブラウザを操作します。

対応ショップ:

- Amazon.co.jp（PA-API / スクレイピング）
- ヨドバシ.com
- Yahoo ショッピング
- Switch Science
- Ubiquiti Store USA
- Lenovo

## 重要な注意事項

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
    ├── config.py               # 型付き設定クラス（dataclass）
    ├── const.py                # 定数
    │
    ├── target.py               # ターゲット設定クラス（dataclass + Protocol）
    ├── item.py                 # アイテムリスト管理
    │
    ├── amazon/                 # Amazon 関連モジュール
    │   ├── paapi.py            # Amazon PA-API による価格取得
    │   └── paapi_rate_limiter.py # PA-API レート制限
    │
    ├── store/                  # ストア別価格取得（スクレイピング）
    │   └── scrape.py           # スクレイピングによる価格チェック
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

#### AppRunner (`cli/app.py`)

アプリケーション全体のライフサイクルを管理するクラス。シグナルハンドラ、WebUI サーバー、メイン監視ループを統合します。

```python
runner = AppRunner(config_file, target_file, port, debug_mode=debug_mode)
runner.setup_signal_handlers()
runner.start_webui_server()
runner.execute()
```

#### 実行フロー

```
price-watch (cli/app.py)
├── initialize() → AppConfig 読み込み、履歴 DB 初期化
├── start_webui_server() → Flask サーバー起動
├── create_driver() → Selenium WebDriver 作成
├── execute() → メイン監視ループ
│   ├── _load_item_list() → target.yaml からアイテム読み込み
│   ├── _do_work() → 各アイテムの価格チェック
│   │   ├── scrape.check() → スクレイピング
│   │   └── amazon.paapi.check_item_list() → PA-API
│   ├── _process_data() → 価格変動検出・履歴保存
│   │   └── notify.info() → Slack 通知
│   └── _sleep_until() → 次回チェックまで待機
└── cleanup() → 終了処理
```

### データモデル

#### target.py

```python
# Enum
CheckMethod: SCRAPE, AMAZON_PAAPI
ActionType: CLICK, INPUT, SIXDIGIT, RECAPTCHA

# Protocol
HasName, HasUrl, HasStore, HasXPathConfig, HasCheckMethod
WatchItem  # 監視対象アイテムの Protocol

# dataclass
ActionStep       # アクションステップ（type, xpath, value）
PreloadConfig    # プリロード設定（url, every）
StoreDefinition  # ストア定義（name, check_method, price_xpath 等）
ItemDefinition   # アイテム定義（name, store, url, asin 等）
ResolvedItem     # ストア定義とマージ済みのアイテム
TargetConfig     # ターゲット設定（stores, items）
```

### 設定ファイル

#### config.yaml

```yaml
check:
    interval_sec: 1800 # 監視周期（秒）

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
store_list:
    - name: ヨドバシ
      price_xpath: '//span[@id="js_scl_salesPrice"]/span[1]'
      thumb_img_xpath: '//img[@id="mainImg"]/@src'
      unavailable_xpath: '//p[contains(@class, "orderInfo")]/span[text()="販売休止中"]'

    - name: Amazon
      check_method: amazon-paapi

item_list:
    - name: 商品名
      store: ヨドバシ
      url: https://www.yodobashi.com/product/...

    - name: Amazon 商品
      store: Amazon
      asin: B0XXXXXXXX
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

| モジュール             | 用途                                          |
| ---------------------- | --------------------------------------------- |
| my_lib.selenium_util   | WebDriver 作成・操作ユーティリティ            |
| my_lib.config          | YAML 設定ファイル読み込み（スキーマ検証付き） |
| my_lib.notify.slack    | Slack 通知（レート制限機能付き）              |
| my_lib.healthz         | Liveness チェック                             |
| my_lib.footprint       | タイムスタンプファイル管理                    |
| my_lib.store.amazon.\* | Amazon API 関連                               |

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
    - [Keep a Changelog](https://keepachangelog.com/) 形式を参考にする

2. **タグを作成する**
    ```bash
    git tag -a v1.x.x -m "バージョン説明"
    git push origin v1.x.x
    ```
