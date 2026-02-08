import { useState, useEffect, useMemo } from "react";
import type { Item } from "../types";

interface UseSearchResult {
    debouncedQuery: string;
    results: Item[];
    isSearching: boolean;
}

export function useSearch(
    query: string,
    items: Item[],
    delay: number = 300,
    maxResults: number = 8
): UseSearchResult {
    const [debouncedQuery, setDebouncedQuery] = useState(query);
    const [isSearching, setIsSearching] = useState(false);

    // デバウンス処理
    useEffect(() => {
        if (query !== debouncedQuery) {
            setIsSearching(true);
        }

        const timer = setTimeout(() => {
            setDebouncedQuery(query);
            setIsSearching(false);
        }, delay);

        return () => clearTimeout(timer);
    }, [query, delay, debouncedQuery]);

    // 検索結果をフィルタリング
    const results = useMemo(() => {
        if (!debouncedQuery.trim()) {
            return [];
        }

        const normalizedQuery = debouncedQuery.toLowerCase().trim();
        const filtered = items.filter((item) => item.name.toLowerCase().includes(normalizedQuery));

        // 最大件数まで返す
        return filtered.slice(0, maxResults);
    }, [debouncedQuery, items, maxResults]);

    return {
        debouncedQuery,
        results,
        isSearching,
    };
}
