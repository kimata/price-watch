export interface PriceHistoryPoint {
    time: string;
    price: number;
    effective_price: number;
    stock: number;
}

export interface StoreEntry {
    url_hash: string;
    store: string;
    url: string;
    current_price: number;
    effective_price: number;
    point_rate: number;
    lowest_price: number | null;
    highest_price: number | null;
    stock: number;
    last_updated: string;
    history: PriceHistoryPoint[];
}

export interface Item {
    name: string;
    thumb_url: string | null;
    stores: StoreEntry[];
    best_store: string;
    best_effective_price: number;
}

export interface StoreDefinition {
    name: string;
    point_rate: number;
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
