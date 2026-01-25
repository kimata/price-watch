import { useState, useEffect, useCallback } from "react";
import Header from "./components/Header";
import PeriodSelector from "./components/PeriodSelector";
import ItemCard from "./components/ItemCard";
import LoadingSpinner from "./components/LoadingSpinner";
import Footer from "./components/Footer";
import { fetchItems } from "./services/apiService";
import type { Item, Period, StoreDefinition } from "./types";

export default function App() {
    const [items, setItems] = useState<Item[]>([]);
    const [storeDefinitions, setStoreDefinitions] = useState<StoreDefinition[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [period, setPeriod] = useState<Period>("30");

    const loadItems = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await fetchItems(period);
            setItems(response.items);
            setStoreDefinitions(response.store_definitions || []);
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

    const handlePeriodChange = (newPeriod: Period) => {
        setPeriod(newPeriod);
    };

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
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {items.map((item) => (
                            <ItemCard key={item.name} item={item} storeDefinitions={storeDefinitions} />
                        ))}
                    </div>
                )}
            </main>
            <Footer storeDefinitions={storeDefinitions} />
        </div>
    );
}
