import axios from "axios";
import type { ItemsResponse, HistoryResponse, Period } from "../types";

const API_BASE = "/price/api";

export async function fetchItems(days: Period): Promise<ItemsResponse> {
    const response = await axios.get<ItemsResponse>(`${API_BASE}/items`, {
        params: { days },
    });
    return response.data;
}

export async function fetchItemHistory(urlHash: string, days: Period): Promise<HistoryResponse> {
    const response = await axios.get<HistoryResponse>(`${API_BASE}/items/${urlHash}/history`, {
        params: { days },
    });
    return response.data;
}
