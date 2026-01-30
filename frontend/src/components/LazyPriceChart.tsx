import { useState, useEffect, useRef, useCallback } from "react";
import type { StoreEntry, StoreDefinition, PriceHistoryPoint, Period } from "../types";
import { fetchItemHistory } from "../services/apiService";
import PriceChart from "./PriceChart";

interface LazyPriceChartProps {
    stores: StoreEntry[];
    storeDefinitions: StoreDefinition[];
    className?: string;
    period?: Period;
    largeLabels?: boolean;
    checkIntervalSec?: number;
}

/**
 * 遅延読み込み付きの価格チャート
 *
 * Intersection Observer を使用してビューポート内に入ったときに
 * 履歴データを取得してグラフを描画します。
 */
export default function LazyPriceChart({
    stores,
    storeDefinitions,
    className = "h-40",
    period = "30",
    largeLabels = false,
    checkIntervalSec = 1800,
}: LazyPriceChartProps) {
    const [isVisible, setIsVisible] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const [storesWithHistory, setStoresWithHistory] = useState<StoreEntry[]>([]);
    const [error, setError] = useState<string | null>(null);
    const containerRef = useRef<HTMLDivElement>(null);

    // Intersection Observer でビューポート内に入ったら isVisible を true に
    useEffect(() => {
        const container = containerRef.current;
        if (!container) return;

        const observer = new IntersectionObserver(
            (entries) => {
                entries.forEach((entry) => {
                    if (entry.isIntersecting) {
                        setIsVisible(true);
                        // 一度表示されたら監視を停止
                        observer.unobserve(container);
                    }
                });
            },
            {
                // ビューポートから 200px 手前で読み込み開始
                rootMargin: "200px",
                threshold: 0,
            }
        );

        observer.observe(container);

        return () => {
            observer.disconnect();
        };
    }, []);

    // 履歴データを取得
    const loadHistory = useCallback(async () => {
        if (stores.length === 0) return;

        setIsLoading(true);
        setError(null);

        try {
            // 各ストアの履歴を並列で取得
            const historyPromises = stores.map(async (store) => {
                try {
                    const response = await fetchItemHistory(store.item_key, period);
                    return {
                        ...store,
                        history: response.history,
                    };
                } catch {
                    // 個別のエラーは無視して空の履歴を返す
                    return {
                        ...store,
                        history: [] as PriceHistoryPoint[],
                    };
                }
            });

            const results = await Promise.all(historyPromises);
            setStoresWithHistory(results);
        } catch {
            setError("履歴の取得に失敗しました");
        } finally {
            setIsLoading(false);
        }
    }, [stores, period]);

    // ビューポート内に入ったら履歴を取得
    useEffect(() => {
        if (isVisible && storesWithHistory.length === 0 && !isLoading) {
            loadHistory();
        }
    }, [isVisible, storesWithHistory.length, isLoading, loadHistory]);

    // period が変更されたら履歴を再取得
    useEffect(() => {
        if (isVisible && storesWithHistory.length > 0) {
            loadHistory();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [period]);

    // ローディング状態
    if (!isVisible || isLoading) {
        return (
            <div
                ref={containerRef}
                className={`${className} relative flex items-center justify-center bg-gray-50 rounded animate-pulse`}
            >
                <div className="flex items-center gap-2 text-gray-400 text-sm">
                    <svg
                        className="animate-spin h-4 w-4"
                        xmlns="http://www.w3.org/2000/svg"
                        fill="none"
                        viewBox="0 0 24 24"
                    >
                        <circle
                            className="opacity-25"
                            cx="12"
                            cy="12"
                            r="10"
                            stroke="currentColor"
                            strokeWidth="4"
                        />
                        <path
                            className="opacity-75"
                            fill="currentColor"
                            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                        />
                    </svg>
                    {isLoading ? "読み込み中..." : ""}
                </div>
            </div>
        );
    }

    // エラー状態
    if (error) {
        return (
            <div
                ref={containerRef}
                className={`${className} relative flex items-center justify-center bg-gray-100 rounded`}
            >
                <span className="text-gray-500 text-sm">{error}</span>
            </div>
        );
    }

    // グラフ表示
    return (
        <div ref={containerRef}>
            <PriceChart
                stores={storesWithHistory}
                storeDefinitions={storeDefinitions}
                className={className}
                period={period}
                largeLabels={largeLabels}
                checkIntervalSec={checkIntervalSec}
            />
        </div>
    );
}
