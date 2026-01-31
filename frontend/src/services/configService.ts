/**
 * target.yaml エディタ API クライアント
 */
import axios from "axios";
import type {
    TargetConfigResponse,
    TargetUpdateRequest,
    TargetUpdateResponse,
    ValidateResponse,
    TargetConfig,
    CheckItemRequest,
    CheckItemResponse,
    AmazonSearchResponse,
    AmazonSearchAvailableResponse,
} from "../types/config";

const API_BASE = "/price/api";
export const API_BASE_URL = "/price";

/**
 * target.yaml の現在の設定を取得
 */
export async function fetchTargetConfig(): Promise<TargetConfigResponse> {
    const response = await axios.get<TargetConfigResponse>(`${API_BASE}/target`);
    return response.data;
}

/**
 * target.yaml を更新
 */
export async function updateTargetConfig(
    config: TargetConfig,
    createBackup: boolean = true,
    password?: string | null
): Promise<TargetUpdateResponse> {
    const request: TargetUpdateRequest = {
        config,
        create_backup: createBackup,
        password,
    };
    const response = await axios.put<TargetUpdateResponse>(`${API_BASE}/target`, request);
    return response.data;
}

/**
 * 設定の事前バリデーション（保存せずに検証）
 */
export async function validateTargetConfig(config: TargetConfig): Promise<ValidateResponse> {
    const response = await axios.post<ValidateResponse>(`${API_BASE}/target/validate`, config);
    return response.data;
}

/**
 * 特定アイテムの価格チェックを開始
 */
export async function startCheckItem(itemName: string, storeName: string): Promise<CheckItemResponse> {
    const request: CheckItemRequest = {
        item_name: itemName,
        store_name: storeName,
    };
    const response = await axios.post<CheckItemResponse>(`${API_BASE}/target/check-item`, request);
    return response.data;
}

/**
 * 価格チェックの進捗を SSE でストリーミング取得
 * @param jobId ジョブID
 * @param onMessage メッセージ受信時のコールバック
 * @param onError エラー発生時のコールバック
 * @returns EventSource インスタンス（close() で接続を閉じる）
 */
export function streamCheckItemProgress(
    jobId: string,
    onMessage: (data: string) => void,
    onError: (error: Event) => void
): EventSource {
    const eventSource = new EventSource(`${API_BASE}/target/check-item/${jobId}/stream`);

    eventSource.onmessage = (event) => {
        onMessage(event.data);
    };

    eventSource.onerror = (error) => {
        onError(error);
        eventSource.close();
    };

    return eventSource;
}

/**
 * Amazon 検索 API が利用可能かどうかを確認
 */
export async function checkAmazonSearchAvailable(): Promise<boolean> {
    const response = await axios.get<AmazonSearchAvailableResponse>(`${API_BASE}/amazon/search/available`);
    return response.data.available;
}

/**
 * Amazon 商品をキーワードで検索
 */
export async function searchAmazon(keywords: string, itemCount: number = 10): Promise<AmazonSearchResponse> {
    const response = await axios.post<AmazonSearchResponse>(`${API_BASE}/amazon/search`, {
        keywords,
        item_count: itemCount,
    });
    return response.data;
}
