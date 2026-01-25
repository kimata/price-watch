# Changelog

このプロジェクトの注目すべき変更点をすべてこのファイルに記載します。

このファイルのフォーマットは [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/) に基づいており、
このプロジェクトは [Semantic Versioning](https://semver.org/spec/v2.0.0.html) に準拠しています。

## [Unreleased]

## [0.1.1] - 2026-01-25

### ✨ Added

- ヨドバシ等のボット検出を回避する User-Agent 動的生成機能
- WebUI による価格履歴ダッシュボード（React フロントエンド）

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

[Unreleased]: https://gitlab.green-rabbit.net/kimata/price-watch/compare/v0.1.1...HEAD
[0.1.1]: https://gitlab.green-rabbit.net/kimata/price-watch/compare/v0.1.0...v0.1.1
[0.1.0]: https://gitlab.green-rabbit.net/kimata/price-watch/commits/v0.1.0
