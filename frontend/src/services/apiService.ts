import axios from "axios";
import type { ItemsResponse, HistoryResponse, EventsResponse, Period } from "../types";

const API_BASE = "/price/api";

export async function fetchItems(days: Period): Promise<ItemsResponse> {
    const response = await axios.get<ItemsResponse>(`${API_BASE}/items`, {
        params: { days },
    });
    return response.data;
}

export async function fetchItemHistory(itemKey: string, days: Period): Promise<HistoryResponse> {
    const response = await axios.get<HistoryResponse>(`${API_BASE}/items/${itemKey}/history`, {
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

export async function fetchItemEvents(itemKey: string, limit: number = 50): Promise<EventsResponse> {
    const response = await axios.get<EventsResponse>(`${API_BASE}/items/${itemKey}/events`, {
        params: { limit },
    });
    return response.data;
}

// === Web Push Notification API ===

export interface PushVapidKeyResponse {
    public_key: string;
}

export interface PushSubscribeRequest {
    item_key: string;
    endpoint: string;
    keys: {
        p256dh: string;
        auth: string;
    };
}

export interface PushSubscribeResponse {
    success: boolean;
    subscription_id: number | null;
}

export interface PushStatusResponse {
    subscribed: boolean;
    subscription_count: number;
}

export async function fetchVapidPublicKey(): Promise<PushVapidKeyResponse> {
    const response = await axios.get<PushVapidKeyResponse>(`${API_BASE}/push/vapid-public-key`);
    return response.data;
}

export async function subscribePush(request: PushSubscribeRequest): Promise<PushSubscribeResponse> {
    const response = await axios.post<PushSubscribeResponse>(`${API_BASE}/push/subscribe`, request);
    return response.data;
}

export async function unsubscribePush(itemKey: string, endpoint: string): Promise<{ success: boolean }> {
    const response = await axios.post<{ success: boolean }>(`${API_BASE}/push/unsubscribe`, {
        item_key: itemKey,
        endpoint,
    });
    return response.data;
}

export async function fetchPushStatus(itemKey: string, endpoint?: string): Promise<PushStatusResponse> {
    const params = endpoint ? { endpoint } : {};
    const response = await axios.get<PushStatusResponse>(`${API_BASE}/items/${itemKey}/push/status`, {
        params,
    });
    return response.data;
}
