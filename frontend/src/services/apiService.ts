import axios from "axios";
import type { ItemsResponse, HistoryResponse, EventsResponse, Period } from "../types";

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

export async function fetchEvents(limit: number = 10): Promise<EventsResponse> {
    const response = await axios.get<EventsResponse>(`${API_BASE}/events`, {
        params: { limit },
    });
    return response.data;
}

export async function fetchItemEvents(urlHash: string, limit: number = 50): Promise<EventsResponse> {
    const response = await axios.get<EventsResponse>(`${API_BASE}/items/${urlHash}/events`, {
        params: { limit },
    });
    return response.data;
}
