import { useState, useEffect, useCallback, useRef } from "react";
import Header from "./components/Header";
import EventBanner from "./components/EventBanner";
import PeriodSelector from "./components/PeriodSelector";
import VirtualizedItemGrid from "./components/VirtualizedItemGrid";
import ItemDetailPage from "./components/ItemDetailPage";
import MetricsPage from "./components/MetricsPage";
import LoadingSpinner from "./components/LoadingSpinner";
import Footer from "./components/Footer";
import { fetchItems } from "./services/apiService";
import type { Item, Period, StoreDefinition } from "./types";

// SSE イベントタイプ
const SSE_EVENT_CONTENT = "content";

// グローバル変数から item_key を取得（OGP ページ用）
declare global {
    interface Window {
        __ITEM_KEY__?: string;
    }
}

// URL から item_key を抽出
function getItemKeyFromUrl(): string | null {
    const match = window.location.pathname.match(/\/price\/items\/([^/]+)/);
    return match ? decodeURIComponent(match[1]) : null;
}

// アイテムの item_key を取得（最初のストアの item_key を使用）
function getItemKey(item: Item): string | null {
    return item.stores.length > 0 ? item.stores[0].item_key : null;
}

// URL からページタイプを判定
function getPageFromUrl(): "list" | "item" | "metrics" {
    const pathname = window.location.pathname;
    if (pathname.match(/\/price\/metrics\/?$/)) {
        return "metrics";
    }
    if (pathname.match(/\/price\/items\/[^/]+/)) {
        return "item";
    }
    return "list";
}

export default function App() {
    const [items, setItems] = useState<Item[]>([]);
    const [storeDefinitions, setStoreDefinitions] = useState<StoreDefinition[]>([]);
    const [categories, setCategories] = useState<string[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [period, setPeriod] = useState<Period>("30");
    const [selectedItem, setSelectedItem] = useState<Item | null>(null);
    const [showMetrics, setShowMetrics] = useState(getPageFromUrl() === "metrics");

    // 初期化済みフラグ（URL/OGP からのアイテム選択を1回だけ実行）
    const initialSelectDone = useRef(false);

    // SSE 接続用 refs
    const eventSourceRef = useRef<EventSource | null>(null);
    const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    const loadItems = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await fetchItems(period);
            setItems(response.items);
            setStoreDefinitions(response.store_definitions || []);
            setCategories(response.categories || []);
        } catch (err) {
            setError("データの取得に失敗しました");
            console.error(err);
        } finally {
            setLoading(false);
        }
    }, [period]);

    useEffect(() => {
        loadItems();
    }, [loadItems]);

    // SSE 接続（コンテンツ更新イベントを受信）
    useEffect(() => {
        const connectSSE = () => {
            if (eventSourceRef.current) {
                eventSourceRef.current.close();
            }

            const eventSource = new EventSource("/price/api/event");

            eventSource.onmessage = (event) => {
                if (event.data === SSE_EVENT_CONTENT) {
                    loadItems();
                }
            };

            eventSource.onerror = () => {
                eventSource.close();
                // 5秒後に再接続
                reconnectTimerRef.current = setTimeout(() => {
                    connectSSE();
                }, 5000);
            };

            eventSourceRef.current = eventSource;
        };

        connectSSE();

        return () => {
            if (eventSourceRef.current) {
                eventSourceRef.current.close();
            }
            if (reconnectTimerRef.current) {
                clearTimeout(reconnectTimerRef.current);
            }
        };
    }, [loadItems]);

    // item_key からアイテムを検索
    const findItemByKey = useCallback(
        (itemKey: string): Item | null => {
            return (
                items.find((item) => item.stores.some((store) => store.item_key === itemKey)) ||
                null
            );
        },
        [items]
    );

    // URL または OGP からアイテムを自動選択（初回のみ）
    useEffect(() => {
        if (initialSelectDone.current || loading || items.length === 0) {
            return;
        }

        // URL から item_key を取得（優先）
        let itemKey = getItemKeyFromUrl();

        // URL になければ OGP 用のグローバル変数から取得
        if (!itemKey) {
            itemKey = window.__ITEM_KEY__ || null;
        }

        if (!itemKey) {
            return;
        }

        const matchedItem = findItemByKey(itemKey);
        if (matchedItem) {
            setSelectedItem(matchedItem);
            initialSelectDone.current = true;
        }
    }, [items, loading, findItemByKey]);

    // ブラウザの戻る/進むボタン対応
    useEffect(() => {
        const handlePopState = () => {
            const page = getPageFromUrl();
            if (page === "metrics") {
                setShowMetrics(true);
                setSelectedItem(null);
            } else if (page === "item") {
                setShowMetrics(false);
                const itemKey = getItemKeyFromUrl();
                if (itemKey) {
                    const matchedItem = findItemByKey(itemKey);
                    setSelectedItem(matchedItem);
                }
            } else {
                setShowMetrics(false);
                setSelectedItem(null);
            }
        };

        window.addEventListener("popstate", handlePopState);
        return () => window.removeEventListener("popstate", handlePopState);
    }, [findItemByKey]);

    const handlePeriodChange = (newPeriod: Period) => {
        setPeriod(newPeriod);
    };

    const handleItemClick = (item: Item) => {
        setSelectedItem(item);

        // URL を変更（履歴に追加）
        const itemKey = getItemKey(item);
        if (itemKey) {
            const newUrl = `/price/items/${encodeURIComponent(itemKey)}`;
            window.history.pushState({ itemKey }, "", newUrl);
        }

        // ページトップにスクロール
        window.scrollTo(0, 0);
    };

    const handleBackToList = () => {
        setSelectedItem(null);

        // URL を一覧ページに戻す（履歴に追加）
        window.history.pushState(null, "", "/price/");
    };

    const handleMetricsClick = () => {
        setShowMetrics(true);
        setSelectedItem(null);
        window.history.pushState(null, "", "/price/metrics");
        window.scrollTo(0, 0);
    };

    const handleBackFromMetrics = () => {
        setShowMetrics(false);
        window.history.pushState(null, "", "/price/");
    };

    // メトリクスページを表示
    if (showMetrics) {
        return <MetricsPage onBack={handleBackFromMetrics} />;
    }

    // 詳細ページを表示
    if (selectedItem) {
        return (
            <ItemDetailPage
                item={selectedItem}
                storeDefinitions={storeDefinitions}
                period={period}
                onBack={handleBackToList}
                onPeriodChange={handlePeriodChange}
            />
        );
    }

    // 一覧ページを表示
    return (
        <div className="min-h-screen bg-gray-100">
            <Header />
            <main className="max-w-7xl mx-auto px-4 py-6">
                <div className="mb-6">
                    <PeriodSelector selected={period} onChange={handlePeriodChange} />
                </div>

                {loading ? (
                    <LoadingSpinner />
                ) : error ? (
                    <div className="text-center py-8">
                        <p className="text-red-600">{error}</p>
                        <button
                            onClick={loadItems}
                            className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
                        >
                            再読み込み
                        </button>
                    </div>
                ) : items.length === 0 ? (
                    <div className="text-center py-8 text-gray-500">監視中のアイテムがありません</div>
                ) : (
                    <VirtualizedItemGrid
                        items={items}
                        storeDefinitions={storeDefinitions}
                        onItemClick={handleItemClick}
                        period={period}
                        categories={categories}
                    />
                )}

                <EventBanner />
            </main>
            <Footer storeDefinitions={storeDefinitions} onMetricsClick={handleMetricsClick} />
        </div>
    );
}
