/**
 * target.yaml エディタ用の型定義
 */

// チェックメソッドの型
export type CheckMethod =
    | "scrape"
    | "my_lib.store.amazon.api"
    | "my_lib.store.mercari.search"
    | "my_lib.store.rakuma.search"
    | "my_lib.store.paypay.search"
    | "my_lib.store.yahoo.api";

// アクションタイプの型
export type ActionType = "click" | "input" | "sixdigit" | "recaptcha";

// アクションステップ
export interface ActionStep {
    type: ActionType;
    xpath?: string | null;
    value?: string | null;
}

// プリロード設定
export interface PreloadConfig {
    url: string;
    every: number;
}

// ストア定義（store_list 内の要素）
export interface StoreDefinitionConfig {
    name: string;
    check_method: CheckMethod;
    price_xpath?: string | null;
    thumb_img_xpath?: string | null;
    unavailable_xpath?: string | null;
    price_unit: string;
    point_rate: number;
    color?: string | null;
    action: ActionStep[];
    affiliate_id?: string | null;
}

// アイテムのストアエントリ（新書式用）
export interface StoreEntryConfig {
    name: string;
    url?: string | null;
    asin?: string | null;
    price_xpath?: string | null;
    thumb_img_xpath?: string | null;
    unavailable_xpath?: string | null;
    price_unit?: string | null;
    preload?: PreloadConfig | null;
    search_keyword?: string | null;
    exclude_keyword?: string | null;
    price?: number[] | null;
    cond?: string | null;
    jan_code?: string | null;
}

// アイテム定義（item_list 内の要素）
export interface ItemDefinitionConfig {
    name: string;
    category?: string | null;
    price?: number[] | null;
    cond?: string | null;
    store: StoreEntryConfig[];
}

// ターゲット設定全体
export interface TargetConfig {
    category_list: string[];
    store_list: StoreDefinitionConfig[];
    item_list: ItemDefinitionConfig[];
}

// API レスポンス: GET /api/target
export interface TargetConfigResponse {
    config: TargetConfig;
    check_methods: string[];
    action_types: string[];
    require_password: boolean;
}

// API リクエスト: PUT /api/target
export interface TargetUpdateRequest {
    config: TargetConfig;
    create_backup: boolean;
    password?: string | null;
}

// API レスポンス: PUT /api/target
export interface TargetUpdateResponse {
    success: boolean;
    git_pushed: boolean;
    git_commit_url?: string | null;
}

// バリデーションエラー
export interface ValidationError {
    path: string;
    message: string;
}

// API レスポンス: POST /api/target/validate
export interface ValidateResponse {
    valid: boolean;
    errors: ValidationError[];
}

// 動作確認ジョブ関連
export interface CheckItemRequest {
    item_name: string;
    store_name: string;
}

export interface CheckItemResponse {
    job_id: string;
}

export interface CheckJobStatus {
    job_id: string;
    status: "pending" | "running" | "completed" | "failed";
    progress: number;
    logs: string[];
    result: CheckJobResult | null;
    error: string | null;
}

export interface CheckJobResult {
    price: number | null;
    stock: number | null;
    thumb_url: string | null;
    crawl_status: "SUCCESS" | "FAILURE";
}

// チェックメソッドの表示名マッピング
export const CHECK_METHOD_LABELS: Record<CheckMethod, string> = {
    scrape: "スクレイピング",
    "my_lib.store.amazon.api": "Amazon PA-API",
    "my_lib.store.mercari.search": "メルカリ検索",
    "my_lib.store.rakuma.search": "ラクマ検索",
    "my_lib.store.paypay.search": "PayPayフリマ検索",
    "my_lib.store.yahoo.api": "Yahoo検索",
};

// アクションタイプの表示名マッピング
export const ACTION_TYPE_LABELS: Record<ActionType, string> = {
    click: "クリック",
    input: "入力",
    sixdigit: "6桁認証",
    recaptcha: "reCAPTCHA",
};

// デフォルト値
export const DEFAULT_STORE_DEFINITION: StoreDefinitionConfig = {
    name: "",
    check_method: "scrape",
    price_xpath: null,
    thumb_img_xpath: null,
    unavailable_xpath: null,
    price_unit: "円",
    point_rate: 0,
    color: null,
    action: [],
    affiliate_id: null,
};

export const DEFAULT_STORE_ENTRY: StoreEntryConfig = {
    name: "",
    url: null,
    asin: null,
    price_xpath: null,
    thumb_img_xpath: null,
    unavailable_xpath: null,
    price_unit: null,
    preload: null,
    search_keyword: null,
    exclude_keyword: null,
    price: null,
    cond: null,
    jan_code: null,
};

export const DEFAULT_ITEM_DEFINITION: ItemDefinitionConfig = {
    name: "",
    category: null,
    price: null,
    cond: null,
    store: [],
};

// Amazon 検索関連
export interface AmazonSearchRequest {
    keywords: string;
    item_count?: number;
}

export interface AmazonSearchResultItem {
    title: string;
    asin: string;
    price: number | null;
    thumb_url: string | null;
}

export interface AmazonSearchResponse {
    items: AmazonSearchResultItem[];
}

export interface AmazonSearchAvailableResponse {
    available: boolean;
}
