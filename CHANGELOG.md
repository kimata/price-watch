# Changelog

このプロジェクトの注目すべき変更点をすべてこのファイルに記載します。

このファイルのフォーマットは [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/) に基づいており、
このプロジェクトは [Semantic Versioning](https://semver.org/spec/v2.0.0.html) に準拠しています。

## [Unreleased]

## [0.1.4] - 2026-02-12

### ✨ Added

- **チャート静的画像生成** — トップページのチャートを Canvas から静的 PNG 画像に変更（Selenium + Chart.js）
- **ChartImageWorker** — Flask リクエストとバックグラウンド生成を単一スレッドで処理するワーカーを実装
- **target.yaml Web エディタ** — パスワード認証付きの Web UI でアイテム・ストアを編集、Git Push 機能も搭載
- **楽天市場検索ストア** — 楽天市場 API を使用したキーワード検索による価格監視に対応
- **ヨドバシ.com 専用スクレイピング** — `my_lib.store.yodobashi.scrape` を使用した専用スクレイパーと商品検索機能を追加
- **Amazon 商品検索** — ASIN を選択して監視対象に追加できる検索機能を実装
- **アフィリエイト ID 対応** — ストアごとにアフィリエイト ID を設定可能に
- **価格記録編集ページ** — 過去の価格記録を編集・削除する管理機能を追加
- **ストア順序のドラッグ&ドロップ** — target.yaml エディタでストア一覧の順序をドラッグ操作で変更可能に
- **target.yaml 変更時の Slack 通知** — アイテム追加・削除・変更を Slack に通知
- **フリマ検索のリトライ・ウォームアップ** — 失敗アイテムを1回リトライ、初回アクセス前のウォームアップ機能を追加
- **グローバルエラーハンドラー** — フロントエンドの未処理エラーをキャッチして表示
- **フロントエンド UI 改善** — お気に入り機能、検索フィルター、ページネーション、ストアアイコン表示
- イベント通知とログに外貨（`price_unit`）を表示
- Twitter 共有メッセージに最安値とストア名を追加
- 巡回完了時にページコンテンツを自動更新（SSE）
- グラフで通貨を円換算して表示

### 🔄 Changed

- チャート画像生成のタイムアウトを 30 秒から 120 秒に延長
- タイムアウト時は 503 エラーではなくプレースホルダー画像を返す（10 秒キャッシュでリトライを促す）
- ChartImageWorker 用に専用の Chrome プロファイルディレクトリを使用
- アイテム詳細ページのストア別価格表示を大きく
- アイテム詳細ページのセクション順序を変更
- API レスポンスに Cache-Control ヘッダーを追加

### 🐛 Fixed

- E2E テストを静的チャート画像に対応
- Selenium テストの並列実行時の Chrome プロファイル競合を修正
- ChartImage コンポーネントに一意の key を追加（同一行の商品で同じグラフが表示される問題を修正）
- ヨドバシ販売終了商品を在庫なしとして正しく処理
- 価格要素がない販売終了商品を在庫なしとして扱う
- Slack 通知のサムネイル URL が二重パスになる問題を修正
- Web API の target.yaml キャッシュが CLI 指定のパスを参照しない問題を修正

### 🔒 Security

- URL ガードによる SSRF 対策を追加
- check-item API を target.yaml 保存済みアイテムのみに制限
- パスワード認証をハッシュ検証に変更
- config.yaml 読み込み失敗時に API を無効化
- IP ベースの認証失敗レート制限を追加
- 1 時間に 5 回認証失敗ごとに Slack 通知を送信

### ⚡ Performance

- `/api/items` の N+1 クエリ問題を解消
- フロントエンドのパフォーマンス改善
- テストジョブの並列実行を有効化
- CI のキャッシュ最適化

### 📝 Documentation

- README にクイックスタートと Web 編集機能の説明を追加

## [0.1.3] - 2026-01-28

### ✨ Added

- **ラクマ・PayPayフリマ検索対応** — フリマ検索を統合モジュールに集約し、メルカリに加えてラクマ・PayPayフリマのキーワード検索による価格監視に対応
- **Yahoo!ショッピング検索対応** — Yahoo!ショッピング API を使用したキーワード検索・JAN コード検索による価格チェック機能を追加
- **OGP 画像生成** — アイテム詳細ページ向けの OGP 画像を自動生成（サムネイル・価格グラフ・最安値ラベル・正方形画像対応）
- **巡回メトリクスページ** — 巡回メトリクス記録機能とダッシュボード（稼働率、巡回統計グラフ、リアルタイム更新インジケーター）を追加
- **トップページのカテゴリー別表示** — `target.yaml` の `category_list` に基づくカテゴリー別アイテムグルーピング表示
- **target.yaml 新書式** — 1アイテムに複数ストアを紐付ける書式に対応、`price`/`cond` のアイテムレベル指定に対応
- **イベント判定の閾値・通貨換算** — 価格下落イベントにウィンドウ別の閾値（率・金額）と通貨換算レートを導入
- 特定アイテム・ストアを指定してデバッグ実行できる `-D` オプション
- ストアごとの通貨単位（`price_unit`）表示対応
- 在庫復活判定に最小在庫なし継続時間を追加
- 情報取得エラーイベントの追加
- イベント通知のタイトルにアイテム名を含める
- 検索結果のキーワード全断片一致フィルタリング
- OGP 画像に同名アイテムの全ストアグラフを描画
- イベント一覧に「全て」チェックボックスを追加
- 価格履歴の外れ値削除スクリプト、未記録イベント補完スクリプト、OGP キャッシュ削除スクリプトを追加
- ドライバー作成失敗時のプロファイル削除リトライ機能

### 🔄 Changed

- Manager パターンによる大規模リファクタリング（`ConfigManager`, `BrowserManager`, `HistoryManager`, `MetricsManager`）
- `dict[str, Any]` を dataclass（`ResolvedItem`/`CheckedItem`）に置換
- `history.py` を `HistoryManager` に移行
- `amazon/` を `store/amazon/` に移動
- SQL スキーマとバリデーションスキーマを外部ファイルに分離
- DB ファイル名を `price.db` に変更し定数で一元管理
- メトリクス DB に `work_ended_at` カラムを追加
- ストア名を `target.yaml` から動的に取得
- メルカリ検索の `cond` 省略時デフォルトを `NEW|LIKE_NEW` に変更
- イベントバナーをテーブル形式にリニューアル
- イベント表示名を短縮
- 巡回時間グラフを日単位の時系列箱ひげ図に変更しストア別グラフを追加
- ヒートマップの日付ラベルのフォントサイズを拡大

### 🐛 Fixed

- 非表示要素がマッチした場合に価格取得が失敗する問題を修正
- Yahoo 検索アイテムがグラフ・パネルに表示されない問題を修正
- 検索系ストアの `item_key` にストア名を含めて衝突を回避
- サムネイル画像のアスペクト比維持、最小サイズチェック追加
- `stock` カラムを NULL 許可に変更するマイグレーション追加
- セッション期間からスリープ時間を除外
- 最安値更新イベントの配色を rose から green に変更
- イベント判定を価格履歴挿入前に実行するよう修正
- トップページグラフの Y 軸に通貨単位を常に表示
- クリック可能な要素に `cursor-pointer` を追加
- フリマ検索のタイムアウトを失敗扱いに変更

### ⚡ Performance

- トップページのパフォーマンス最適化

### 🧪 Tests

- テストカバレッジを 78% から 92% に向上
- `captcha.py`, `history.py`, `store/scrape.py`, `target.py`, `thumbnail.py`, `metrics.py` のユニットテストを追加

### 🔧 CI

- GitHub Actions で Docker イメージをビルド・登録するワークフローを追加
- pre-commit に mypy を追加

### 📝 Documentation

- README.md を刷新し GitHub Actions バッジを追加
- Docker Compose での動作手順を詳細化

## [0.1.2] - 2026-01-26

### ✨ Added

- **メルカリ対応**
    - `my_lib.store.mercari.search` を使用したキーワード検索による価格監視
    - 検索キーワード、価格範囲、商品状態（新品/未使用に近い等）での絞り込み
    - 最大40件から最安値商品を自動選定
    - 検索条件が同じアイテムは同一として履歴を管理
    - PR（広告）アイテムの自動除外
- アイテム詳細ページの実装（価格履歴グラフ、イベント履歴表示）
- 価格グラフの凡例クリックによる系列選択機能
- 価格グラフの在庫なし期間を灰色で表示

### 🔄 Changed

- DB スキーマ変更: `url_hash` を `item_key` にリネーム（検索ベースのアイテム対応）
- 価格情報がないアイテムに「価格情報なし」を表示
- イベント履歴の日時表示を日本語形式（「YYYY年M月D日 H:mm」）に変更
- トップページのイベントバナーを横長レイアウトに変更
- 価格グラフ横軸のラベルに日付を追加

## [0.1.1] - 2026-01-25

### ✨ Added

- **WebUI による価格履歴ダッシュボード**
    - React + TypeScript + Tailwind CSS によるフロントエンド
    - アイテム一覧表示（サムネイル、現在価格、在庫状況）
    - 価格推移グラフ（Chart.js）
    - イベントバナー（値下げ、在庫復活、最安値更新等のリアルタイム表示）
    - Flask による REST API サーバー
- ヨドバシ等のボット検出を回避する User-Agent 動的生成機能

### 🔄 Changed

- Poetry から uv に移行
- src/price_watch/ パッケージ構成に変更
- CLAUDE.md 準拠のコーディング規約に基づきリファクタリング
    - インポートスタイルを `import xxx` 形式に統一
    - `datetime.now()` を `my_lib.time.now()` に変更
    - 空チェックを bool 評価に変更
    - if-elif チェーンを match 文に変換
- pytest によるテストを追加
- ruff による linter/formatter 設定
- GitLab CI 設定を追加

### 🐛 Fixed

- ログ出力の抑制
- ヨドバシ対策の改善

## [0.1.0] - 2023-09-02

### ✨ Added

- 商品価格監視機能
    - スクレイピングによる価格取得（ヨドバシ、Yahoo ショッピング、Switch Science、Ubiquiti Store USA、Lenovo）
    - Amazon PA-API による価格取得
    - サムネイル画像の自動取得
- 価格変動・在庫復活の Slack 通知
- 最低価格更新時の通知機能
- 価格履歴の SQLite 保存
- reCAPTCHA / CAPTCHA 音声認識による自動解決
- 価格取得エラー継続時の Slack 通知
- Kubernetes / Docker 対応
- Liveness Probe 対応

### 🔧 CI

- pre-commit 設定
- Renovate 設定

[Unreleased]: https://gitlab.green-rabbit.net/kimata/price-watch/compare/v0.1.4...HEAD
[0.1.4]: https://gitlab.green-rabbit.net/kimata/price-watch/compare/v0.1.3...v0.1.4
[0.1.3]: https://gitlab.green-rabbit.net/kimata/price-watch/compare/v0.1.2...v0.1.3
[0.1.2]: https://gitlab.green-rabbit.net/kimata/price-watch/compare/v0.1.1...v0.1.2
[0.1.1]: https://gitlab.green-rabbit.net/kimata/price-watch/compare/v0.1.0...v0.1.1
[0.1.0]: https://gitlab.green-rabbit.net/kimata/price-watch/commits/v0.1.0
