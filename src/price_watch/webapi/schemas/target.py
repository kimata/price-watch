#!/usr/bin/env python3
"""
Pydantic schemas for target.yaml editor API.

These schemas define the contract for the target.yaml configuration editor,
ensuring type safety and validation for API requests and responses.
"""

from my_lib.pydantic.base import BaseSchema
from pydantic import Field

# === チェックメソッド定義 ===
# target.py の CheckMethod enum に対応
CHECK_METHODS = [
    "scrape",
    "my_lib.store.amazon.api",
    "my_lib.store.mercari.search",
    "my_lib.store.rakuma.search",
    "my_lib.store.paypay.search",
    "my_lib.store.yahoo.api",
    "my_lib.store.rakuten.api",
    "my_lib.store.yodobashi.scrape",
]

# === アクションタイプ定義 ===
ACTION_TYPES = ["click", "input", "sixdigit", "recaptcha"]

# === check_method ごとの必須フィールド定義 ===
# バリデーション時に参照する
# フィールド名をそのまま指定: そのフィールドが必須
# "url_or_asin": url または asin のいずれかが必要
# 定義なし or 空リスト: 必須フィールドなし（検索系など）
#
# Note: XPath 系フィールドはストア定義またはアイテムのストアエントリで指定可能
#       ストア定義で指定されていればアイテム側では省略可能
CHECK_METHOD_REQUIRED_FIELDS: dict[str, list[str]] = {
    "scrape": ["url", "price_xpath", "unavailable_xpath", "thumb_img_xpath"],
    "my_lib.store.amazon.api": ["url_or_asin"],
    "my_lib.store.yodobashi.scrape": ["url"],
    # 検索系は URL/ASIN 不要（検索結果から動的に取得）
    # "my_lib.store.mercari.search": [],
    # "my_lib.store.rakuma.search": [],
    # "my_lib.store.paypay.search": [],
    # "my_lib.store.yahoo.api": [],
    # "my_lib.store.rakuten.api": [],
}


# === リクエスト/レスポンス用スキーマ ===


class ActionStepSchema(BaseSchema):
    """アクションステップ."""

    type: str = Field(..., description="アクションタイプ (click, input, sixdigit, recaptcha)")
    xpath: str | None = Field(default=None, description="操作対象の XPath")
    value: str | None = Field(default=None, description="入力値（input タイプの場合）")


class PreloadConfigSchema(BaseSchema):
    """プリロード設定."""

    url: str = Field(..., description="プリロード URL")
    every: int = Field(default=1, ge=1, description="何アイテムおきにプリロードするか")


class StoreDefinitionSchema(BaseSchema):
    """ストア定義."""

    name: str = Field(..., min_length=1, description="ストア名")
    check_method: str = Field(default="scrape", description="チェック方法")
    price_xpath: str | None = Field(default=None, description="価格の XPath")
    thumb_img_xpath: str | None = Field(default=None, description="サムネイル画像の XPath")
    unavailable_xpath: str | None = Field(default=None, description="在庫なし判定の XPath")
    price_unit: str = Field(default="円", description="価格の通貨単位")
    point_rate: float = Field(default=0.0, ge=0.0, le=100.0, description="ポイント還元率（%）")
    color: str | None = Field(default=None, description="ストアの色（hex形式）")
    action: list[ActionStepSchema] = Field(default_factory=list, description="アクションステップ")
    affiliate_id: str | None = Field(default=None, description="アフィリエイトID")


class StoreEntrySchema(BaseSchema):
    """アイテムのストアエントリ（新書式用）."""

    name: str = Field(..., min_length=1, description="ストア名")
    url: str | None = Field(default=None, description="商品 URL")
    asin: str | None = Field(default=None, description="Amazon ASIN")
    price_xpath: str | None = Field(default=None, description="価格の XPath（ストア定義を上書き）")
    thumb_img_xpath: str | None = Field(default=None, description="サムネイル画像の XPath")
    unavailable_xpath: str | None = Field(default=None, description="在庫なし判定の XPath")
    price_unit: str | None = Field(default=None, description="価格の通貨単位")
    preload: PreloadConfigSchema | None = Field(default=None, description="プリロード設定")
    # 検索系ストア用
    search_keyword: str | None = Field(default=None, description="検索キーワード")
    exclude_keyword: str | None = Field(default=None, description="除外キーワード")
    price: list[int] | None = Field(default=None, description="価格範囲 [min] or [min, max]")
    cond: str | None = Field(default=None, description="商品状態")
    jan_code: str | None = Field(default=None, description="JANコード（Yahoo検索用）")


class ItemDefinitionSchema(BaseSchema):
    """アイテム定義."""

    name: str = Field(..., min_length=1, description="アイテム名")
    category: str | None = Field(default=None, description="カテゴリー名")
    # アイテムレベルの共通設定
    price: list[int] | None = Field(default=None, description="価格範囲 [min] or [min, max]")
    cond: str | None = Field(default=None, description="商品状態")
    # ストアリスト（新書式）
    store: list[StoreEntrySchema] = Field(..., min_length=1, description="ストアリスト")


class TargetConfigSchema(BaseSchema):
    """ターゲット設定（target.yaml）."""

    category_list: list[str] = Field(default_factory=list, description="カテゴリー表示順")
    store_list: list[StoreDefinitionSchema] = Field(default_factory=list, description="ストア定義リスト")
    item_list: list[ItemDefinitionSchema] = Field(default_factory=list, description="アイテム定義リスト")


# === API レスポンス ===


class TargetConfigResponse(BaseSchema):
    """GET /api/target のレスポンス."""

    config: TargetConfigSchema
    check_methods: list[str] = Field(default_factory=lambda: CHECK_METHODS)
    action_types: list[str] = Field(default_factory=lambda: ACTION_TYPES)
    require_password: bool = Field(default=False, description="保存時にパスワードが必要か")


class TargetUpdateRequest(BaseSchema):
    """PUT /api/target のリクエスト."""

    config: TargetConfigSchema
    create_backup: bool = Field(default=True, description="バックアップを作成するか")
    password: str | None = Field(default=None, description="認証パスワード")


class TargetUpdateResponse(BaseSchema):
    """PUT /api/target のレスポンス."""

    success: bool = Field(..., description="保存成功かどうか")
    git_pushed: bool = Field(default=False, description="Git push が実行されたか")
    git_commit_url: str | None = Field(default=None, description="コミット URL")


class ValidationError(BaseSchema):
    """バリデーションエラー詳細."""

    path: str = Field(..., description="エラー箇所のパス")
    message: str = Field(..., description="エラーメッセージ")


class ValidateResponse(BaseSchema):
    """POST /api/target/validate のレスポンス."""

    valid: bool
    errors: list[ValidationError] = Field(default_factory=list)


class CheckItemRequest(BaseSchema):
    """POST /api/target/check-item のリクエスト."""

    item_name: str = Field(..., description="アイテム名")
    store_name: str = Field(..., description="ストア名")


class CheckItemResponse(BaseSchema):
    """POST /api/target/check-item のレスポンス."""

    job_id: str = Field(..., description="ジョブID")


class CheckJobStatus(BaseSchema):
    """チェックジョブのステータス."""

    job_id: str
    status: str = Field(..., description="pending, running, completed, failed")
    progress: float = Field(default=0.0, ge=0.0, le=100.0)
    logs: list[str] = Field(default_factory=list)
    result: dict | None = Field(default=None, description="チェック結果")
    error: str | None = Field(default=None, description="エラーメッセージ")
