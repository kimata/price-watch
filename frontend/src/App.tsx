import { useState, useEffect, useCallback, useRef } from "react";
import Header from "./components/Header";
import HeroSection from "./components/HeroSection";
import EventBanner from "./components/EventBanner";
import PeriodSelector from "./components/PeriodSelector";
import VirtualizedItemGrid from "./components/VirtualizedItemGrid";
import ItemDetailPage from "./components/ItemDetailPage";
import MetricsPage from "./components/MetricsPage";
import ConfigEditorPage from "./components/config/ConfigEditorPage";
import { PriceRecordEditorPage } from "./components/priceRecord";
import LoadingSpinner from "./components/LoadingSpinner";
import Footer from "./components/Footer";
import { useItems } from "./hooks/useItems";
import type { Item, Period } from "./types";

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
function getPageFromUrl(): "list" | "item" | "metrics" | "config" {
    const pathname = window.location.pathname;
    if (pathname.match(/\/price\/metrics\/?$/)) {
        return "metrics";
    }
    if (pathname.match(/\/price\/config\/?$/)) {
        return "config";
    }
    if (pathname.match(/\/price\/items\/[^/]+/)) {
        return "item";
    }
    return "list";
}

// 有効な期間の値
const VALID_PERIODS: Period[] = ["30", "90", "180", "365", "all"];

// URL から期間を取得
function getPeriodFromUrl(): Period {
    const params = new URLSearchParams(window.location.search);
    const periodParam = params.get("period");
    if (periodParam && VALID_PERIODS.includes(periodParam as Period)) {
        return periodParam as Period;
    }
    return "30"; // デフォルト値
}

// URL を更新（期間パラメータを含む）
function updateUrlWithPeriod(period: Period, replace: boolean = false): void {
    const url = new URL(window.location.href);
    if (period === "30") {
        url.searchParams.delete("period"); // デフォルト値の場合はパラメータを削除
    } else {
        url.searchParams.set("period", period);
    }
    if (replace) {
        window.history.replaceState(window.history.state, "", url.toString());
    } else {
        window.history.pushState(window.history.state, "", url.toString());
    }
}

