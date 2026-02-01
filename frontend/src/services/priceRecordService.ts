/**
 * 価格記録編集 API クライアント
 */
import axios from "axios";

const API_BASE = "/price/api";

// === 型定義 ===

export interface PriceRecord {
    id: number;
    price: number | null;
    stock: number | null;
    time: string;
    crawl_status: number;
}

export interface ItemInfo {
    id: number;
    item_key: string;
    name: string;
    store: string;
    price_unit: string;
}

export interface PriceRecordsResponse {
    item: ItemInfo;
    records: PriceRecord[];
    require_password: boolean;
}

export interface DeletePreviewResponse {
    record_count: number;
    event_count: number;
    prices: number[];
}

export interface DeleteRecordsResponse {
    deleted_records: number;
    deleted_events: number;
    new_lowest_price: number | null;
}

// === API 関数 ===

/**
 * 価格記録一覧を取得
 */
export async function fetchPriceRecords(itemKey: string): Promise<PriceRecordsResponse> {
    const response = await axios.get<PriceRecordsResponse>(
        `${API_BASE}/items/${encodeURIComponent(itemKey)}/price-records`
    );
    return response.data;
}

/**
 * 削除プレビューを取得
 */
export async function previewDeleteRecords(
    itemKey: string,
    recordIds: number[]
): Promise<DeletePreviewResponse> {
    const response = await axios.post<DeletePreviewResponse>(
        `${API_BASE}/items/${encodeURIComponent(itemKey)}/price-records/preview-delete`,
        { record_ids: recordIds }
    );
    return response.data;
}

/**
 * 価格記録を削除
 */
export async function deleteRecords(
    itemKey: string,
    recordIds: number[],
    password: string
): Promise<DeleteRecordsResponse> {
    const response = await axios.delete<DeleteRecordsResponse>(
        `${API_BASE}/items/${encodeURIComponent(itemKey)}/price-records`,
        { data: { record_ids: recordIds, password } }
    );
    return response.data;
}
