export interface PriceHistoryPoint {
    time: string;
    price: number | null; // null = 在庫なしで価格取得できず
    effective_price: number | null; // null = 在庫なしで価格取得できず
    stock: number;
}

export interface StoreEntry {
    item_key: string;
    store: string;
    url: string | null; // メルカリの場合は最安商品URL（動的）
    current_price: number | null; // null = 価格未取得
    effective_price: number | null; // null = 価格未取得
    point_rate: number;
    lowest_price: number | null;
    highest_price: number | null;
    stock: number;
    last_updated: string;
    history: PriceHistoryPoint[];
    product_url?: string | null; // メルカリ: 最安商品への直接リンク
    search_keyword?: string | null; // メルカリ: 検索キーワード（表示用）
}

export interface Item {
    name: string;
    thumb_url: string | null;
    stores: StoreEntry[];
    best_store: string;
    best_effective_price: number | null; // null = 全ストア価格なし
}

export interface StoreDefinition {
    name: string;
    point_rate: number;
    color: string | null;
}

export interface ItemsResponse {
    items: Item[];
    store_definitions: StoreDefinition[];
}

export interface HistoryResponse {
    history: PriceHistoryPoint[];
}

export type Period = "30" | "90" | "180" | "365" | "all";

export interface PeriodOption {
    value: Period;
    label: string;
}

export const PERIOD_OPTIONS: PeriodOption[] = [
    { value: "30", label: "30日" },
    { value: "90", label: "90日" },
    { value: "180", label: "180日" },
    { value: "365", label: "1年" },
    { value: "all", label: "全期間" },
];

// イベント関連の型
export type EventType =
    | "back_in_stock"
    | "crawl_failure"
    | "data_retrieval_failure"
    | "lowest_price"
    | "price_drop";

export interface Event {
    id: number;
    item_name: string;
    store: string;
    url: string;
    thumb_url: string | null;
    event_type: EventType;
    price: number | null;
    old_price: number | null;
    threshold_days: number | null;
    created_at: string;
    message: string;
    title: string;
}

export interface EventsResponse {
    events: Event[];
}