export default function App() {
    const [period, setPeriod] = useState<Period>(getPeriodFromUrl);
    const [selectedItem, setSelectedItem] = useState<Item | null>(null);
    const [showMetrics, setShowMetrics] = useState(getPageFromUrl() === "metrics");
    const [showConfig, setShowConfig] = useState(getPageFromUrl() === "config");
    const [configItemName, setConfigItemName] = useState<string | undefined>(undefined);
    const [showPriceRecordEditor, setShowPriceRecordEditor] = useState(false);
    const [previousPage, setPreviousPage] = useState<"list" | "item">("list");

    // TanStack Query でアイテム一覧を取得
    const {
        data: itemsData,
        isLoading: loading,
        error,
    } = useItems(period);

    const items = itemsData?.items ?? [];
    const storeDefinitions = itemsData?.store_definitions ?? [];
    const categories = itemsData?.categories ?? [];
    const checkIntervalSec = itemsData?.check_interval_sec ?? 1800;

    // 初期化済みフラグ（URL/OGP からのアイテム選択を1回だけ実行）
    const initialSelectDone = useRef(false);
    // ハッシュスクロール済みフラグ
    const hashScrollDone = useRef(false);

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

    // URL のハッシュに対応するカテゴリにスクロール（初回のみ）
    useEffect(() => {
        if (hashScrollDone.current || loading || items.length === 0 || selectedItem) {
            return;
        }

        const hash = window.location.hash;
        if (hash) {
            // 少し遅延させてDOMのレンダリングを待つ
            setTimeout(() => {
                const el = document.getElementById(hash.slice(1));
                if (el) {
                    // 要素の位置を取得して、オフセットを考慮してスクロール
                    const rect = el.getBoundingClientRect();
                    const offset = 24; // 余白
                    const y = rect.top + window.scrollY - offset;
                    window.scrollTo({ top: y, behavior: "smooth" });
                }
            }, 100);
            hashScrollDone.current = true;
        }
    }, [items, loading, selectedItem]);

    // ブラウザの戻る/進むボタン対応
    useEffect(() => {
        const handlePopState = () => {
            const page = getPageFromUrl();
            const urlPeriod = getPeriodFromUrl();
            setPeriod(urlPeriod);

            if (page === "metrics") {
                setShowMetrics(true);
                setShowConfig(false);
                setSelectedItem(null);
            } else if (page === "config") {
                setShowConfig(true);
                setShowMetrics(false);
                setSelectedItem(null);
            } else if (page === "item") {
                setShowMetrics(false);
                setShowConfig(false);
                const itemKey = getItemKeyFromUrl();
                if (itemKey) {
                    const matchedItem = findItemByKey(itemKey);
                    setSelectedItem(matchedItem);
                }
            } else {
                setShowMetrics(false);
                setShowConfig(false);
                setSelectedItem(null);
            }
        };

        window.addEventListener("popstate", handlePopState);
        return () => window.removeEventListener("popstate", handlePopState);
    }, [findItemByKey]);

    const handlePeriodChange = (newPeriod: Period) => {
        setPeriod(newPeriod);
        updateUrlWithPeriod(newPeriod, true); // replaceState で履歴を増やさない
    };

    // 期間パラメータを含む URL を生成
    const buildUrlWithPeriod = (basePath: string): string => {
        const url = new URL(basePath, window.location.origin);
        if (period !== "30") {
            url.searchParams.set("period", period);
        }
        return url.pathname + url.search + url.hash;
    };

    const handleItemClick = (item: Item) => {
        setSelectedItem(item);

        // URL を変更（履歴に追加、期間パラメータを保持）
        const itemKey = getItemKey(item);
        if (itemKey) {
            const newUrl = buildUrlWithPeriod(`/price/items/${encodeURIComponent(itemKey)}`);
            window.history.pushState({ itemKey }, "", newUrl);
        }

        // ページトップにスクロール
        window.scrollTo(0, 0);
    };

    const handleBackToList = () => {
        setSelectedItem(null);

        // URL を一覧ページに戻す（履歴に追加、期間パラメータを保持）
        const newUrl = buildUrlWithPeriod("/price/");
        window.history.pushState(null, "", newUrl);
    };

    const handleMetricsClick = () => {
        setShowMetrics(true);
        setShowConfig(false);
        setSelectedItem(null);
        const newUrl = buildUrlWithPeriod("/price/metrics");
        window.history.pushState(null, "", newUrl);
        window.scrollTo(0, 0);
    };

    const handleBackFromMetrics = () => {
        setShowMetrics(false);
        const newUrl = buildUrlWithPeriod("/price/");
        window.history.pushState(null, "", newUrl);
    };

    const handleConfigClick = (itemName?: string) => {
        // 遷移元を記録
        if (selectedItem) {
            setPreviousPage("item");
        } else {
            setPreviousPage("list");
        }
        setShowConfig(true);
        setShowMetrics(false);
        setConfigItemName(itemName);
        const newUrl = buildUrlWithPeriod("/price/config");
        window.history.pushState(null, "", newUrl);
        window.scrollTo(0, 0);
    };

    const handleBackFromConfig = () => {
        setShowConfig(false);
        setConfigItemName(undefined);
        // 遷移元に応じて戻り先を決定
        if (previousPage === "item" && selectedItem) {
            const itemKey = getItemKey(selectedItem);
            if (itemKey) {
                const newUrl = buildUrlWithPeriod(`/price/items/${encodeURIComponent(itemKey)}`);
                window.history.pushState({ itemKey }, "", newUrl);
            } else {
                const newUrl = buildUrlWithPeriod("/price/");
                window.history.pushState(null, "", newUrl);
            }
        } else {
            const newUrl = buildUrlWithPeriod("/price/");
            window.history.pushState(null, "", newUrl);
        }
    };

    const handlePriceRecordEditorClick = () => {
        setShowPriceRecordEditor(true);
        setPreviousPage("item");
        window.scrollTo(0, 0);
    };

    const handleBackFromPriceRecordEditor = () => {
        setShowPriceRecordEditor(false);
        // アイテム詳細ページに戻る
        if (selectedItem) {
            const itemKey = getItemKey(selectedItem);
            if (itemKey) {
                const newUrl = buildUrlWithPeriod(`/price/items/${encodeURIComponent(itemKey)}`);
                window.history.pushState({ itemKey }, "", newUrl);
            }
        }
    };

    // メトリクスページを表示
    if (showMetrics) {
        return <MetricsPage onBack={handleBackFromMetrics} />;
    }

    // 設定エディタページを表示
    if (showConfig) {
        return <ConfigEditorPage onBack={handleBackFromConfig} initialItemName={configItemName} previousPage={previousPage} selectedItem={selectedItem} />;
    }

    // 価格記録編集ページを表示
    if (showPriceRecordEditor && selectedItem) {
        return (
            <PriceRecordEditorPage
                item={selectedItem}
                onBack={handleBackFromPriceRecordEditor}
            />
        );
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
                checkIntervalSec={checkIntervalSec}
                onConfigClick={handleConfigClick}
                onPriceRecordEditorClick={handlePriceRecordEditorClick}
            />
        );
    }

    // 一覧ページを表示
    return (
        <div className="min-h-screen bg-gray-100">
            <Header items={items} onItemClick={handleItemClick} />
            <main className="max-w-7xl mx-auto px-4 py-6">
                {/* ヒーローセクション */}
                {!loading && items.length > 0 && (
                    <HeroSection
                        items={items}
                        storeDefinitions={storeDefinitions}
                        onItemClick={handleItemClick}
                    />
                )}

                <div className="mb-6">
                    <PeriodSelector selected={period} onChange={handlePeriodChange} />
                </div>

                {loading ? (
                    <LoadingSpinner />
                ) : error ? (
                    <div className="text-center py-8">
                        <p className="text-red-600">データの取得に失敗しました</p>
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
                        checkIntervalSec={checkIntervalSec}
                    />
                )}

                <EventBanner />
            </main>
            <Footer storeDefinitions={storeDefinitions} onMetricsClick={handleMetricsClick} onConfigClick={handleConfigClick} />
        </div>
    );
}
