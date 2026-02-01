import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { fetchItems, fetchItemHistory, fetchItemEvents } from "../services/apiService";
import { useSSESubscription } from "../contexts/SSEContext";
import type { Period, Item, StoreEntry, PriceHistoryPoint, Event } from "../types";

// クエリキー定義
export const queryKeys = {
    items: (period: Period) => ["items", period] as const,
    itemHistory: (itemKey: string, period: Period) => ["itemHistory", itemKey, period] as const,
    itemEvents: (itemKey: string) => ["itemEvents", itemKey] as const,
};

// アイテム一覧を取得
export function useItems(period: Period) {
    const queryClient = useQueryClient();

    const query = useQuery({
        queryKey: queryKeys.items(period),
        queryFn: () => fetchItems(period),
    });

    // SSEイベント時にアイテムを再取得
    const invalidateItems = useCallback(() => {
        queryClient.invalidateQueries({ queryKey: queryKeys.items(period) });
    }, [queryClient, period]);

    useSSESubscription(invalidateItems);

    return query;
}

// アイテム詳細データを取得（ストアごとの履歴を含む）
export function useItemDetails(item: Item | null, period: Period) {
    const queryClient = useQueryClient();

    const query = useQuery({
        queryKey: ["itemDetails", item?.name, period],
        queryFn: async (): Promise<Item | null> => {
            if (!item) return null;

            // 最新のアイテム一覧を取得
            const response = await fetchItems(period);
            const foundItem = response.items.find((i) => i.name === item.name);

            if (!foundItem) return null;

            // 各ストアの履歴を並列で取得
            const storesWithHistory = await Promise.all(
                foundItem.stores.map(async (store): Promise<StoreEntry> => {
                    try {
                        const historyResponse = await fetchItemHistory(store.item_key, period);
                        return {
                            ...store,
                            history: historyResponse.history,
                        };
                    } catch {
                        // 個別のエラーは無視して空の履歴を返す
                        return {
                            ...store,
                            history: [] as PriceHistoryPoint[],
                        };
                    }
                })
            );

            return {
                ...foundItem,
                stores: storesWithHistory,
            };
        },
        enabled: !!item,
    });

    // SSEイベント時にアイテム詳細を再取得
    const invalidateItemDetails = useCallback(() => {
        if (item) {
            queryClient.invalidateQueries({ queryKey: ["itemDetails", item.name, period] });
        }
    }, [queryClient, item, period]);

    useSSESubscription(invalidateItemDetails);

    return query;
}

// アイテムのイベント履歴を取得
export function useItemEvents(stores: StoreEntry[]) {
    const queryClient = useQueryClient();

    // 全ストアの item_key を連結してユニークなキーを作成
    const storeKeys = stores
        .map((s) => s.item_key)
        .sort()
        .join(",");

    const query = useQuery({
        queryKey: ["itemEvents", storeKeys],
        queryFn: async (): Promise<Event[]> => {
            // 全ストアのイベントを取得してマージ
            const allEvents: Event[] = [];
            for (const store of stores) {
                const response = await fetchItemEvents(store.item_key, 20);
                allEvents.push(...response.events);
            }
            // 日時でソート（新しい順）
            allEvents.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
            // 重複を除去（同じIDのイベント）
            const uniqueEvents = allEvents.filter(
                (event, index, self) => self.findIndex((e) => e.id === event.id) === index
            );
            return uniqueEvents.slice(0, 50);
        },
        enabled: stores.length > 0,
    });

    // SSEイベント時にイベント履歴を再取得
    const invalidateEvents = useCallback(() => {
        queryClient.invalidateQueries({ queryKey: ["itemEvents", storeKeys] });
    }, [queryClient, storeKeys]);

    useSSESubscription(invalidateEvents);

    return query;
}
